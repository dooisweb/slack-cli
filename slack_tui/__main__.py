"""Entry point for running slack_tui as a module: python -m slack_tui"""

import logging

from slack_tui.app import SlackTuiApp

LOG_FILE = "/tmp/slack-tui.log"


def main() -> None:
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = SlackTuiApp()
    app.run()


if __name__ == "__main__":
    main()
