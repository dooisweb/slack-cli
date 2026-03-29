"""Data models for Slack entities."""

from dataclasses import dataclass, field
from enum import Enum


class ChannelType(Enum):
    PUBLIC = "public_channel"
    PRIVATE = "private_channel"
    DM = "im"
    MPDM = "mpim"


@dataclass
class Channel:
    id: str
    name: str
    channel_type: ChannelType
    is_member: bool = False
    user_id: str | None = None  # For DMs: the other user's ID
    last_activity: float = 0.0  # Unix timestamp of last activity


@dataclass
class User:
    id: str
    display_name: str
    real_name: str
    is_bot: bool = False


@dataclass
class FileAttachment:
    id: str
    name: str
    mimetype: str
    size: int  # bytes
    url_private: str  # requires auth to download


@dataclass
class SearchResult:
    channel_id: str
    channel_name: str
    user_name: str
    text: str
    timestamp: float
    permalink: str


@dataclass
class Message:
    ts: str  # Slack timestamp (unique message ID)
    channel_id: str
    user_id: str
    user_name: str  # Resolved display name
    text: str
    timestamp: float  # Unix timestamp for display formatting
    files: list[FileAttachment] = field(default_factory=list)
    thread_ts: str | None = None  # Parent message ts — if set, this is a thread reply
    reply_count: int = 0  # Number of thread replies
