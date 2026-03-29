"""Main Textual application — orchestrates TUI and Slack API."""

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from textual import work
from textual.app import App, ComposeResult
from textual.message import Message as TextualMessage
from textual.widgets import Footer, Header
from textual.worker import Worker, WorkerState

from slack_tui import cache as disk_cache
from slack_tui.config import SlackConfig, load_config, save_config
from slack_tui.models import Channel, ChannelType, FileAttachment, Message
from slack_tui.screens.auth_screen import AuthScreen
from slack_tui.slack_client import SlackClient
from slack_tui.widgets.autocomplete import AutocompleteDropdown
from slack_tui.widgets.chat_panel import ChatPanel
from slack_tui.widgets.message_input import MessageInput
from slack_tui.widgets.message_view import MessageView
from slack_tui.widgets.sidebar import ChannelListItem, Sidebar

# Available slash commands: (name, description)
COMMANDS = [
    ("/msg", "jump to a DM or channel"),
    ("/channels", "reload channel list"),
    ("/help", "show available commands"),
]

POLL_INTERVAL = 3  # seconds between polling current channel
BACKGROUND_POLL_BATCH = 2  # how many other channels to check per cycle
BACKGROUND_POLL_DELAY = 2  # seconds between background batch API calls


class NewSlackMessage(TextualMessage):
    """Custom event for incoming real-time messages."""

    def __init__(self, message: Message) -> None:
        self.message = message
        super().__init__()


class SlackTuiApp(App):
    """A terminal-based Slack client."""

    TITLE = "Slack TUI"
    CSS_PATH = "app.tcss"
    BINDINGS = [
        ("tab", "toggle_focus", "Switch Panel"),
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.slack_client: SlackClient | None = None
        self.config: SlackConfig | None = None
        self.current_channel: Channel | None = None
        self._last_message_ts: str | None = None  # Track latest message for polling
        self._polling = False
        self._all_channels: list[Channel] = []
        self._channel_last_ts: dict[str, str] = {}  # track last seen ts per channel
        self._sent_texts: set[str] = set()  # track recently sent texts to deduplicate

    def compose(self) -> ComposeResult:
        yield Header()
        yield Sidebar(id="sidebar")
        yield ChatPanel(id="chat-panel")
        yield Footer()

    def on_mount(self) -> None:
        config = load_config()
        if config is not None:
            self._connect(config)
        else:
            self.push_screen(AuthScreen(), callback=self._on_auth_result)

    def _on_auth_result(self, config: SlackConfig | None) -> None:
        if config is None:
            self.exit()
            return
        save_config(config)
        self._connect(config)

    def _connect(self, config: SlackConfig) -> None:
        self.config = config
        self.slack_client = SlackClient(config.bot_token)
        # Load cached channels instantly, then refresh from API
        cached = disk_cache.load_channels()
        if cached:
            self._all_channels = cached
            self._show_channels(cached)
        self._refresh_channels()

    @work(exclusive=True, group="show_channels")
    async def _show_channels(self, channels: list[Channel]) -> None:
        sidebar = self.query_one("#sidebar", Sidebar)
        await sidebar.load_channels(channels)

    @work(exclusive=True, group="channels")
    async def _refresh_channels(self) -> None:
        """Fetch fresh channel data from Slack API and update sidebar."""
        assert self.slack_client is not None
        try:
            channels = await self.slack_client.fetch_channels()
            own_user_id = await self.slack_client.get_own_user_id()

            # Resolve display names for DMs and MPDMs
            for ch in channels:
                if ch.channel_type == ChannelType.DM and ch.user_id:
                    ch.name = await self.slack_client.resolve_dm_name(ch)
                elif ch.channel_type == ChannelType.MPDM:
                    ch.name = await self.slack_client.resolve_mpdm_name(ch, own_user_id)

            # Filter out channels with no activity in the last 90 days
            # (using `updated` field from API — not perfectly accurate, so
            # we use a generous window to avoid hiding active channels)
            cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).timestamp()
            channels = [c for c in channels if c.last_activity >= cutoff]

            self._all_channels = channels

            # Seed last-seen timestamps from current time so only messages
            # arriving after startup trigger unread indicators
            now_ts = str(time.time())
            for ch in channels:
                if ch.id not in self._channel_last_ts:
                    self._channel_last_ts[ch.id] = now_ts

            # Start polling if not already running
            if not self._polling:
                self._polling = True
                self._poll_messages()

            # Update sidebar and persist cache
            sidebar = self.query_one("#sidebar", Sidebar)
            await sidebar.load_channels(channels)
            disk_cache.save_channels(channels)
            self.slack_client.save_user_cache()
        except Exception as e:
            self.notify(f"Failed to load channels: {e}", severity="error")

    def on_sidebar_channel_selected(self, event: Sidebar.ChannelSelected) -> None:
        self.current_channel = event.channel
        self.sub_title = event.channel.name
        self._last_message_ts = None
        # Clear unread indicator
        sidebar = self.query_one("#sidebar", Sidebar)
        sidebar.mark_unread(event.channel.id, False)
        self._load_history()

    @work(exclusive=True, group="history")
    async def _load_history(self) -> None:
        assert self.slack_client is not None
        assert self.current_channel is not None
        channel_id = self.current_channel.id
        msg_view = self.query_one("#message-view", MessageView)

        # Show cached history instantly
        cached = disk_cache.load_history(channel_id)
        if cached:
            msg_view.load_history(cached)
            self._last_message_ts = cached[-1].ts
            self._channel_last_ts[channel_id] = cached[-1].ts

        # Fetch fresh history from API
        try:
            messages = await self.slack_client.fetch_history(channel_id)
            msg_view.load_history(messages)
            if messages:
                self._last_message_ts = messages[-1].ts
                self._channel_last_ts[channel_id] = messages[-1].ts
                disk_cache.save_history(channel_id, messages)
                # Download images in background
                self._download_images(messages)
        except Exception as e:
            self.notify(f"Failed to load history: {e}", severity="error")

    @work(exclusive=True, group="poll")
    async def _poll_messages(self) -> None:
        """Launch two concurrent polling loops."""
        assert self.slack_client is not None
        await asyncio.gather(
            self._poll_current_channel(),
            self._poll_background_channels(),
        )

    async def _poll_current_channel(self) -> None:
        """Poll the active channel every POLL_INTERVAL seconds."""
        while True:
            if self.current_channel:
                last_ts = self._channel_last_ts.get(self.current_channel.id)
                if last_ts:
                    try:
                        new_msgs = await self.slack_client.fetch_new_messages(
                            self.current_channel.id, last_ts
                        )
                        for msg in new_msgs:
                            self._channel_last_ts[self.current_channel.id] = msg.ts
                            self.post_message(NewSlackMessage(msg))
                    except Exception:
                        pass
            await asyncio.sleep(POLL_INTERVAL)

    async def _poll_background_channels(self) -> None:
        """Rotate through non-current channels slowly."""
        bg_index = 0
        while True:
            await asyncio.sleep(POLL_INTERVAL)
            others = [c for c in self._all_channels
                      if not self.current_channel or c.id != self.current_channel.id]
            if not others:
                continue
            batch = []
            for i in range(BACKGROUND_POLL_BATCH):
                idx = (bg_index + i) % len(others)
                batch.append(others[idx])
            bg_index = (bg_index + BACKGROUND_POLL_BATCH) % len(others)

            for ch in batch:
                last_ts = self._channel_last_ts.get(ch.id)
                if not last_ts:
                    continue
                try:
                    new_msgs = await self.slack_client.fetch_new_messages(ch.id, last_ts)
                    for msg in new_msgs:
                        self._channel_last_ts[ch.id] = msg.ts
                        self.post_message(NewSlackMessage(msg))
                except Exception:
                    pass
                await asyncio.sleep(BACKGROUND_POLL_DELAY)

    def on_message_input_autocomplete_request(self, event: MessageInput.AutocompleteRequest) -> None:
        """Generate autocomplete suggestions based on current input."""
        text = event.text
        dropdown = self.query_one("#autocomplete", AutocompleteDropdown)
        msg_input = self.query_one("#message-input", MessageInput)
        options = self._get_completions(text)
        if options:
            dropdown.show(options)
            msg_input.autocomplete_active = True
        else:
            dropdown.hide()
            msg_input.autocomplete_active = False

    def on_message_input_autocomplete_dismiss(self, event: MessageInput.AutocompleteDismiss) -> None:
        dropdown = self.query_one("#autocomplete", AutocompleteDropdown)
        msg_input = self.query_one("#message-input", MessageInput)
        dropdown.hide()
        msg_input.autocomplete_active = False

    def _get_completions(self, text: str) -> list[tuple[str, str]]:
        """Return (completion_text, description) pairs for the given input."""
        parts = text.split(None, 1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1].strip() if len(parts) > 1 else ""

        # Still typing the command name (no space yet)
        if len(parts) <= 1:
            return [(c, d) for c, d in COMMANDS if c.startswith(cmd)]

        # Command is complete, provide argument completions
        if cmd == "/msg":
            return self._complete_channel_name(arg)

        return []

    def _complete_channel_name(self, prefix: str) -> list[tuple[str, str]]:
        """Return channel/user completions for /msg."""
        search = prefix.lstrip("@#").lower()
        results: list[tuple[str, str]] = []
        for ch in self._all_channels:
            if search and not ch.name.lower().startswith(search):
                continue
            if ch.channel_type in (ChannelType.DM, ChannelType.MPDM):
                results.append((f"/msg @{ch.name}", "DM"))
            elif ch.channel_type == ChannelType.PRIVATE:
                results.append((f"/msg #{ch.name}", "private"))
            else:
                results.append((f"/msg #{ch.name}", "channel"))
            if len(results) >= 10:
                break
        return results

    def on_message_input_message_submitted(self, event: MessageInput.MessageSubmitted) -> None:
        # Dismiss autocomplete on submit
        dropdown = self.query_one("#autocomplete", AutocompleteDropdown)
        msg_input = self.query_one("#message-input", MessageInput)
        dropdown.hide()
        msg_input.autocomplete_active = False

        text = event.text
        if text.startswith("/"):
            self._handle_command(text)
            return
        if self.current_channel:
            # Optimistic display — show immediately in the UI
            now = time.time()
            local_msg = Message(
                ts=str(now),
                channel_id=self.current_channel.id,
                user_id="me",
                user_name="You",
                text=text,
                timestamp=now,
            )
            msg_view = self.query_one("#message-view", MessageView)
            msg_view.append_message(local_msg)
            self._sent_texts.add(text)
            self._bump_channel_activity(self.current_channel.id)
            self._send_message(self.current_channel.id, text)

    def _handle_command(self, text: str) -> None:
        """Parse and execute slash commands from the message input."""
        parts = text.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd == "/msg":
            self._cmd_msg(arg)
        elif cmd == "/channels":
            self._cmd_channels()
        elif cmd == "/help":
            self._cmd_help()
        else:
            self.notify(f"Unknown command: {cmd}. Type /help for a list.", severity="warning", timeout=5)

    def _cmd_msg(self, name: str) -> None:
        """Switch to a DM or channel by name. Usage: /msg @user or /msg #channel"""
        if not name:
            self.notify("Usage: /msg @user or /msg #channel", severity="warning", timeout=5)
            return
        # Strip leading @ or #
        search = name.lstrip("@#").lower()
        for ch in self._all_channels:
            if ch.name.lower() == search:
                self._select_channel(ch)
                return
        self.notify(f"No channel or user found matching '{name}'", severity="warning", timeout=5)

    def _cmd_channels(self) -> None:
        """Reload the channel list."""
        self._refresh_channels()
        self.notify("Reloading channels...", timeout=3)

    def _cmd_help(self) -> None:
        """Show available commands."""
        help_text = (
            "/msg @user — jump to a DM\n"
            "/msg #channel — jump to a channel\n"
            "/channels — reload channel list\n"
            "/help — show this help"
        )
        self.notify(help_text, timeout=10)

    def _select_channel(self, channel: Channel) -> None:
        """Programmatically select a channel (same as clicking sidebar)."""
        self.current_channel = channel
        self.sub_title = channel.name
        self._last_message_ts = None
        sidebar = self.query_one("#sidebar", Sidebar)
        sidebar.mark_unread(channel.id, False)
        self._load_history()
        # Highlight in sidebar
        sidebar = self.query_one("#sidebar", Sidebar)
        for i, item in enumerate(sidebar.children):
            if isinstance(item, ChannelListItem) and item.channel.id == channel.id:
                sidebar.index = i
                break

    @work(exclusive=False, group="send")
    async def _send_message(self, channel_id: str, text: str) -> None:
        assert self.slack_client is not None
        success, error = await self.slack_client.send_message(channel_id, text)
        if not success:
            self.notify(f"Send failed: {error}", severity="error", timeout=5)

    @work(exclusive=False, group="images")
    async def _download_images(self, messages: list[Message]) -> None:
        """Download image attachments and render them as ASCII art."""
        assert self.slack_client is not None
        msg_view = self.query_one("#message-view", MessageView)
        for message in messages:
            for file in message.files:
                if file.id in msg_view._image_cache:
                    continue
                data = await self.slack_client.download_file(file.url_private, file.id)
                if data:
                    msg_view.render_image_attachment(file, data)

    @work(exclusive=False, group="images")
    async def _download_single_image(self, file: FileAttachment) -> None:
        """Download and render a single image attachment."""
        assert self.slack_client is not None
        msg_view = self.query_one("#message-view", MessageView)
        data = await self.slack_client.download_file(file.url_private, file.id)
        if data:
            msg_view.render_image_attachment(file, data)

    def _bump_channel_activity(self, channel_id: str) -> None:
        """Update a channel's last_activity and move it to the top of its sidebar category."""
        now = time.time()
        for ch in self._all_channels:
            if ch.id == channel_id:
                ch.last_activity = now
                break
        sidebar = self.query_one("#sidebar", Sidebar)
        sidebar.move_to_top(channel_id)

    def on_new_slack_message(self, event: NewSlackMessage) -> None:
        channel_id = event.message.channel_id
        # Skip messages we already displayed optimistically
        if event.message.text in self._sent_texts:
            self._sent_texts.discard(event.message.text)
            return

        # Bump channel to top of its sidebar category
        self._bump_channel_activity(channel_id)

        if self.current_channel and channel_id == self.current_channel.id:
            # Current channel — show message in chat
            msg_view = self.query_one("#message-view", MessageView)
            msg_view.append_message(event.message)
            # Download any image attachments
            for file in event.message.files:
                self._download_single_image(file)
        else:
            # Different channel — mark unread in sidebar
            sidebar = self.query_one("#sidebar", Sidebar)
            sidebar.mark_unread(channel_id, True)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state == WorkerState.ERROR:
            logging.error("Worker %s failed: %s", event.worker.name, event.worker.error)
            self.notify(f"Error: {event.worker.error}", severity="error", timeout=10)

    async def action_quit(self) -> None:
        self.exit()

    def action_toggle_focus(self) -> None:
        """Tab toggles focus between sidebar and message input."""
        msg_input = self.query_one("#message-input", MessageInput)
        # Don't switch panels if autocomplete is active (Tab selects completion)
        if msg_input.autocomplete_active:
            return
        sidebar = self.query_one("#sidebar", Sidebar)
        if sidebar.has_focus or sidebar.has_focus_within:
            msg_input.focus()
        else:
            sidebar.focus()
