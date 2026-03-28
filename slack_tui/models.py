"""Data models for Slack entities."""

from dataclasses import dataclass
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
class Message:
    ts: str  # Slack timestamp (unique message ID)
    channel_id: str
    user_id: str
    user_name: str  # Resolved display name
    text: str
    timestamp: float  # Unix timestamp for display formatting
