import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy


ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from custom.action.invite import (  # noqa: E402
    HeartlinkGiftSelectBlue,
    HeartlinkGiftSelectTrekker,
)


class FakeContext:
    def __init__(self, trekker):
        self.trekker = trekker
        self.tasker = SimpleNamespace(stopping=False)

    def get_node_data(self, _node_name):
        return {"attach": {"trekker": self.trekker}}


class TestableHeartlinkSelector(HeartlinkGiftSelectTrekker):
    def __init__(self, click_results, bottom_results):
        super().__init__()
        self.click_results = iter(click_results)
        self.bottom_results = iter(bottom_results)
        self.click_names = []
        self.scroll_count = 0
        self.reset_count = 0

    def _click_trekker(self, _context, trekker_name):
        self.click_names.append(trekker_name)
        return next(self.click_results)

    def _scroll_to_next_page(self, _context, image=None):
        self.scroll_count += 1
        return next(self.bottom_results)

    def _scroll_to_top(self, _context):
        self.reset_count += 1
        return True


class TestableBlueGiftSelector(HeartlinkGiftSelectBlue):
    def __init__(self, counts, pages, scroll_results):
        super().__init__()
        self.counts = iter(counts)
        self.pages = iter(pages)
        self.scroll_results = iter(scroll_results)
        self.clicked = []
        self.scroll_count = 0

    def _read_selected_count(self, _context, image=None):
        return next(self.counts)

    @staticmethod
    def _capture_image(_context):
        return object()

    def _get_blue_candidates(self, _context, _image):
        return next(self.pages)

    def _click(self, _context, position):
        self.clicked.append(position)

    def _scroll_down(self, _context):
        self.scroll_count += 1
        return next(self.scroll_results)


class HeartlinkSelectorTests(unittest.TestCase):
    def test_name_filter_does_not_merge_trekker_with_address(self):
        results = [
            SimpleNamespace(text="花鈴", score=0.998, box=[185, 168, 48, 28]),
            SimpleNamespace(text="塞爾斯泰晨曦街78號", score=0.999, box=[189, 206, 160, 18]),
            SimpleNamespace(text="15", score=0.999, box=[311, 179, 32, 15]),
            SimpleNamespace(text="2040/4000", score=0.999, box=[349, 177, 87, 13]),
        ]

        filtered = HeartlinkGiftSelectTrekker._get_heartlink_name_results(results)

        self.assertEqual(filtered, [{"text": "花鈴", "x": 209, "y": 182}])

    def test_blank_name_keeps_current_trekker(self):
        selector = TestableHeartlinkSelector([], [])
        result = selector.run(FakeContext(""), SimpleNamespace(node_name="node"))
        self.assertTrue(result)
        self.assertEqual(selector.click_names, [])

    def test_scrolls_until_matching_trekker_is_clicked(self):
        selector = TestableHeartlinkSelector([False, True], [False])
        result = selector.run(FakeContext("Target"), SimpleNamespace(node_name="node"))
        self.assertTrue(result)
        self.assertEqual(selector.click_names, ["Target", "Target"])
        self.assertEqual(selector.scroll_count, 1)

    def test_missing_trekker_stops_gift_flow_and_resets_list(self):
        selector = TestableHeartlinkSelector([False], [True])
        result = selector.run(FakeContext("Missing"), SimpleNamespace(node_name="node"))
        self.assertFalse(result)
        self.assertEqual(selector.reset_count, 1)


class HeartlinkBlueGiftTests(unittest.TestCase):
    def test_blue_background_is_accepted_and_yellow_background_is_rejected(self):
        blue_image = numpy.zeros((720, 1280, 3), dtype=numpy.uint8)
        yellow_image = numpy.zeros((720, 1280, 3), dtype=numpy.uint8)
        position = (643, 309)
        blue_image[300:318, 600:660] = [230, 220, 150]
        yellow_image[300:318, 600:660] = [100, 210, 240]

        self.assertTrue(HeartlinkGiftSelectBlue._is_blue_candidate(blue_image, position))
        self.assertFalse(HeartlinkGiftSelectBlue._is_blue_candidate(yellow_image, position))

    def test_parses_selected_count_from_ocr_results(self):
        results = [SimpleNamespace(text="今日已贈禮 7/10")]
        self.assertEqual(HeartlinkGiftSelectBlue._parse_selected_count(results), 7)

    def test_deduplicates_overlapping_template_results(self):
        results = [
            SimpleNamespace(box=[100, 100, 40, 40]),
            SimpleNamespace(box=[105, 104, 40, 40]),
            SimpleNamespace(box=[200, 100, 40, 40]),
        ]
        self.assertEqual(
            HeartlinkGiftSelectBlue._deduplicate_candidates(results),
            [(120, 120), (220, 120)],
        )

    def test_scrolls_again_when_first_page_has_fewer_than_ten_gifts(self):
        first_page = [(100 + index, 200) for index in range(3)]
        second_page = [(200 + index, 300) for index in range(7)]
        selector = TestableBlueGiftSelector(
            counts=range(11),
            pages=[first_page, second_page],
            scroll_results=[True],
        )

        result = selector.run(FakeContext(""), SimpleNamespace())

        self.assertTrue(result)
        self.assertEqual(len(selector.clicked), 10)
        self.assertEqual(selector.scroll_count, 1)


class HeartlinkConfigurationTests(unittest.TestCase):
    def test_gift_modes_route_through_trekker_selector(self):
        tasks = json.loads(
            (ROOT / "assets/resource/tasks/talk.json").read_text(encoding="utf-8")
        )
        task = next(item for item in tasks["task"] if item["name"] == "心鏈送禮(新)")
        self.assertEqual(task["option"][0], "心链送礼新_旅人")

        option = tasks["option"]["心链送礼新_礼物类型"]
        for case in option["cases"]:
            click_mail = case["pipeline_override"]["心链_点击邮寄"]
            self.assertEqual(click_mail["next"], ["心链送礼新_选择旅人"])

        blue_case = next(case for case in option["cases"] if case["name"] == "只送藍色禮物")
        selector = blue_case["pipeline_override"]["心链送礼新_选择旅人"]
        self.assertEqual(selector["next"], ["心链送礼新_选择十个蓝色礼物"])


if __name__ == "__main__":
    unittest.main()
