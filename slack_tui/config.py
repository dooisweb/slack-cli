"""Configuration management — load/save Slack tokens from TOML."""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SlackConfig:
    bot_token: str  # xoxb-... or xoxp-...
    app_token: str  # xapp-...


def _config_path() -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "slack-tui" / "config.toml"


def load_config() -> SlackConfig | None:
    """Load tokens from config file or environment variables.

    Environment variables (SLACK_BOT_TOKEN, SLACK_APP_TOKEN) take precedence
    over the config file.  Returns None if no valid tokens are found.
    """
    bot_token = os.environ.get("SLACK_BOT_TOKEN", "")
    app_token = os.environ.get("SLACK_APP_TOKEN", "")

    if not (bot_token and app_token):
        path = _config_path()
        if not path.exists():
            return None
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
            tokens = data.get("tokens", {})
            bot_token = bot_token or tokens.get("bot_token", "")
            app_token = app_token or tokens.get("app_token", "")
        except Exception:
            return None

    if not bot_token or not app_token:
        return None
    if not (bot_token.startswith("xoxb-") or bot_token.startswith("xoxp-")):
        return None
    if not app_token.startswith("xapp-"):
        return None

    return SlackConfig(bot_token=bot_token, app_token=app_token)


def save_config(config: SlackConfig) -> None:
    """Save tokens to config file with restricted permissions."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    content = f'[tokens]\nbot_token = "{config.bot_token}"\napp_token = "{config.app_token}"\n'

    # Write with owner-only permissions from creation (avoids race window
    # where file exists momentarily with default umask permissions)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, content.encode())
    finally:
        os.close(fd)
