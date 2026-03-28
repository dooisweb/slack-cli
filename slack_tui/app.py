"""Main Textual application — orchestrates TUI and Slack API."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from textual import work
from textual.app import App, ComposeResult
from textual.message import Message as TextualMessage
from textual.widgets import Footer, Header
from textual.worker import Worker, WorkerState

from slack_tui import cache as disk_cache
from slack_tui.config import SlackConfig, load_config, save_config
from slack_tui.models import Channel, ChannelType, Message
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

POLL_INTERVAL = 3  # seconds between polling for new messages


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

            # Fetch actual last message timestamps concurrently
            async def _update_last_activity(ch: Channel) -> None:
                ch.last_activity = await self.slack_client.fetch_last_message_ts(ch.id)

            await asyncio.gather(*[_update_last_activity(ch) for ch in channels])

            # Filter out channels with no activity in the last 30 days
            cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).timestamp()
            channels = [c for c in channels if c.last_activity >= cutoff]

            self._all_channels = channels

            # Seed last-seen timestamps for polling all channels
            for ch in channels:
                if ch.id not in self._channel_last_ts and ch.last_activity > 0:
                    self._channel_last_ts[ch.id] = str(ch.last_activity)

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
        except Exception as e:
            self.notify(f"Failed to load history: {e}", severity="error")

    @work(exclusive=True, group="poll")
    async def _poll_messages(self) -> None:
        """Poll all channels for new messages every few seconds."""
        assert self.slack_client is not None
        log = logging.getLogger(__name__)
        while True:
            await asyncio.sleep(POLL_INTERVAL)
            for ch in self._all_channels:
                last_ts = self._channel_last_ts.get(ch.id)
                if not last_ts:
                    continue
                try:
                    new_messages = await self.slack_client.fetch_new_messages(ch.id, last_ts)
                    for msg in new_messages:
                        self._channel_last_ts[ch.id] = msg.ts
                        self.post_message(NewSlackMessage(msg))
                except Exception:
                    pass  # silently skip errors for background channels

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

    def on_new_slack_message(self, event: NewSlackMessage) -> None:
        channel_id = event.message.channel_id
        if self.current_channel and channel_id == self.current_channel.id:
            # Current channel — show message in chat
            msg_view = self.query_one("#message-view", MessageView)
            msg_view.append_message(event.message)
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
