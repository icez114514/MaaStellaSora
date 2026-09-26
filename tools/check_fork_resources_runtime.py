"""Load each configured bundle sequence in an isolated MaaFramework process."""

import json
from pathlib import Path

from maa.resource import Resource

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"


def main() -> None:
    interface = json.loads((ASSETS / "interface.json").read_text(encoding="utf-8"))
    for configuration in interface["resource"]:
        resource = Resource()
        for raw_path in configuration["path"]:
            path = ASSETS / raw_path.removeprefix("{PROJECT_DIR}/")
            if not resource.post_bundle(path).wait().status.succeeded:
                raise AssertionError(f"resource load failed: {path}")

        shop = resource.get_node_data("星塔_自动刷650_检查金币_agent")
        assert shop["action"]["param"]["custom_action"] == "fork_auto_farm_650_check"
        abandon = resource.get_node_data("星塔_自动刷650_放弃_agent")
        assert abandon["action"]["type"] == "Click"
        assert abandon["action"]["param"]["target"] is True
        assert "星塔_回到主页_agent" in [step["name"] for step in abandon["next"]]
        gift = resource.get_node_data("心链送礼新_选择十个蓝色礼物")
        assert gift["action"]["param"]["custom_action"] == "HeartlinkGiftSelectBlue"
        invitation = resource.get_node_data("邀约_送出礼物")
        assert [step["name"] for step in invitation["next"]] == [
            "邀约_送出礼物后点击人物_1"
        ]
        if configuration["name"] == "台服":
            entry = resource.get_node_data("星塔_入口_agent")
            assert entry["attach"]["event_rules"] == "ascension_event_tw.json"
            assert "送出禮物" in invitation["recognition"]["param"]["expected"]
            assert "放棄" in abandon["recognition"]["param"]["expected"]
        print(f"Loaded fork resource: {configuration['name']}")


if __name__ == "__main__":
    main()
