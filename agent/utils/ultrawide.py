from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any, TypeVar


REFERENCE_WIDTH = 1280
REFERENCE_HEIGHT = 720
SOURCE_WIDTH = 5120
SOURCE_HEIGHT = 2160
SOURCE_ACTIVE_LEFT = 206
SOURCE_ACTIVE_RIGHT = 4915
SOURCE_UI_LEFT = 400
SOURCE_UI_RIGHT = 4720
_T = TypeVar("_T")


def is_ultrawide_size(width: int, height: int) -> bool:
    if width <= 0 or height <= 0:
        return False
    return width / height >= 2.2


def image_size(image: Any) -> tuple[int, int]:
    height, width = image.shape[:2]
    return int(width), int(height)


def horizontal_offsets(width: int, height: int) -> tuple[int, int, int]:
    if not is_ultrawide_size(width, height):
        return 0, 0, 0

    return tuple(
        _offset_for_x(reference_x, width)
        for reference_x in (0, REFERENCE_WIDTH // 2, REFERENCE_WIDTH)
    )


def _mapped_x(x: float, width: int) -> float:
    ui_left = width * SOURCE_UI_LEFT / SOURCE_WIDTH
    ui_right = width * SOURCE_UI_RIGHT / SOURCE_WIDTH
    return ui_left + x * (ui_right - ui_left) / REFERENCE_WIDTH


def _map_x(x: float, width: int) -> int:
    return round(_mapped_x(x, width))


def _offset_for_x(x: float, width: int) -> int:
    return round(_mapped_x(x, width) - x)


def adapt_point(
    point: Sequence[int],
    width: int,
    height: int,
) -> list[int]:
    x, y = point
    if not is_ultrawide_size(width, height):
        return [x, y]
    return [_map_x(x, width), y]


def adapt_rect(
    rect: Sequence[int],
    width: int,
    height: int,
) -> list[int]:
    x, y, rect_width, rect_height = rect
    if not is_ultrawide_size(width, height):
        return [x, y, rect_width, rect_height]

    if x <= 0 and x + rect_width >= REFERENCE_WIDTH:
        active_left = round(width * SOURCE_ACTIVE_LEFT / SOURCE_WIDTH)
        active_right = round(width * SOURCE_ACTIVE_RIGHT / SOURCE_WIDTH)
        return [active_left, y, active_right - active_left, rect_height]

    center_x = x + rect_width / 2
    return [
        x + _offset_for_x(center_x, width),
        y,
        rect_width,
        rect_height,
    ]


def adapt_span(
    span: Sequence[int],
    width: int,
    height: int,
) -> list[int]:
    start, end = span
    if not is_ultrawide_size(width, height):
        return [start, end]
    if start <= 0 and end >= REFERENCE_WIDTH:
        active_left = round(width * SOURCE_ACTIVE_LEFT / SOURCE_WIDTH)
        active_right = round(width * SOURCE_ACTIVE_RIGHT / SOURCE_WIDTH)
        return [active_left, active_right]
    return [_map_x(start, width), _map_x(end, width)]


def adapt_dataclass_layout(layout: _T, width: int, height: int) -> _T:
    values = {}
    for field_name in (
        "core_potential_roi",
        "general_potential_roi",
        "general_potential_level_roi",
        "recommended_level_roi",
        "potential_roi",
    ):
        values[field_name] = adapt_rect(
            getattr(layout, field_name),
            width,
            height,
        )
    values["x_border"] = adapt_span(layout.x_border, width, height)
    return replace(layout, **values)
