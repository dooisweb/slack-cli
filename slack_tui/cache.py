"""Disk cache for channels, users, and message history."""

import json
import logging
import os
from pathlib import Path

from slack_tui.models import Channel, ChannelType, Message, User

log = logging.getLogger(__name__)


def _cache_dir() -> Path:
    cache_home = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return cache_home / "slack-tui"


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


# --- Channels ---

def save_channels(channels: list[Channel]) -> None:
    d = _cache_dir()
    _ensure_dir(d)
    data = [
        {
            "id": ch.id,
            "name": ch.name,
            "channel_type": ch.channel_type.value,
            "is_member": ch.is_member,
            "user_id": ch.user_id,
            "last_activity": ch.last_activity,
        }
        for ch in channels
    ]
    (d / "channels.json").write_text(json.dumps(data))


def load_channels() -> list[Channel] | None:
    path = _cache_dir() / "channels.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return [
            Channel(
                id=item["id"],
                name=item["name"],
                channel_type=ChannelType(item["channel_type"]),
                is_member=item.get("is_member", False),
                user_id=item.get("user_id"),
                last_activity=item.get("last_activity", 0.0),
            )
            for item in data
        ]
    except Exception:
        log.warning("Failed to load channels cache", exc_info=True)
        return None


# --- Users ---

def save_users(users: dict[str, User]) -> None:
    d = _cache_dir()
    _ensure_dir(d)
    data = {
        uid: {
            "id": u.id,
            "display_name": u.display_name,
            "real_name": u.real_name,
            "is_bot": u.is_bot,
        }
        for uid, u in users.items()
    }
    (d / "users.json").write_text(json.dumps(data))


def load_users() -> dict[str, User] | None:
    path = _cache_dir() / "users.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return {
            uid: User(
                id=item["id"],
                display_name=item["display_name"],
                real_name=item["real_name"],
                is_bot=item.get("is_bot", False),
            )
            for uid, item in data.items()
        }
    except Exception:
        log.warning("Failed to load users cache", exc_info=True)
        return None


# --- Message history ---

def save_history(channel_id: str, messages: list[Message]) -> None:
    d = _cache_dir() / "history"
    _ensure_dir(d)
    data = [
        {
            "ts": m.ts,
            "channel_id": m.channel_id,
            "user_id": m.user_id,
            "user_name": m.user_name,
            "text": m.text,
            "timestamp": m.timestamp,
        }
        for m in messages
    ]
    (d / f"{channel_id}.json").write_text(json.dumps(data))


def load_history(channel_id: str) -> list[Message] | None:
    path = _cache_dir() / "history" / f"{channel_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return [
            Message(
                ts=item["ts"],
                channel_id=item["channel_id"],
                user_id=item["user_id"],
                user_name=item["user_name"],
                text=item["text"],
                timestamp=item["timestamp"],
            )
            for item in data
        ]
    except Exception:
        log.warning("Failed to load history cache for %s", channel_id, exc_info=True)
        return None
