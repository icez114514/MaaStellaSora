import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


AGENT_DIR = Path(__file__).resolve().parents[1] / "agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from utils.window_aspect import (  # noqa: E402
    ENV_ENABLED,
    _run_resize_attempts,
    choose_target_resolution,
    has_supported_client_size,
    load_policy,
)


class ResolutionPolicyTests(unittest.TestCase):
    def test_existing_16_by_9_resolution_is_supported(self):
        self.assertTrue(
            has_supported_client_size((2560, 1440), (16, 9), (1920, 1080))
        )

    def test_non_16_by_9_resolution_requires_resize(self):
        self.assertFalse(
            has_supported_client_size((3440, 1440), (16, 9), (1920, 1080))
        )

    def test_too_small_16_by_9_resolution_requires_resize(self):
        self.assertFalse(
            has_supported_client_size((1280, 720), (16, 9), (1920, 1080))
        )

    def test_selects_first_candidate_that_fits_with_window_frame(self):
        target = choose_target_resolution(
            ((3840, 2160), (2560, 1440), (1920, 1080)),
            work_area=(3840, 1600),
            non_client_size=(16, 39),
        )
        self.assertEqual(target, (2560, 1440))

    def test_returns_none_when_no_candidate_fits(self):
        target = choose_target_resolution(
            ((1920, 1080),),
            work_area=(1600, 900),
            non_client_size=(16, 39),
        )
        self.assertIsNone(target)

    def test_retries_after_fullscreen_toggle_when_unity_rejects_first_resize(self):
        attempts = iter(
            (
                ((2560, 1440), (3400, 1400)),
                ((2560, 1440), (2560, 1440)),
            )
        )
        toggles = []

        target, actual, used_fallback = _run_resize_attempts(
            resize_once=lambda: next(attempts),
            toggle_fullscreen=lambda: toggles.append(True),
            allow_fullscreen_toggle=True,
        )

        self.assertEqual(target, (2560, 1440))
        self.assertEqual(actual, (2560, 1440))
        self.assertTrue(used_fallback)
        self.assertEqual(toggles, [True])


class ConfigurationTests(unittest.TestCase):
    def test_environment_can_disable_resize(self):
        raw = {
            "enabled": True,
            "ratio": [16, 9],
            "min_size": [1920, 1080],
            "resize_to": [[2560, 1440], [1920, 1080]],
            "poll_interval_seconds": 2,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "window_aspect.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with patch.dict(os.environ, {ENV_ENABLED: "false"}):
                policy = load_policy(path)
        self.assertFalse(policy.enabled)
        self.assertEqual(policy.resize_to[0], (2560, 1440))
        self.assertEqual(policy.restore_to, (5120, 2160))

    def test_restore_target_configuration_is_loaded(self):
        raw = {
            "enabled": True,
            "ratio": [16, 9],
            "min_size": [1920, 1080],
            "resize_to": [[2560, 1440]],
            "restore_to": [5120, 2160],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "window_aspect.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            policy = load_policy(path)

        self.assertEqual(policy.restore_to, (5120, 2160))


if __name__ == "__main__":
    unittest.main()
