"""Disk cache for channels, users, and message history."""

import json
import logging
import os
import re
from pathlib import Path

from slack_tui.models import Channel, ChannelType, FileAttachment, Message, User

log = logging.getLogger(__name__)

# Slack IDs are alphanumeric (e.g. C01234ABCDE, U01234ABCDE)
_SAFE_ID_RE = re.compile(r'^[A-Za-z0-9_-]+$')


def _write_private(path: Path, content: str) -> None:
    """Atomically write content to a file readable only by the owner (mode 0600).

    Writes to a temp file first, then renames to avoid corruption if the
    process is killed mid-write.
    """
    import tempfile
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        os.write(tmp_fd, content.encode())
        os.close(tmp_fd)
        tmp_fd = -1  # mark as closed
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, str(path))  # atomic on POSIX
    except BaseException:
        if tmp_fd >= 0:
            os.close(tmp_fd)
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _validate_id(identifier: str) -> str:
    """Validate that an identifier is safe for use as a filename component."""
    if not _SAFE_ID_RE.match(identifier):
        raise ValueError(f"Invalid identifier for cache path: {identifier!r}")
    return identifier


def _cache_dir() -> Path:
    cache_home = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return cache_home / "slack-tui"


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)


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
    _write_private(d / "channels.json", json.dumps(data))


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
    _write_private(d / "users.json", json.dumps(data))


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
    _validate_id(channel_id)
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
            "files": [
                {
                    "id": f.id,
                    "name": f.name,
                    "mimetype": f.mimetype,
                    "size": f.size,
                    "url_private": f.url_private,
                }
                for f in m.files
            ],
            "thread_ts": m.thread_ts,
            "reply_count": m.reply_count,
        }
        for m in messages
    ]
    _write_private(d / f"{channel_id}.json", json.dumps(data))


def load_history(channel_id: str) -> list[Message] | None:
    _validate_id(channel_id)
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
                files=[
                    FileAttachment(
                        id=f["id"],
                        name=f["name"],
                        mimetype=f["mimetype"],
                        size=f["size"],
                        url_private=f["url_private"],
                    )
                    for f in item.get("files", [])
                ],
                thread_ts=item.get("thread_ts"),
                reply_count=item.get("reply_count", 0),
            )
            for item in data
        ]
    except Exception:
        log.warning("Failed to load history cache for %s", channel_id, exc_info=True)
        return None
