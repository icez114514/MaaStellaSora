"""Read-only checks for the fork extension's upstream touchpoints."""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
ERRORS: list[str] = []


def load_jsonc(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    out = []
    quoted = escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if quoted:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
            out.append(char)
        elif text[index:index + 2] == "//":
            while index < len(text) and text[index] != "\n":
                index += 1
            continue
        else:
            out.append(char)
        index += 1
    return json.loads(re.sub(r",\s*([}\]])", r"\1", "".join(out)))


def require(condition: bool, label: str) -> None:
    if not condition:
        ERRORS.append(label)


def pipeline_nodes(bundle: Path) -> dict:
    nodes = {}
    for path in sorted((bundle / "pipeline").rglob("*.json")):
        nodes.update(load_jsonc(path))
    return nodes


def custom_name(node: dict, section: str, key: str) -> str | None:
    return node.get(section, {}).get("param", {}).get(key)


def main() -> int:
    interface = load_jsonc(ASSETS / "interface.json")
    tasks = load_jsonc(ASSETS / "resource/fork/tasks.json")
    require(
        interface.get("agent", {}).get("child_args", [])[-1:] ==
        ["./../agent/fork_ext/entry.py"],
        "interface.agent.child_args must point to fork_ext/entry.py",
    )
    require(
        "resource/fork/tasks.json" in interface.get("import", []),
        "interface.import must include resource/fork/tasks.json",
    )

    base = pipeline_nodes(ASSETS / "resource/base")
    fork = pipeline_nodes(ASSETS / "resource/fork/base")
    upstream_contracts = {
        "星塔_入口_agent": ("action", "custom_action", "ascension_preparation"),
        "星塔_循环用节点_agent": ("action", "custom_action", "ascension_loop"),
        "星塔_节点_选择潜能_agent": (
            "recognition", "custom_recognition", "choose_potential_recognition"
        ),
        "星塔_节点_进行对话选择_agent": (
            "recognition", "custom_recognition", "event_recognition"
        ),
    }
    for name, (section, key, expected) in upstream_contracts.items():
        require(custom_name(base.get(name, {}), section, key) == expected,
                f"upstream contract changed: {name} -> {expected}")

    required_nodes = [
        "星塔_节点_进入商店_agent", "星塔_通用_识别当前金币_agent",
        "星塔_节点_选择潜能_点击刷新_agent",
        "星塔_保存记录_agent", "星塔_回到难度选择界面_agent",
        "星塔_回到出发界面_agent", "星塔_回到主页_agent", "心链_入口",
        "心链_点击邮寄", "心链_选择礼物", "心链_赠送礼物",
        "邀约_点击空白", "邀约_还是算了", "邀约_送出礼物",
        "邀约_默契提升", "猎影合围_追踪目标_战斗结束",
        "猎影合围_协助_战斗结束", "通用_点击空白处继续",
    ]
    for name in required_nodes:
        require(name in base, f"upstream node missing: {name}")
    expected_edges = {
        "星塔_节点_进入商店_agent": "星塔_节点_商店_购物_agent",
        "星塔_节点_选择潜能_agent": "星塔_节点_选择潜能_拿走_agent",
        "星塔_循环用节点_agent": "星塔_快速战斗按钮_agent",
        "心链_点击邮寄": "心链_选择礼物",
        "邀约_送出礼物": "邀约_已回到邀约界面",
        "猎影合围_协助_战斗结束": "猎影合围_协助_协助讨伐主界面",
    }
    for source, target in expected_edges.items():
        steps = base.get(source, {}).get("next", [])
        names = [step if isinstance(step, str) else step.get("name") for step in steps]
        require(target in names, f"upstream connection changed: {source} -> {target}")

    task_by_name = {task["name"]: task for task in tasks.get("task", [])}
    tower = task_by_name.get("Fork_自动刷650", {})
    gift = task_by_name.get("Fork_心链送礼", {})
    require(tower.get("entry") == "星塔_入口_agent", "fork tower task entry changed")
    require(gift.get("entry") == "心链_入口", "fork heartlink task entry changed")
    require(
        tower.get("pipeline_override", {}).get("星塔_节点_进入商店_agent", {}).get("next") ==
        ["星塔_自动刷650_检查金币_agent"],
        "fork first-shop route changed",
    )
    require(
        gift.get("pipeline_override", {}).get("心链_点击邮寄", {}).get("next") ==
        ["心链送礼新_选择旅人"],
        "fork gift route changed",
    )
    for name in (
        "星塔_自动刷650_检查金币_agent", "星塔_自动刷650_放弃_agent",
        "心链送礼新_选择旅人", "心链送礼新_选择十个蓝色礼物",
    ):
        require(name in fork, f"fork node missing: {name}")
    require((ASSETS / "resource/fork/base/image/gift_blue_good.png").is_file(),
            "blue-gift template missing")
    extension_code = (
        (ROOT / "agent/fork_ext/auto_farm_650.py").read_text(encoding="utf-8")
        + (ROOT / "agent/fork_ext/heartlink.py").read_text(encoding="utf-8")
    )
    for custom in (
        "fork_choose_potential_650", "fork_event_650_first",
        "fork_auto_farm_650_check", "fork_auto_farm_650_loop",
        "HeartlinkGiftSelectTrekker", "HeartlinkGiftSelectBlue",
    ):
        require(f'("{custom}")' in extension_code, f"custom registration missing: {custom}")
    invite_code = (ROOT / "agent/custom/action/invite.py").read_text(encoding="utf-8")
    for helper in ("_scroll_to_next_page", "_scroll_to_top"):
        require(f"def {helper}(" in invite_code,
                f"upstream InviteAuto helper changed: {helper}")

    required_paths = {
        "官服": ["resource/base", "resource/fork/base"],
        "台服": ["resource/base", "resource/tw", "resource/fork/base", "resource/fork/tw"],
        "国际服": ["resource/base", "resource/en", "resource/fork/base", "resource/fork/en"],
        "日服": ["resource/base", "resource/jp", "resource/fork/base", "resource/fork/jp"],
    }
    for resource in interface.get("resource", []):
        name = resource.get("name")
        expected = ["{PROJECT_DIR}/" + value for value in required_paths.get(name, [])]
        require(resource.get("path") == expected, f"resource path order changed: {name}")
        for value in resource.get("path", []):
            require((ASSETS / value.removeprefix("{PROJECT_DIR}/")).is_dir(),
                    f"resource bundle missing: {value}")

    if ERRORS:
        for error in ERRORS:
            print("FAIL:", error)
        return 1
    print("Fork extension touchpoints OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
