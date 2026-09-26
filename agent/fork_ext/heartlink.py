import difflib
import re
import time

import numpy
from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context

from custom.action.invite import InviteAuto
from utils import logger


@AgentServer.custom_action("HeartlinkGiftSelectTrekker")
class HeartlinkGiftSelectTrekker(InviteAuto):
    """Select the configured trekker before entering the gift flow."""

    @staticmethod
    def _get_heartlink_name_results(results, threshold=0.7):
        """Extract trekker names without merging the address shown below them."""
        if not results:
            return []

        valid_results = [result for result in results if result.score >= threshold]
        level_centers = []
        for result in valid_results:
            x, y, w, h = result.box
            if 280 <= x <= 350 and w <= 60 and result.text.strip().isdigit():
                level_centers.append(y + h // 2)

        names = []
        for result in valid_results:
            x, y, w, h = result.box
            text = result.text.strip()
            if not text or text.isascii() or any(char.isdigit() for char in text):
                continue

            center_y = y + h // 2
            aligned_with_level = any(abs(center_y - level_y) <= 18 for level_y in level_centers)
            name_shape_fallback = 150 <= x <= 280 and h >= 24 and w <= 140
            if aligned_with_level or name_shape_fallback:
                names.append({"text": text, "x": x + w // 2, "y": center_y})
        return names

    def _click_trekker(
            self,
            context: Context,
            trekker_name: str,
    ) -> bool:
        translate_table = str.maketrans({
            '（': '(',
            '）': ')',
            ' ': None,
            '　': None,
        })
        formatted_name = trekker_name.translate(translate_table)

        image = context.tasker.controller.post_screencap().wait().get()
        reco_detail = context.run_recognition("邀约_左方识别邀约对象", image)
        results = self._get_heartlink_name_results(reco_detail.all_results)
        self.logger.debug(f"心链送礼识别出{len(results)}个旅人名称，开始比较")

        for result in results:
            formatted_result = result["text"].translate(translate_table)
            similarity = difflib.SequenceMatcher(
                None,
                formatted_result,
                formatted_name,
            ).ratio()
            if similarity >= 0.8:
                self.logger.debug(
                    f"心链送礼旅人识别成功！预期: {formatted_name}, "
                    f"识别结果: {formatted_result}, 相似度: {similarity:.2f}"
                )
                context.tasker.controller.post_click(result["x"], result["y"]).wait()
                return True
        return False

    def run(
            self,
            context: Context,
            argv: CustomAction.RunArg,
    ) -> bool:
        node_data = context.get_node_data(argv.node_name)
        try:
            trekker_name = str(node_data["attach"]["trekker"]).strip()
        except (TypeError, KeyError, AttributeError) as exc:
            self.logger.warning(f"读取心链送礼旅人名称失败: {exc}")
            return False

        if not trekker_name or trekker_name in ("x", "X"):
            self.logger.debug("心链送礼未指定旅人，维持当前选择")
            return True

        while not context.tasker.stopping:
            if self._click_trekker(context, trekker_name):
                self.logger.info(f"已选择心链送礼旅人: {trekker_name}")
                return True

            if self._scroll_to_next_page(context):
                self.logger.warning(f"找不到心链送礼旅人: {trekker_name}")
                self._scroll_to_top(context)
                return False

        return False


@AgentServer.custom_action("HeartlinkGiftSelectBlue")
class HeartlinkGiftSelectBlue(CustomAction):
    """Select ten blue gifts, scrolling the gift grid as needed."""

    TARGET_COUNT = 10
    MAX_SCROLLS = 25
    GIFT_ROI = (650, 180, 1200, 625)

    def __init__(self):
        super().__init__()
        self.logger = logger.get_logger()

    @staticmethod
    def _parse_selected_count(results):
        for result in results or []:
            text = re.sub(r"\s+", "", result.text)
            match = re.search(r"(?<!\d)(\d{1,2})/10(?!\d)", text)
            if match:
                count = int(match.group(1))
                if 0 <= count <= 10:
                    return count
        return None

    @staticmethod
    def _deduplicate_candidates(results):
        candidates = []
        for result in sorted(results or [], key=lambda item: (item.box[1], item.box[0])):
            x, y, w, h = result.box
            center = (x + w // 2, y + h // 2)
            if any(abs(center[0] - old[0]) < 20 and abs(center[1] - old[1]) < 20
                   for old in candidates):
                continue
            candidates.append(center)
        return candidates

    @staticmethod
    def _is_blue_candidate(image, position, minimum_ratio=0.35):
        image_array = numpy.asarray(image)
        if image_array.ndim != 3 or image_array.shape[2] < 3:
            return False

        center_x, center_y = position
        height, width = image_array.shape[:2]
        x1 = max(0, center_x - 43)
        x2 = min(width, center_x + 17)
        y1 = max(0, center_y - 9)
        y2 = min(height, center_y + 9)
        background = image_array[y1:y2, x1:x2, :3]
        if background.size == 0:
            return False

        blue = background[:, :, 0].astype(numpy.int16)
        green = background[:, :, 1].astype(numpy.int16)
        red = background[:, :, 2].astype(numpy.int16)
        cyan_pixels = (blue >= red + 20) & (green >= red + 5)
        return float(numpy.mean(cyan_pixels)) >= minimum_ratio

    @classmethod
    def _gift_region_difference(cls, before, after):
        x1, y1, x2, y2 = cls.GIFT_ROI
        before_array = numpy.asarray(before)[y1:y2, x1:x2]
        after_array = numpy.asarray(after)[y1:y2, x1:x2]
        if before_array.shape != after_array.shape or before_array.size == 0:
            return float("inf")
        difference = numpy.abs(
            before_array.astype(numpy.int16) - after_array.astype(numpy.int16)
        )
        return float(numpy.mean(difference))

    @staticmethod
    def _capture_image(context: Context):
        return context.tasker.controller.post_screencap().wait().get()

    def _read_selected_count(self, context: Context, image=None):
        if image is None:
            image = self._capture_image(context)
        detail = context.run_recognition("心链送礼新_识别已选礼物数量", image)
        return self._parse_selected_count(detail.all_results if detail else [])

    def _get_blue_candidates(self, context: Context, image):
        detail = context.run_recognition("心链送礼新_识别蓝色礼物", image)
        candidates = self._deduplicate_candidates(detail.all_results if detail else [])
        return [position for position in candidates
                if self._is_blue_candidate(image, position)]

    @staticmethod
    def _click(context: Context, position):
        context.tasker.controller.post_click(*position).wait()
        time.sleep(0.25)

    def _scroll_down(self, context: Context):
        before = self._capture_image(context)
        context.run_task("心链送礼新_向下滚动一步")
        after = self._capture_image(context)
        return self._gift_region_difference(before, after) >= 1.0

    def run(
            self,
            context: Context,
            argv: CustomAction.RunArg,
    ) -> bool:
        del argv
        selected_count = self._read_selected_count(context)
        if selected_count is None:
            self.logger.error("无法识别心链送礼数量，为避免误送已停止")
            return False
        if selected_count >= self.TARGET_COUNT:
            return True

        unchanged_scrolls = 0
        for scroll_index in range(self.MAX_SCROLLS + 1):
            if context.tasker.stopping:
                return False

            image = self._capture_image(context)
            candidates = self._get_blue_candidates(context, image)
            self.logger.debug(
                f"蓝色礼物第{scroll_index + 1}页识别到{len(candidates)}个候选，"
                f"当前已选{selected_count}/10"
            )

            for position in candidates:
                previous_count = selected_count
                self._click(context, position)
                new_count = self._read_selected_count(context)
                if new_count is None:
                    self.logger.error("点击蓝色礼物后无法识别数量，已停止")
                    return False

                if new_count < previous_count:
                    self._click(context, position)
                    restored_count = self._read_selected_count(context)
                    if restored_count != previous_count:
                        self.logger.error("无法还原误点的已选礼物，已停止")
                        return False
                    selected_count = restored_count
                    continue

                selected_count = new_count
                if selected_count >= self.TARGET_COUNT:
                    self.logger.info("已选满10个蓝色礼物")
                    return True

            if scroll_index >= self.MAX_SCROLLS:
                break

            if self._scroll_down(context):
                unchanged_scrolls = 0
            else:
                unchanged_scrolls += 1
                if unchanged_scrolls >= 2:
                    break

        self.logger.warning(f"蓝色礼物不足10个，当前已选{selected_count}/10，不会送出")
        return False
