"""Auth screen — token entry modal shown when no config exists."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label

from slack_tui.config import SlackConfig


class AuthScreen(ModalScreen[SlackConfig | None]):
    """Modal screen for entering Slack tokens."""

    def compose(self) -> ComposeResult:
        with Vertical(id="auth-dialog"):
            yield Label("Slack TUI Setup", classes="auth-title")
            yield Label("Bot Token (xoxb-... or xoxp-...):")
            yield Input(id="bot-token", placeholder="xoxb-...", password=True)
            yield Label("App-Level Token (xapp-...):")
            yield Input(id="app-token", placeholder="xapp-...", password=True)
            with Horizontal(id="auth-buttons"):
                yield Button("Save", id="save", variant="primary")
                yield Button("Cancel", id="cancel", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            bot = self.query_one("#bot-token", Input).value.strip()
            app_tok = self.query_one("#app-token", Input).value.strip()
            if not bot or not app_tok:
                self.notify("Both tokens are required", severity="error")
                return
            if not (bot.startswith("xoxb-") or bot.startswith("xoxp-")):
                self.notify(
                    "Bot token must start with xoxb- or xoxp-",
                    severity="error",
                )
                return
            if not app_tok.startswith("xapp-"):
                self.notify(
                    "App token must start with xapp-",
                    severity="error",
                )
                return
            self.dismiss(SlackConfig(bot_token=bot, app_token=app_tok))
        elif event.button.id == "cancel":
            self.dismiss(None)
