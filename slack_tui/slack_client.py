"""Async Slack API wrapper for channels, messages, and users."""

import asyncio
import logging

from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

log = logging.getLogger(__name__)

from slack_tui.models import Channel, ChannelType, FileAttachment, Message, SearchResult, User
from slack_tui import cache as disk_cache


async def _rate_limit_retry(coro_fn, max_retries: int = 2):
    """Call an async function, retrying on rate limit (429) errors."""
    for attempt in range(max_retries + 1):
        try:
            return await coro_fn()
        except SlackApiError as e:
            if e.response.status_code == 429 and attempt < max_retries:
                retry_after = int(e.response.headers.get("Retry-After", 5))
                log.warning("Rate limited, retrying in %ds", retry_after)
                await asyncio.sleep(retry_after)
            else:
                raise


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

            response = await _rate_limit_retry(
                lambda kw=dict(kwargs): self.web_client.conversations_list(**kw)
            )
            for conv in response.get("channels", []):
                # updated is in milliseconds; convert to seconds
                updated = float(conv.get("updated", 0))
                if updated > 1e12:
                    updated = updated / 1000.0
                ch = Channel(
                    id=conv["id"],
                    name=conv.get("name", conv["id"]),
                    channel_type=ChannelType(self._resolve_channel_type(conv)),
                    is_member=conv.get("is_member", False),
                    user_id=conv.get("user"),
                    last_activity=updated,
                )
                channels.append(ch)

            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        return channels

    @staticmethod
    def _parse_image_files(msg: dict) -> list[FileAttachment]:
        """Extract image file attachments from a Slack message."""
        files = []
        for f in msg.get("files", []):
            mime = f.get("mimetype", "")
            if mime.startswith("image/"):
                files.append(FileAttachment(
                    id=f["id"],
                    name=f.get("name", "image"),
                    mimetype=mime,
                    size=f.get("size", 0),
                    url_private=f.get("url_private_download", f.get("url_private", "")),
                ))
        return files

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
        response = await _rate_limit_retry(
            lambda: self.web_client.conversations_history(channel=channel_id, limit=limit)
        )
        messages: list[Message] = []
        for msg in response.get("messages", []):
            if msg.get("subtype") and msg["subtype"] not in ("bot_message", "file_share"):
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
                    files=self._parse_image_files(msg),
                    thread_ts=msg.get("thread_ts") if msg.get("thread_ts") != ts else None,
                    reply_count=msg.get("reply_count", 0),
                )
            )

        messages.reverse()  # API returns newest first; we want oldest first
        return messages

    async def fetch_new_messages(self, channel_id: str, oldest_ts: str) -> list[Message]:
        """Fetch messages newer than oldest_ts, oldest first."""
        response = await _rate_limit_retry(
            lambda: self.web_client.conversations_history(
                channel=channel_id, oldest=oldest_ts, inclusive=False, limit=100
            )
        )
        messages: list[Message] = []
        for msg in response.get("messages", []):
            if msg.get("subtype") and msg["subtype"] not in ("bot_message", "file_share"):
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
                    files=self._parse_image_files(msg),
                    thread_ts=msg.get("thread_ts") if msg.get("thread_ts") != ts else None,
                    reply_count=msg.get("reply_count", 0),
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

    async def fetch_thread(self, channel_id: str, thread_ts: str) -> list[Message]:
        """Fetch all replies in a thread, oldest first."""
        response = await _rate_limit_retry(
            lambda: self.web_client.conversations_replies(
                channel=channel_id, ts=thread_ts, limit=200
            )
        )
        messages: list[Message] = []
        for msg in response.get("messages", []):
            if msg.get("subtype") and msg["subtype"] not in ("bot_message", "file_share"):
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
                    files=self._parse_image_files(msg),
                    thread_ts=msg.get("thread_ts") if msg.get("thread_ts") != ts else None,
                    reply_count=msg.get("reply_count", 0),
                )
            )
        return messages

    async def send_thread_reply(
        self, channel_id: str, thread_ts: str, text: str
    ) -> tuple[bool, str]:
        """Send a threaded reply. Returns (success, error_message)."""
        try:
            await self.web_client.chat_postMessage(
                channel=channel_id, text=text, thread_ts=thread_ts
            )
            return True, ""
        except SlackApiError as e:
            error = e.response["error"]
            log.error("send_thread_reply failed: %s", error)
            return False, error

    async def get_user_name(self, user_id: str) -> str:
        """Look up user display name, with in-memory cache."""
        if user_id in self._user_cache:
            return self._user_cache[user_id].display_name

        try:
            response = await _rate_limit_retry(
                lambda: self.web_client.users_info(user=user_id)
            )
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
            response = await _rate_limit_retry(
                lambda cid=channel_id: self.web_client.conversations_history(
                    channel=cid, limit=1
                )
            )
            messages = response.get("messages", [])
            if messages:
                return float(messages[0]["ts"])
        except SlackApiError:
            pass
        return 0.0

    async def fetch_last_message_ts_batch(
        self, channel_ids: list[str], batch_size: int = 5, delay: float = 1.0
    ) -> dict[str, float]:
        """Fetch last message timestamps for multiple channels in batches.

        Returns a mapping of channel_id -> last_message_timestamp (epoch seconds).
        Channels with no messages or API errors get 0.0.
        """
        results: dict[str, float] = {}
        for i in range(0, len(channel_ids), batch_size):
            batch = channel_ids[i : i + batch_size]
            tasks = [self.fetch_last_message_ts(cid) for cid in batch]
            timestamps = await asyncio.gather(*tasks, return_exceptions=True)
            for cid, ts in zip(batch, timestamps):
                if isinstance(ts, Exception):
                    log.warning("Failed to fetch last_message_ts for %s: %s", cid, ts)
                    results[cid] = 0.0
                else:
                    results[cid] = ts
            # Rate-limit delay between batches (skip after the last batch)
            if i + batch_size < len(channel_ids):
                await asyncio.sleep(delay)
        return results

    async def download_file(self, url: str, file_id: str | None = None) -> bytes | None:
        """Download a file from Slack.

        Tries two methods:
        1. Direct URL download with Bearer token auth
        2. files.info API to get a fresh URL (requires files:read scope)
        """
        import aiohttp
        if not url:
            return None

        token = self.web_client.token
        headers = {"Authorization": f"Bearer {token}"}

        try:
            # Direct download with auth header (no auto-redirect — check first)
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, allow_redirects=False) as resp:
                    if resp.status == 200:
                        ct = resp.headers.get("Content-Type", "")
                        if "image" in ct:
                            data = await resp.read()
                            log.info("Downloaded %d bytes from direct URL", len(data))
                            return data

                # Direct URL didn't work — try files.info API for a fresh URL
                if file_id:
                    try:
                        info = await _rate_limit_retry(
                            lambda: self.web_client.files_info(file=file_id)
                        )
                        dl_url = info["file"].get("url_private_download", "")
                        if dl_url:
                            async with session.get(dl_url, headers=headers) as resp2:
                                ct = resp2.headers.get("Content-Type", "")
                                if resp2.status == 200 and "image" in ct:
                                    data = await resp2.read()
                                    log.info("Downloaded %d bytes via files.info", len(data))
                                    return data
                    except SlackApiError as e:
                        if "missing_scope" in str(e):
                            log.warning("files:read scope needed for image downloads")
                        else:
                            log.error("files.info failed: %s", e)

            log.warning("Could not download file: %s (add files:read scope to your Slack app)", url[:80])
        except Exception as e:
            log.error("Download error: %s", e)
        return None

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

    async def search_messages(self, query: str, count: int = 20) -> list[SearchResult]:
        """Search messages across the workspace.

        Requires the ``search:read`` OAuth scope on the user token.
        Returns a list of :class:`SearchResult` objects.
        """
        response = await _rate_limit_retry(
            lambda: self.web_client.search_messages(query=query, count=count, sort="timestamp")
        )
        results: list[SearchResult] = []
        for match in response.get("messages", {}).get("matches", []):
            channel_info = match.get("channel", {})
            channel_id = channel_info.get("id", "")
            channel_name = channel_info.get("name", "unknown")
            user_name = match.get("username", "unknown")
            text = match.get("text", "")
            ts = match.get("ts", "0")
            permalink = match.get("permalink", "")
            results.append(SearchResult(
                channel_id=channel_id,
                channel_name=channel_name,
                user_name=user_name,
                text=text,
                timestamp=float(ts.split(".")[0]) if ts else 0.0,
                permalink=permalink,
            ))
        return results
