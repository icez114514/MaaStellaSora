import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

AGENT_DIR = Path(__file__).resolve().parents[1] / "agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from fork_ext.auto_farm_650 import (  # noqa: E402
    AutoFarm650Check,
    AutoFarm650Loop,
    Prefer650EventRecognition,
    Strict650PotentialRecognition,
    choose_strict_650,
)
from custom.reco.climb_tower_quiz import EventRecognition  # noqa: E402


def potential(*, old, new, kind="normal", recommendation=6, recommended=True):
    return SimpleNamespace(
        old_level=old, new_level=new,
        type=kind,
        recommended_level=recommendation, recommended=recommended,
        level_span=new - old,
    )


class StrictPotentialTests(unittest.TestCase):
    def test_new_level_three_beats_upgrade(self):
        upgrade = potential(old=2, new=5)
        fresh = potential(old=0, new=3)
        self.assertIs(choose_strict_650([upgrade, fresh], False), fresh)

    def test_rare_new_level_two_is_accepted(self):
        rare = potential(old=0, new=2, kind="rare")
        self.assertIs(choose_strict_650([rare], False), rare)

    def test_rare_new_level_three_is_accepted(self):
        rare = potential(old=0, new=3, kind="rare")
        self.assertIs(choose_strict_650([rare], False), rare)

    def test_normal_new_level_two_is_rejected(self):
        self.assertIsNone(choose_strict_650([
            potential(old=0, new=2, kind="normal")
        ], False))

    def test_rare_new_level_one_is_rejected(self):
        self.assertIsNone(choose_strict_650([
            potential(old=0, new=1, kind="rare")
        ], False))

    def test_rare_still_requires_target_level_six(self):
        self.assertIsNone(choose_strict_650([
            potential(old=0, new=2, kind="rare", recommendation=5)
        ], False))

    def test_rejects_non_six_recommendations(self):
        self.assertIsNone(choose_strict_650([
            potential(old=0, new=3, recommendation=5),
            potential(old=1, new=3, recommendation=5),
        ], False))

    def test_core_uses_recommended_potential(self):
        first = potential(old=0, new=1, recommendation=1)
        self.assertIs(choose_strict_650([first], True), first)


class FakeContext:
    def __init__(self):
        self.stopped = False
        self.clicked = []
        self.click_success = True
        self.overrides = []
        self.shop_attach = {"target_coin": 1200}
        self.tasker = SimpleNamespace(
            post_stop=lambda: setattr(self, "stopped", True),
            controller=SimpleNamespace(post_click=self._click),
        )

    def _click(self, *position):
        self.clicked.append(position)
        return SimpleNamespace(
            wait=lambda: SimpleNamespace(succeeded=self.click_success)
        )

    def get_node_data(self, _name):
        return {"attach": self.shop_attach}

    def override_pipeline(self, value):
        self.overrides.append(value)
        self.shop_attach.update(
            value.get("星塔_自动刷650_检查金币_agent", {}).get("attach", {})
        )


class PotentialRetryTests(unittest.TestCase):
    def run_potential(self, *, refresh_limit, current_coin, refresh_cost=100):
        context = FakeContext()
        fallback = SimpleNamespace(box=[100, 200, 50, 50])
        data = SimpleNamespace(
            initial_coin=500, current_coin=500,
            refresh_cost=refresh_cost, refreshable=refresh_limit > 0,
            params=SimpleNamespace(reserved_coin=0),
            potentials=[fallback], core_potential=False,
        )
        refreshes = []

        def refresh():
            refreshes.append(True)
            data.current_coin = current_coin
            return True

        handler = SimpleNamespace(
            wait_for_item_list_gone=lambda: None,
            read_potentials_info=lambda: handler,
            choose=lambda: None,
            choose_fallback_potential=lambda: fallback,
            refresh=refresh,
            pick=lambda _potential: True,
            HANDLER_TYPE="preset",
        )
        with (
            patch("fork_ext.auto_farm_650.ChoosePotentialRecognition._get_params"),
            patch("fork_ext.auto_farm_650.Data", return_value=data),
            patch("fork_ext.auto_farm_650.PotentialInteractor") as interactor,
            patch("fork_ext.auto_farm_650.Strict650Handler", return_value=handler),
            patch("fork_ext.auto_farm_650.State") as state,
        ):
            interactor.return_value.get_current_coin.return_value = 500
            interactor.return_value.get_refresh_cost.return_value = refresh_cost
            result = Strict650PotentialRecognition().analyze(
                context, SimpleNamespace(node_name="potential")
            )
        self.assertEqual(result.box, fallback.box)
        self.assertFalse(context.stopped)
        self.assertTrue(context.shop_attach["retry_due_to_potential"])
        self.assertEqual(len(refreshes), refresh_limit)
        state.owned_potentials.save.assert_called_once()
        return context

    def test_refresh_limit_reaches_shop_and_retries(self):
        context = self.run_potential(refresh_limit=0, current_coin=500)
        with patch("fork_ext.auto_farm_650.PotentialInteractor") as interactor:
            result = AutoFarm650Check().run(
                context, SimpleNamespace(node_name="shop")
            )
        self.assertTrue(result)
        self.assertEqual(context.clicked, [(65, 40)])
        interactor.assert_not_called()

    def test_coin_exhausted_after_refresh_reaches_shop(self):
        self.run_potential(refresh_limit=1, current_coin=50)

    def test_next_run_clears_retry_flag(self):
        context = FakeContext()
        context.shop_attach["retry_due_to_potential"] = True
        with patch("fork_ext.auto_farm_650.State") as state:
            self.assertTrue(AutoFarm650Loop().run(
                context, SimpleNamespace(node_name="loop")
            ))
        state.reset.assert_called_once()
        self.assertFalse(context.shop_attach["retry_due_to_potential"])


class ShopDecisionTests(unittest.TestCase):
    def run_at_coin(self, coin):
        context = FakeContext()
        with patch("fork_ext.auto_farm_650.PotentialInteractor") as interactor:
            interactor.return_value.get_current_coin.return_value = coin
            result = AutoFarm650Check().run(context, SimpleNamespace(node_name="shop"))
        return context, result

    def test_ocr_failure_stops_without_abandoning(self):
        context, result = self.run_at_coin(-1)
        self.assertFalse(result)
        self.assertTrue(context.stopped)
        self.assertEqual(context.clicked, [])

    def test_goal_stops_without_abandoning(self):
        context, result = self.run_at_coin(1200)
        self.assertFalse(result)
        self.assertTrue(context.stopped)
        self.assertEqual(context.clicked, [])

    def test_below_goal_abandons(self):
        context, result = self.run_at_coin(1199)
        self.assertTrue(result)
        self.assertFalse(context.stopped)
        self.assertEqual(context.clicked, [(65, 40)])

    def test_failed_return_click_stops(self):
        context = FakeContext()
        context.click_success = False
        with patch("fork_ext.auto_farm_650.PotentialInteractor") as interactor:
            interactor.return_value.get_current_coin.return_value = 1199
            result = AutoFarm650Check().run(context, SimpleNamespace(node_name="shop"))
        self.assertFalse(result)
        self.assertTrue(context.stopped)


class ShopExitPipelineTests(unittest.TestCase):
    def test_abandon_uses_recognized_button_and_returns_to_loop(self):
        root = Path(__file__).resolve().parents[1]
        for locale in ("base", "tw"):
            with self.subTest(locale=locale):
                path = root / "assets/resource/fork" / locale / "pipeline/auto_farm_650.json"
                nodes = json.loads(path.read_text(encoding="utf-8"))
                abandon = nodes["星塔_自动刷650_放弃_agent"]
                self.assertEqual(abandon["action"]["type"], "Click")
                self.assertIs(abandon["action"]["param"]["target"], True)
                self.assertNotIn("星塔_自动刷650_放弃确认_agent", abandon["next"])
                self.assertIn("星塔_回到主页_agent", abandon["next"])


class EventPriorityTests(unittest.TestCase):
    def test_650_rule_moves_ahead_of_normal_answer(self):
        rules = [{"choices": ["normal"]}, {"consequences": ["650"]}]
        context = SimpleNamespace(
            get_node_data=lambda _: {"attach": {"rules": rules}},
            override_pipeline=lambda value: setattr(context, "override", value),
        )
        with patch.object(EventRecognition, "analyze", return_value="chosen"):
            result = Prefer650EventRecognition().analyze(
                context, SimpleNamespace(node_name="event")
            )
        self.assertEqual(result, "chosen")
        self.assertEqual(
            context.override["event"]["attach"]["rules"][0]["consequences"],
            ["650"],
        )


if __name__ == "__main__":
    unittest.main()
