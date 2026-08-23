import difflib
import re
import time

import numpy
from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
from utils import logger

@AgentServer.custom_action("InviteAuto")
class InviteAuto(CustomAction):
    def __init__(self):
        # 导入logger
        super().__init__()
        self.logger = logger.get_logger()

    def run(
            self,
            context: Context,
            argv: CustomAction.RunArg,
    ) -> bool:
        """
            邀约功能总控制节点
        """

        # 邀约对象的任务列表
        invite_nodes = ["邀约_1号", "邀约_2号", "邀约_3号", "邀约_4号", "邀约_5号"]

        for node in invite_nodes:
            # 检查邀约对象是否达到上限
            image = context.tasker.controller.post_screencap().wait().get()
            reco_detail = context.run_recognition("邀约_达上限", image)
            if reco_detail and reco_detail.hit:
                self.logger.info(f"邀约次数已达到本日上限")
                return True

            trekker_name, choose_gift = self._get_trekker_info(context, node)
            if not trekker_name or trekker_name in ("x", "X"):
                self.logger.debug(f"节点'{node}'的邀约对象为空，跳过")
                continue

            # 标记是否需要手动重置位置
            need_reset = False
            # 执行邀约流程
            while not context.tasker.stopping:
                if self._click_trekker(context, trekker_name):
                    # 成功点击邀约对象后，按照choose_gift情况获取送礼流程，然后尝试执行邀约
                    pipeline_override = self._get_choose_gift_pipeline(choose_gift)
                    res = context.run_task("邀约_开始邀约", pipeline_override)

                    # 成功识别到邀约按钮时，不需要手动重置位置
                    if res and res.status.succeeded:
                        need_reset = False

                    break # 无论任务结果如何，只要点到了人，就停止向下翻页

                # 没找到则滑向下一页，若已到底部则放弃寻找
                is_bottom = self._scroll_to_next_page(context)
                if is_bottom:
                    break
                else:
                    need_reset = True

            # 邀约流程完成后，如果需要手动重置位置，则滚动到顶部
            if need_reset:
                self._scroll_to_top(context)

            # 检测任务中止的情况，防止卡死，检测成功时结束函数
            if context.tasker.stopping:
                return False
        # 返回True，执行后续的“通用_返回主页”节点
        return True

    def _get_trekker_info(self, context: Context, node) -> tuple[str, str]:
        """
            获取邀约对象名字及送礼选项

            Args:
                context: maa.context.Context
                node: string，需要提取内容的节点名称

            Returns:
                str: 邀约对象名字
                str: 送礼选项
        """
        trekker_info = context.get_node_data(node)

        try:
            trekker_name = trekker_info['recognition']['param']['expected'][0]
            trekker_name = trekker_name.strip()
            choose_gift = trekker_info['attach']['gift']
        except (TypeError, KeyError, IndexError, AttributeError) as e:
            self.logger.warning(f"提取节点'{node}'的文本过程中出现问题: {e}")
            trekker_name = ""
            choose_gift = ""

        return trekker_name, choose_gift

    def _click_trekker(
            self,
            context: Context,
            trekker_name: str
    ) -> bool:
        """
            识别并点击邀约对象

            Args:
                context: maa.context.Context
                trekker_name: 旅人名字

            Returns:
                bool: 选择到目标对象时返回True，未能选择到目标对象时返回False
        """
        # 参数
        similarity_limit = 0.8 # 文本相似度阈值

        # 处理旅人名字的文本问题，把全角括号都换成半角括号，把空格都取消
        translate_table = str.maketrans({
            '（': '(',
            '）': ')',
            ' ': None,
            '　': None
        })
        formatted_name = trekker_name.translate(translate_table)

        # 识别对象
        image = context.tasker.controller.post_screencap().wait().get()
        reco_detail = context.run_recognition("邀约_左方识别邀约对象", image)

        # 整理识别结果
        results = self._get_refined_merge(reco_detail.all_results)
        self.logger.debug(f"识别出{len(results)}个结果，开始比较")

        # 比较文本相似程度，如果相似程度高，则点击，并返回True，否则返回False
        for result in results:
            # 使用difflib库计算文本相似度
            formatted_result = result['text'].translate(translate_table)
            similarity = difflib.SequenceMatcher(None, formatted_result, formatted_name).ratio()

            if similarity >= similarity_limit:
                self.logger.debug(f"识别成功！预期: {formatted_name}, 识别结果: {formatted_result}, 相似度: {similarity:.2f}")
                context.tasker.controller.post_click(result['x'], result['y']).wait()
                self.logger.debug(f"点击坐标{result['x']},{result['y']}完成")
                return True
            self.logger.debug(f"识别失败！预期: {formatted_name}, 识别结果: {formatted_result}, 相似度: {similarity:.2f}")
        return False

    @staticmethod
    def _get_refined_merge(results, threshold = 0.7, y_tolerance = 30, x_tolerance = 50):
        """
            处理OCR识别结果，将符合条件的文本块进行合并，并计算最终的点击位置。

            Args:
                results (list): ocr检测结果的列表，每个元素应有 text 和 score 和 box 属性。
                threshold (float): 识别分数阈值，用于过滤识别分数过低的结果
                x_tolerance (int): X 轴方向允许的最大距离，用于判断两个文本框是否属于同一格。
                y_tolerance (int): Y 轴方向允许的最大距离，用于判断当前文本框是否属于同一格。

            Returns:
                list: 合并后的文本及其对应点击坐标的字典列表，每个字典包含 'text'、'x' 和 'y' 键。
        """

        # 排除掉没有识别结果的情况
        if not results:
            return []

        # 过滤掉低于识别阈值的结果，或以P开头的乱码结果
        results = [r for r in results if r.score >= threshold
                   and not (r.text.startswith('P') and not r.text.isascii())
                   and r.text != 'P' and r.text != 'PI']
        # 按 Y 坐标排序，确保从上往下处理
        results.sort(key=lambda r: r.box[1])

        merged_list = []
        for item in results:
            x, y, w, h = item.box
            cx, cy = x + w // 2, y + h // 2

            found = False
            for m in merged_list:
                # 逻辑：X轴距离在格子范围内，且当前块顶部靠近上一个块的底部
                if abs(m['x_ref'] - x) <= x_tolerance and abs(y - m['y_end']) <= y_tolerance:
                    m['text'] += item.text
                    # 简单合并坐标并取整
                    m['x'] = (m['x'] + cx) // 2
                    m['y'] = (m['y'] + cy) // 2
                    m['y_end'] = y + h  # 更新底部边界供下一次合并参考
                    found = True
                    break

            if not found:
                # 没能合并时，创建为新的元素
                merged_list.append({
                    'text': item.text,
                    'x': cx,
                    'y': cy,
                    'x_ref': x,  # 辅助字段：记录起始X
                    'y_end': y + h  # 辅助字段：记录当前底部Y
                })

        # 返回前可以清理掉辅助字段，只保留要的三个键
        return [{'text': i['text'], 'x': i['x'], 'y': i['y']} for i in merged_list]

    def _scroll_to_next_page(self, context: Context, image=None):
        """
            向下滑动到下一页

            Args:
                context: maa.context.Context

            Returns:
                bool: 已滑到底部或无法判断是否划到底部时，返回True；未滑到底部时，返回False
        """
        if not image:
            image = context.tasker.controller.post_screencap().wait().get()

        if not context.override_image("invite_scroll_down_template", image):
            self.logger.error("截图错误，将无法判断是否滑动到底部")
            return True

        context.run_task("邀约_向下滑动")

        image = context.tasker.controller.post_screencap().wait().get()
        reco_result = context.run_recognition("邀约_已滑动到底部", image)
        if reco_result and len(reco_result.all_results) > 0:
            self.logger.debug(f"向下滑动识别分数：{reco_result.all_results[0].score}")
        if reco_result and reco_result.hit:
            self.logger.debug(f"已滑动到底部")
            return True
        else:
            self.logger.debug(f"未滑动到底部")
            return False

    def _scroll_to_top(self, context: Context):
        """
            向上滑动到顶部

            Args:
                context: maa.context.Context

            Returns:
                bool:
                    已滑到顶部时，返回True；
                    未滑到顶部，无法判断是否滑到顶部，又或者任务被中止时，返回False
        """
        image = context.tasker.controller.post_screencap().wait().get()
        while True:
            if not context.override_image("invite_scroll_up_template", image):
                self.logger.error("截图错误，将无法判断是否滑动到顶部")
                return False

            context.run_task("邀约_向上滑动")

            image = context.tasker.controller.post_screencap().wait().get()
            reco_result = context.run_recognition("邀约_已滑动到顶部", image)
            if reco_result and len(reco_result.all_results) > 0:
                self.logger.debug(f"向上滑动识别分数：{reco_result.all_results[0].score}")
            if reco_result and reco_result.hit:
                self.logger.debug(f"已滑动到顶部")
                return True

            # 检测任务中止的情况，防止卡死，检测成功时返回False
            if context.tasker.stopping:
                return False

    def _get_choose_gift_pipeline(self, choose_gift: str) -> dict:
        """
            根据choose_gift修改送礼流程
            pipeline默认是送最好的礼物

            Args:
                choose_gift: 送礼选项，只有"all"、"favorite"、"no"三种

            Returns:
                dict: 重置的pipeline配置
        """
        if choose_gift == "favorite":
            pipeline_override = {}
        elif choose_gift == "all":
            pipeline_override = {
                "邀约_选择礼物":{
                    "recognition":{
                        "param":{
                            "template":[
                                "Invite/邀约_喜好图标.png",
                                "Invite/邀约_喜好图标2.png",
                                "Invite/邀约_喜好图标3.png"
                            ]
                        }
                    }
                }
            }
        elif choose_gift == "no":
            pipeline_override = {
                "邀约_送礼流程": {
                    "next": [
                        "邀约_还是算了"
                    ]
                }
            }
        else:
            self.logger.error(f"未知的送礼选项：{choose_gift}，将默认只送黄色笑脸")
            return {}
        return pipeline_override


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
