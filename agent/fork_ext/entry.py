"""Register fork extensions before starting the upstream agent."""

import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

import main as upstream_main  # noqa: E402
from fork_ext import auto_farm_650, heartlink  # noqa: E402,F401
from fork_ext.window_aspect import start_auto_resize  # noqa: E402


def main() -> None:
    resize = start_auto_resize()
    try:
        upstream_main.main()
    finally:
        resize.stop()


if __name__ == "__main__":
    main()
