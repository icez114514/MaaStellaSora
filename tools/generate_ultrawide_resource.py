from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

import jsonc


REFERENCE_WIDTH = 1280
REFERENCE_HEIGHT = 720
TARGET_WIDTH = round(5120 / 3)
TARGET_HEIGHT = 720
ACTIVE_LEFT = round(TARGET_WIDTH * 206 / 5120)
ACTIVE_RIGHT = round(TARGET_WIDTH * 4915 / 5120)
UI_LEFT = TARGET_WIDTH * 400 / 5120
UI_RIGHT = TARGET_WIDTH * 4720 / 5120
COORDINATE_KEYS = {"roi", "target", "begin", "end"}
PROFILES = {
    "base": ("base",),
    "tw": ("base", "tw"),
    "en": ("base", "en"),
    "jp": ("base", "jp"),
}
BASE_OVERRIDES = {
    "星塔_开始爬塔_agent": {
        "next": [
            "[JumpBack]星塔_开始爬塔_检测商店购物界面_agent",
            "[JumpBack]星塔_节点_进入潜能选择_agent",
            "[JumpBack]星塔_节点_进入对话_agent",
            "[JumpBack]星塔_节点_进入对话选择_agent",
            "星塔_开始爬塔_检测背包按钮_agent",
        ],
    },
    "星塔_开始爬塔_检测背包按钮_agent": {
        "recognition": {
            "param": {
                "template": ["ClimbTower_agent/bag_button_5120x2160.png"],
                "threshold": 0.8,
            },
        },
    },
}


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_layers(resource_root: Path, layers: tuple[str, ...]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for layer in layers:
        pipeline_root = resource_root / layer / "pipeline"
        for path in sorted(pipeline_root.rglob("*.json")):
            data = jsonc.loads(path.read_text(encoding="utf-8"))
            merged = deep_merge(merged, data)
    return merged


def horizontal_offset(center_x: float) -> int:
    mapped_x = UI_LEFT + center_x * (UI_RIGHT - UI_LEFT) / REFERENCE_WIDTH
    return round(mapped_x - center_x)


def transform_coordinate(key: str, value: list[int]) -> list[int]:
    if key == "roi" or (key == "target" and len(value) == 4):
        x, y, width, height = value
        if x <= 0 and x + width >= REFERENCE_WIDTH:
            return [ACTIVE_LEFT, y, ACTIVE_RIGHT - ACTIVE_LEFT, height]
        return [x + horizontal_offset(x + width / 2), y, width, height]

    if len(value) == 2:
        x, y = value
        return [x + horizontal_offset(x), y]

    raise ValueError(f"Unsupported coordinate {key}={value}")


def extract_coordinate_patch(value: Any) -> Any:
    if not isinstance(value, dict):
        return None

    patch = {}
    for key, child in value.items():
        if (
            key in COORDINATE_KEYS
            and isinstance(child, list)
            and len(child) in (2, 4)
            and all(isinstance(item, int) and not isinstance(item, bool) for item in child)
        ):
            patch[key] = transform_coordinate(key, child)
            continue

        child_patch = extract_coordinate_patch(child)
        if child_patch:
            patch[key] = child_patch

    return patch or None


def generate_profile(resource_root: Path, output_root: Path, profile: str) -> Path:
    merged = load_layers(resource_root, PROFILES[profile])
    output = {}
    for node_name, node in merged.items():
        patch = extract_coordinate_patch(node)
        if patch:
            output[node_name] = patch

    if profile == "base":
        output = deep_merge(output, BASE_OVERRIDES)

    output_path = output_root / profile / "pipeline" / "ultrawide.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=(*PROFILES, "all"), default="all")
    parser.add_argument(
        "--resource-root",
        type=Path,
        default=Path("assets/resource"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("assets/resource/ultrawide_5120"),
    )
    args = parser.parse_args()

    profiles = PROFILES if args.profile == "all" else (args.profile,)
    for profile in profiles:
        output_path = generate_profile(
            args.resource_root,
            args.output_root,
            profile,
        )
        print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
