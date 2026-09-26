"""Auto-farm the first tower shop without changing upstream handlers."""

from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction
from maa.custom_recognition import CustomRecognition

from custom.reco.climb_tower_potential.data import Data, Potential
from custom.reco.climb_tower_potential.handler_preset import RecommendationHandler
from custom.reco.climb_tower_potential.interactor import PotentialInteractor
from custom.reco.climb_tower_potential.main import ChoosePotentialRecognition
from custom.reco.climb_tower_potential.state import State
from custom.reco.climb_tower_quiz import EventRecognition
from utils import logger as logger_module

logger = logger_module.get_logger("fork_auto_farm_650")
SHOP_CHECK_NODE = "星塔_自动刷650_检查金币_agent"


def choose_strict_650(potentials: list[Potential], core: bool) -> Potential | None:
    """Apply the fork's strict level-six recommendation policy."""
    if core:
        return next((p for p in potentials if p.recommended), None)

    new = [
        p for p in potentials
        if p.recommended and p.recommended_level == 6
        and p.old_level == 0
        and (
            (p.type == "normal" and p.new_level == 3)
            or (p.type == "rare" and p.new_level in (2, 3))
        )
    ]
    if new:
        return max(new, key=lambda p: (p.new_level, p.level_span))

    upgrades = [
        p for p in potentials
        if p.recommended and p.recommended_level == 6
        and 0 < p.old_level < 6 and p.new_level > p.old_level
        and p.new_level >= 3
    ]
    return max(
        upgrades,
        key=lambda p: (p.level_span, p.new_level, p.old_level),
        default=None,
    )


class Strict650Handler(RecommendationHandler):
    def choose(self) -> Potential | None:
        return choose_strict_650(self.data.potentials, self.data.core_potential)


@AgentServer.custom_recognition("fork_choose_potential_650")
class Strict650PotentialRecognition(CustomRecognition):
    def analyze(
        self, context: Context, argv: CustomRecognition.AnalyzeArg,
    ) -> CustomRecognition.AnalyzeResult:
        params = ChoosePotentialRecognition._get_params(context, argv.node_name)
        data = Data(params=params)
        screen = PotentialInteractor(context)
        data.initial_coin = screen.get_current_coin()
        data.current_coin = data.initial_coin
        data.refresh_cost = screen.get_refresh_cost()
        data.core_potential = screen.check_core_potential()
        data.potential_types = screen.get_potential_types(data.core_potential)

        handler = Strict650Handler(screen, data)
        handler.wait_for_item_list_gone()
        while True:
            potential = handler.read_potentials_info().choose()
            if potential is not None:
                break
            can_afford_refresh = (
                data.refresh_cost >= 0
                and data.current_coin >= data.refresh_cost + data.params.reserved_coin
            )
            if not data.refreshable or not can_afford_refresh:
                if data.initial_coin < 0 or data.refresh_cost < 0:
                    logger.error("Potential refresh data unavailable; stopping safely")
                    context.tasker.post_stop()
                    return CustomRecognition.AnalyzeResult(box=None, detail={})
                if not data.potentials:
                    logger.error("No potential card recognized; stopping safely")
                    context.tasker.post_stop()
                    return CustomRecognition.AnalyzeResult(box=None, detail={})
                potential = handler.choose_fallback_potential()
                logger.info("No qualifying potential or refresh remaining; retry after first shop")
                context.override_pipeline({
                    SHOP_CHECK_NODE: {"attach": {"retry_due_to_potential": True}}
                })
                break
            if not handler.refresh():
                logger.error("Potential refresh failed; stopping safely")
                context.tasker.post_stop()
                return CustomRecognition.AnalyzeResult(box=None, detail={})

        if not handler.pick(potential):
            logger.error("Potential click failed; stopping safely")
            context.tasker.post_stop()
            return CustomRecognition.AnalyzeResult(box=None, detail={})
        State.owned_potentials.save(potential, handler=handler.HANDLER_TYPE)
        return CustomRecognition.AnalyzeResult(box=potential.box, detail={})


@AgentServer.custom_recognition("fork_event_650_first")
class Prefer650EventRecognition(EventRecognition):
    def analyze(
        self, context: Context, argv: CustomRecognition.AnalyzeArg,
    ) -> CustomRecognition.AnalyzeResult:
        node = context.get_node_data(argv.node_name) or {}
        rules = node.get("attach", {}).get("rules", [])
        preferred = [r for r in rules if "650" in str(r.get("consequences", []))]
        if preferred:
            others = [r for r in rules if r not in preferred]
            context.override_pipeline({
                argv.node_name: {"attach": {"rules": preferred + others}}
            })
        return super().analyze(context, argv)


@AgentServer.custom_action("fork_auto_farm_650_check")
class AutoFarm650Check(CustomAction):
    RETURN_BUTTON = (65, 40)

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        node = context.get_node_data(argv.node_name) or {}
        attach = node.get("attach", {})
        if attach.get("retry_due_to_potential"):
            logger.info("Potential target missed; leaving at first shop for next run")
        else:
            target = int(attach.get("target_coin", 1200))
            coin = PotentialInteractor(context).get_current_coin()
            if coin < 0:
                logger.error("Coin OCR failed; stopping without abandoning")
                context.tasker.post_stop()
                return False
            if coin >= target:
                logger.info(f"Auto-farm target reached: {coin}/{target}")
                context.tasker.post_stop()
                return False
            logger.info(f"Auto-farm retry: {coin}/{target}")
        clicked = context.tasker.controller.post_click(*self.RETURN_BUTTON).wait()
        if not clicked.succeeded:
            logger.error("Return click failed; stopping safely")
            context.tasker.post_stop()
            return False
        return True


@AgentServer.custom_action("fork_auto_farm_650_loop")
class AutoFarm650Loop(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        State.reset()
        context.override_pipeline({
            SHOP_CHECK_NODE: {"attach": {"retry_due_to_potential": False}}
        })
        return True
