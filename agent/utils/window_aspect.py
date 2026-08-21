from __future__ import annotations

import ctypes
import json
import os
import re
import sys
import threading
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from time import sleep
from typing import Callable, Iterable


AGENT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = AGENT_DIR / "window_aspect.json"
ENV_ENABLED = "MAASTELLASORA_AUTO_RESIZE_16_9"


@dataclass(frozen=True)
class AspectPolicy:
    enabled: bool
    ratio: tuple[int, int]
    min_size: tuple[int, int]
    resize_to: tuple[tuple[int, int], ...]
    fullscreen_toggle_fallback: bool
    poll_interval_seconds: float
    class_pattern: str
    title_pattern: str


class AutoResizeHandle:
    """Owns the background watcher without exposing Win32 details to callers."""

    def __init__(self, stop_event: threading.Event, thread: threading.Thread | None):
        self._stop_event = stop_event
        self._thread = thread

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=3)


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {value!r}")


def _pair(value: object, name: str) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{name} must contain exactly two integers")
    width, height = value
    if not isinstance(width, int) or not isinstance(height, int):
        raise ValueError(f"{name} must contain exactly two integers")
    if width <= 0 or height <= 0:
        raise ValueError(f"{name} values must be positive")
    return width, height


def _interface_path() -> Path | None:
    candidates = (
        AGENT_DIR.parent / "interface.json",
        AGENT_DIR.parent / "assets" / "interface.json",
    )
    return next((path for path in candidates if path.is_file()), None)


def _controller_patterns() -> tuple[str, str]:
    path = _interface_path()
    if path is None:
        return r"^UnityWndClass$", r"xtlr|StellaSora"
    with path.open("r", encoding="utf-8") as stream:
        interface = json.load(stream)
    for controller in interface.get("controller", []):
        if controller.get("type") != "Win32":
            continue
        win32 = controller.get("win32", {})
        return (
            str(win32.get("class_regex", r"^UnityWndClass$")),
            str(win32.get("window_regex", r"xtlr|StellaSora")),
        )
    return r"^UnityWndClass$", r"xtlr|StellaSora"


def load_policy(path: Path = CONFIG_PATH) -> AspectPolicy:
    with path.open("r", encoding="utf-8") as stream:
        raw = json.load(stream)
    class_pattern, title_pattern = _controller_patterns()
    enabled = bool(raw.get("enabled", True))
    env_enabled = os.getenv(ENV_ENABLED)
    if env_enabled is not None:
        enabled = _parse_bool(env_enabled)
    resize_to = tuple(
        _pair(item, f"resize_to[{index}]")
        for index, item in enumerate(raw.get("resize_to", []))
    )
    if not resize_to:
        raise ValueError("resize_to must not be empty")
    return AspectPolicy(
        enabled=enabled,
        ratio=_pair(raw.get("ratio", [16, 9]), "ratio"),
        min_size=_pair(raw.get("min_size", [1920, 1080]), "min_size"),
        resize_to=resize_to,
        fullscreen_toggle_fallback=bool(raw.get("fullscreen_toggle_fallback", True)),
        poll_interval_seconds=max(float(raw.get("poll_interval_seconds", 2.0)), 0.25),
        class_pattern=class_pattern,
        title_pattern=title_pattern,
    )


def has_supported_client_size(
    size: tuple[int, int],
    ratio: tuple[int, int],
    min_size: tuple[int, int],
    tolerance: float = 0.01,
) -> bool:
    width, height = size
    if width < min_size[0] or height < min_size[1] or height == 0:
        return False
    expected = ratio[0] / ratio[1]
    return abs(width / height - expected) <= expected * tolerance


def choose_target_resolution(
    candidates: Iterable[tuple[int, int]],
    work_area: tuple[int, int],
    non_client_size: tuple[int, int],
) -> tuple[int, int] | None:
    available_width, available_height = work_area
    frame_width, frame_height = non_client_size
    for width, height in candidates:
        if width + frame_width <= available_width and height + frame_height <= available_height:
            return width, height
    return None


def _resize_matches(target: tuple[int, int], actual: tuple[int, int]) -> bool:
    return abs(actual[0] - target[0]) <= 2 and abs(actual[1] - target[1]) <= 2


def _run_resize_attempts(
    resize_once: Callable[[], tuple[tuple[int, int], tuple[int, int]]],
    toggle_fullscreen: Callable[[], None],
    allow_fullscreen_toggle: bool,
) -> tuple[tuple[int, int], tuple[int, int], bool]:
    target, actual = resize_once()
    if _resize_matches(target, actual) or not allow_fullscreen_toggle:
        return target, actual, False
    toggle_fullscreen()
    target, actual = resize_once()
    return target, actual, True


def start_auto_resize() -> AutoResizeHandle:
    stop_event = threading.Event()
    if sys.platform != "win32":
        return AutoResizeHandle(stop_event, None)
    try:
        policy = load_policy()
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(f"[window-aspect] disabled: invalid configuration: {error}", flush=True)
        return AutoResizeHandle(stop_event, None)
    if not policy.enabled:
        print("[window-aspect] automatic 16:9 resize is disabled", flush=True)
        return AutoResizeHandle(stop_event, None)
    thread = threading.Thread(
        target=_watch_for_game_window,
        args=(policy, stop_event),
        name="window-aspect-watcher",
        daemon=True,
    )
    thread.start()
    return AutoResizeHandle(stop_event, thread)


def _watch_for_game_window(policy: AspectPolicy, stop_event: threading.Event) -> None:
    try:
        win32 = _Win32WindowAdapter(policy)
    except (AttributeError, OSError) as error:
        print(f"[window-aspect] Win32 initialization failed: {error}", flush=True)
        return
    while not stop_event.is_set():
        hwnd = win32.find_game_window()
        if hwnd:
            try:
                result = win32.ensure_supported_resolution(hwnd)
                print(f"[window-aspect] {result}", flush=True)
            except OSError as error:
                print(f"[window-aspect] resize failed: {error}", flush=True)
            return
        stop_event.wait(policy.poll_interval_seconds)


class _Rect(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class _MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", _Rect),
        ("rcWork", _Rect),
        ("dwFlags", wintypes.DWORD),
    ]


class _Win32WindowAdapter:
    GWL_STYLE = -16
    GWL_EXSTYLE = -20
    WS_CAPTION = 0x00C00000
    WS_POPUP = 0x80000000
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    SWP_FRAMECHANGED = 0x0020
    MONITOR_DEFAULTTONEAREST = 2
    SW_RESTORE = 9
    WM_SYSKEYDOWN = 0x0104
    WM_SYSKEYUP = 0x0105
    VK_RETURN = 0x0D

    def __init__(self, policy: AspectPolicy):
        self.policy = policy
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.class_regex = re.compile(policy.class_pattern, re.IGNORECASE)
        self.title_regex = re.compile(policy.title_pattern, re.IGNORECASE)
        self._configure_signatures()
        set_dpi_context = getattr(self.user32, "SetThreadDpiAwarenessContext", None)
        if set_dpi_context is not None:
            set_dpi_context(ctypes.c_void_p(-4))

    def _configure_signatures(self) -> None:
        self.user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
        self.user32.EnumWindows.restype = wintypes.BOOL
        self.user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user32.GetClassNameW.restype = ctypes.c_int
        self.user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user32.GetWindowTextW.restype = ctypes.c_int
        self.user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user32.IsWindowVisible.restype = wintypes.BOOL
        self.user32.IsZoomed.argtypes = [wintypes.HWND]
        self.user32.IsZoomed.restype = wintypes.BOOL
        self.user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.ShowWindow.restype = wintypes.BOOL
        self.user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(_Rect)]
        self.user32.GetClientRect.restype = wintypes.BOOL
        self.user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(_Rect)]
        self.user32.GetWindowRect.restype = wintypes.BOOL
        self.user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.GetWindowLongW.restype = wintypes.LONG
        self.user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
        self.user32.SetWindowLongW.restype = wintypes.LONG
        self.user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        self.user32.SetWindowPos.restype = wintypes.BOOL
        self.user32.PostMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        self.user32.PostMessageW.restype = wintypes.BOOL
        self.user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        self.user32.MonitorFromWindow.restype = wintypes.HANDLE
        self.user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MonitorInfo)]
        self.user32.GetMonitorInfoW.restype = wintypes.BOOL

    def find_game_window(self) -> int | None:
        matches: list[int] = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def callback(hwnd: int, _lparam: int) -> bool:
            if not self.user32.IsWindowVisible(hwnd):
                return True
            class_name = ctypes.create_unicode_buffer(256)
            title = ctypes.create_unicode_buffer(512)
            self.user32.GetClassNameW(hwnd, class_name, len(class_name))
            self.user32.GetWindowTextW(hwnd, title, len(title))
            if self.class_regex.search(class_name.value) and self.title_regex.search(title.value):
                matches.append(hwnd)
                return False
            return True

        callback_ref = callback_type(callback)
        self.user32.EnumWindows(callback_ref, 0)
        return matches[0] if matches else None

    def ensure_supported_resolution(self, hwnd: int) -> str:
        current = self._size(hwnd, client=True)
        if has_supported_client_size(current, self.policy.ratio, self.policy.min_size):
            return f"game client already supported: {current[0]}x{current[1]}"

        target, actual, used_fallback = _run_resize_attempts(
            resize_once=lambda: self._resize_once(hwnd),
            toggle_fullscreen=lambda: self._toggle_fullscreen(hwnd),
            allow_fullscreen_toggle=self.policy.fullscreen_toggle_fallback,
        )
        if _resize_matches(target, actual):
            suffix = " after fullscreen toggle" if used_fallback else ""
            return (
                f"game client resized from {current[0]}x{current[1]} "
                f"to {actual[0]}x{actual[1]}{suffix}"
            )
        fallback = " after fullscreen toggle" if used_fallback else ""
        raise OSError(
            f"game rejected target {target[0]}x{target[1]}{fallback}; "
            f"actual client is {actual[0]}x{actual[1]}"
        )

    def _resize_once(self, hwnd: int) -> tuple[tuple[int, int], tuple[int, int]]:
        if self.user32.IsZoomed(hwnd):
            self.user32.ShowWindow(hwnd, self.SW_RESTORE)
            sleep(0.1)
        self._show_title_bar(hwnd)
        sleep(0.1)
        outer = self._size(hwnd, client=False)
        client = self._size(hwnd, client=True)
        non_client = (max(outer[0] - client[0], 0), max(outer[1] - client[1], 0))
        work_rect = self._work_rect(hwnd)
        work_size = (work_rect.right - work_rect.left, work_rect.bottom - work_rect.top)
        target = choose_target_resolution(self.policy.resize_to, work_size, non_client)
        if target is None:
            raise OSError("no configured 16:9 client size fits the monitor work area")

        outer_width = target[0] + non_client[0]
        outer_height = target[1] + non_client[1]
        x = work_rect.left + (work_size[0] - outer_width) // 2
        y = work_rect.top + (work_size[1] - outer_height) // 2
        flags = self.SWP_NOZORDER | self.SWP_NOACTIVATE
        if not self.user32.SetWindowPos(hwnd, None, x, y, outer_width, outer_height, flags):
            self._raise_last_error("SetWindowPos resize")

        for _ in range(20):
            actual = self._size(hwnd, client=True)
            if _resize_matches(target, actual):
                return target, actual
            sleep(0.1)
        return target, self._size(hwnd, client=True)

    def _toggle_fullscreen(self, hwnd: int) -> None:
        scan_code = 0x1C
        key_down = 1 | (scan_code << 16) | (1 << 29)
        key_up = key_down | (1 << 30) | (1 << 31)
        if not self.user32.PostMessageW(
            hwnd,
            self.WM_SYSKEYDOWN,
            self.VK_RETURN,
            key_down,
        ):
            self._raise_last_error("PostMessageW Alt+Enter key down")
        if not self.user32.PostMessageW(
            hwnd,
            self.WM_SYSKEYUP,
            self.VK_RETURN,
            key_up,
        ):
            self._raise_last_error("PostMessageW Alt+Enter key up")
        sleep(1.0)

    def _show_title_bar(self, hwnd: int) -> None:
        style = int(self.user32.GetWindowLongW(hwnd, self.GWL_STYLE)) & 0xFFFFFFFF
        new_style = (style | self.WS_CAPTION) & ~self.WS_POPUP
        if new_style == style:
            return
        ctypes.set_last_error(0)
        previous = self.user32.SetWindowLongW(hwnd, self.GWL_STYLE, ctypes.c_long(new_style).value)
        if previous == 0 and ctypes.get_last_error() != 0:
            self._raise_last_error("SetWindowLongW")
        rect = self._rect(hwnd, client=False)
        flags = self.SWP_NOZORDER | self.SWP_NOACTIVATE | self.SWP_FRAMECHANGED
        if not self.user32.SetWindowPos(
            hwnd,
            None,
            rect.left,
            rect.top,
            rect.right - rect.left,
            rect.bottom - rect.top,
            flags,
        ):
            self._raise_last_error("SetWindowPos frame refresh")

    def _work_rect(self, hwnd: int) -> _Rect:
        monitor = self.user32.MonitorFromWindow(hwnd, self.MONITOR_DEFAULTTONEAREST)
        if not monitor:
            self._raise_last_error("MonitorFromWindow")
        info = _MonitorInfo(cbSize=ctypes.sizeof(_MonitorInfo))
        if not self.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            self._raise_last_error("GetMonitorInfoW")
        return info.rcWork

    def _rect(self, hwnd: int, client: bool) -> _Rect:
        rect = _Rect()
        getter = self.user32.GetClientRect if client else self.user32.GetWindowRect
        if not getter(hwnd, ctypes.byref(rect)):
            self._raise_last_error("GetClientRect" if client else "GetWindowRect")
        return rect

    def _size(self, hwnd: int, client: bool) -> tuple[int, int]:
        rect = self._rect(hwnd, client)
        return rect.right - rect.left, rect.bottom - rect.top

    @staticmethod
    def _raise_last_error(operation: str) -> None:
        error_code = ctypes.get_last_error()
        raise OSError(error_code, f"{operation} failed", None, error_code)
