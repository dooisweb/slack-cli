"""Entry point for running slack_tui as a module: python -m slack_tui"""

import logging
import os
from pathlib import Path

from slack_tui.app import SlackTuiApp


def _log_path() -> str:
    cache_home = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    log_dir = cache_home / "slack-tui"
    log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_file = log_dir / "slack-tui.log"
    # Create log file with owner-only permissions if it doesn't exist
    if not log_file.exists():
        fd = os.open(str(log_file), os.O_WRONLY | os.O_CREAT, 0o600)
        os.close(fd)
    return str(log_file)


def main() -> None:
    level_name = os.environ.get("SLACK_TUI_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    logging.basicConfig(
        filename=_log_path(),
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = SlackTuiApp()
    app.run()


if __name__ == "__main__":
    main()
