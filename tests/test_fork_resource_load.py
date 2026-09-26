import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ForkResourceLoadTests(unittest.TestCase):
    def test_all_locales_load_with_fork_overlay(self):
        # Maa AgentServer replaces the process-wide MaaFramework library handle.
        # Load resources in a fresh process so this test can run with agent tests.
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(ROOT / "tools/check_fork_resources_runtime.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertEqual(result.returncode, 0, (result.stdout + result.stderr)[-3000:])


if __name__ == "__main__":
    unittest.main()
