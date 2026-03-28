"""Async Slack API wrapper for channels, messages, and users."""

import logging

from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from slack_tui.models import Channel, ChannelType, Message, User
from slack_tui import cache as disk_cache


class SlackClient:
    def __init__(self, bot_token: str) -> None:
        self.web_client = AsyncWebClient(token=bot_token)
        self._user_cache: dict[str, User] = {}
        # Seed from disk cache
        cached_users = disk_cache.load_users()
        if cached_users:
            self._user_cache = cached_users

    async def fetch_channels(self) -> list[Channel]:
        """Fetch all channels/DMs the user is a member of, with pagination."""
        channels: list[Channel] = []
        cursor = None
        types = "public_channel,private_channel,im,mpim"

        while True:
            kwargs: dict = {"types": types, "limit": 200, "exclude_archived": True}
            if cursor:
                kwargs["cursor"] = cursor

            response = await self.web_client.conversations_list(**kwargs)
            for conv in response.get("channels", []):
                ch = Channel(
                    id=conv["id"],
                    name=conv.get("name", conv["id"]),
                    channel_type=ChannelType(self._resolve_channel_type(conv)),
                    is_member=conv.get("is_member", False),
                    user_id=conv.get("user"),
                )
                channels.append(ch)

            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        return channels

    def _resolve_channel_type(self, conv: dict) -> str:
        if conv.get("is_im"):
            return ChannelType.DM.value
        if conv.get("is_mpim"):
            return ChannelType.MPDM.value
        if conv.get("is_private"):
            return ChannelType.PRIVATE.value
        return ChannelType.PUBLIC.value

    async def fetch_history(self, channel_id: str, limit: int = 50) -> list[Message]:
        """Fetch recent messages for a channel, oldest first."""
        response = await self.web_client.conversations_history(
            channel=channel_id, limit=limit
        )
        messages: list[Message] = []
        for msg in response.get("messages", []):
            if msg.get("subtype") and msg["subtype"] not in ("bot_message",):
                continue
            user_id = msg.get("user", msg.get("bot_id", "unknown"))
            user_name = await self.get_user_name(user_id)
            ts = msg["ts"]
            messages.append(
                Message(
                    ts=ts,
                    channel_id=channel_id,
                    user_id=user_id,
                    user_name=user_name,
                    text=msg.get("text", ""),
                    timestamp=float(ts.split(".")[0]),
                )
            )

        messages.reverse()  # API returns newest first; we want oldest first
        return messages

    async def fetch_new_messages(self, channel_id: str, oldest_ts: str) -> list[Message]:
        """Fetch messages newer than oldest_ts, oldest first."""
        response = await self.web_client.conversations_history(
            channel=channel_id, oldest=oldest_ts, inclusive=False, limit=100
        )
        messages: list[Message] = []
        for msg in response.get("messages", []):
            if msg.get("subtype") and msg["subtype"] not in ("bot_message",):
                continue
            user_id = msg.get("user", msg.get("bot_id", "unknown"))
            user_name = await self.get_user_name(user_id)
            ts = msg["ts"]
            messages.append(
                Message(
                    ts=ts,
                    channel_id=channel_id,
                    user_id=user_id,
                    user_name=user_name,
                    text=msg.get("text", ""),
                    timestamp=float(ts.split(".")[0]),
                )
            )
        messages.reverse()
        return messages

    async def send_message(self, channel_id: str, text: str) -> tuple[bool, str]:
        """Send a message. Returns (success, error_message)."""
        try:
            await self.web_client.chat_postMessage(channel=channel_id, text=text)
            return True, ""
        except SlackApiError as e:
            error = e.response["error"]
            logging.getLogger(__name__).error("send_message failed: %s", error)
            return False, error

    async def get_user_name(self, user_id: str) -> str:
        """Look up user display name, with in-memory cache."""
        if user_id in self._user_cache:
            return self._user_cache[user_id].display_name

        try:
            response = await self.web_client.users_info(user=user_id)
            user_data = response["user"]
            profile = user_data.get("profile", {})
            display_name = (
                profile.get("display_name")
                or profile.get("real_name")
                or user_data.get("real_name")
                or user_data.get("name")
                or user_id
            )
            user = User(
                id=user_id,
                display_name=display_name,
                real_name=user_data.get("real_name", display_name),
                is_bot=user_data.get("is_bot", False),
            )
            self._user_cache[user_id] = user
            return display_name
        except SlackApiError:
            return user_id

    def save_user_cache(self) -> None:
        """Persist the in-memory user cache to disk."""
        disk_cache.save_users(self._user_cache)

    async def get_own_user_id(self) -> str:
        """Get the authenticated user's own ID via auth.test."""
        response = await self.web_client.auth_test()
        return response["user_id"]

    async def fetch_last_message_ts(self, channel_id: str) -> float:
        """Fetch the timestamp of the most recent message in a channel."""
        try:
            response = await self.web_client.conversations_history(
                channel=channel_id, limit=1
            )
            messages = response.get("messages", [])
            if messages:
                return float(messages[0]["ts"])
        except SlackApiError:
            pass
        return 0.0

    async def resolve_dm_name(self, channel: Channel) -> str:
        """For DM channels, resolve the other user's display name."""
        if channel.user_id:
            return await self.get_user_name(channel.user_id)
        return channel.name

    async def resolve_mpdm_name(self, channel: Channel, own_user_id: str) -> str:
        """For MPDM channels, resolve member names excluding self."""
        try:
            response = await self.web_client.conversations_members(channel=channel.id)
            member_ids = response.get("members", [])
            names = []
            for uid in member_ids:
                if uid == own_user_id:
                    continue
                name = await self.get_user_name(uid)
                names.append(name)
            return ", ".join(names) if names else channel.name
        except SlackApiError:
            return channel.name
