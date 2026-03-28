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
    """Load tokens from config file. Returns None if missing or invalid."""
    path = _config_path()
    if not path.exists():
        return None

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)

        tokens = data.get("tokens", {})
        bot_token = tokens.get("bot_token", "")
        app_token = tokens.get("app_token", "")

        if not bot_token or not app_token:
            return None
        if not (bot_token.startswith("xoxb-") or bot_token.startswith("xoxp-")):
            return None
        if not app_token.startswith("xapp-"):
            return None

        return SlackConfig(bot_token=bot_token, app_token=app_token)
    except Exception:
        return None


def save_config(config: SlackConfig) -> None:
    """Save tokens to config file with restricted permissions."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    content = f'[tokens]\nbot_token = "{config.bot_token}"\napp_token = "{config.app_token}"\n'

    path.write_text(content)
    os.chmod(path, 0o600)
