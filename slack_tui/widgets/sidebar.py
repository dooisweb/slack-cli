"""Sidebar widget — channel and DM list with collapsible categories."""

from textual.message import Message as TextualMessage
from textual.widgets import Label, ListItem, ListView
from textual.containers import Vertical

from slack_tui.models import Channel, ChannelType


_TYPE_PREFIX = {
    ChannelType.PUBLIC: "#",
    ChannelType.PRIVATE: "\U0001f512",  # lock emoji
    ChannelType.DM: "",
    ChannelType.MPDM: "",
}

# Presence indicator dots
_PRESENCE_ACTIVE = "\u25cf"  # ● filled circle (green)
_PRESENCE_AWAY = "\u25cb"    # ○ hollow circle


class CategoryHeader(ListItem):
    """A clickable category header that toggles visibility of its items."""

    def __init__(self, label: str, category_key: str) -> None:
        self.category_key = category_key
        self._expanded = True
        self._label_text = label
        super().__init__(Label(f"▼ {label}"), id=f"cat-{category_key}")

    @property
    def expanded(self) -> bool:
        return self._expanded

    def toggle(self) -> None:
        self._expanded = not self._expanded
        arrow = "▼" if self._expanded else "▶"
        self.query_one(Label).update(f"{arrow} {self._label_text}")


class ChannelListItem(ListItem):
    """A single channel/DM entry."""

    MAX_PREVIEW_LEN = 25

    def __init__(self, channel: Channel, category_key: str) -> None:
        self.channel = channel
        self.category_key = category_key
        self._has_unread = False
        self._preview_text = ""
        self._presence: str | None = None  # "active", "away", or None (no presence shown)
        prefix = _TYPE_PREFIX.get(channel.channel_type, "")
        self._base_label = f"{prefix} {channel.name}" if prefix else channel.name
        self._name_label = Label(f"  {self._base_label}", classes="channel-name")
        self._preview_label = Label("", classes="channel-preview")
        self._preview_label.display = False
        super().__init__(
            Vertical(self._name_label, self._preview_label, classes="channel-item-container"),
            id=f"channel-{channel.id}",
        )

    def _presence_prefix(self) -> str:
        """Return the presence dot prefix for this item."""
        if self._presence == "active":
            return f"[green]{_PRESENCE_ACTIVE}[/green] "
        elif self._presence == "away":
            return f"[dim]{_PRESENCE_AWAY}[/dim] "
        return ""

    def _refresh_label(self) -> None:
        """Re-render the name label based on current unread + presence state."""
        presence = self._presence_prefix()
        if self._has_unread:
            self._name_label.update(f"  \u25cf {presence}{self._base_label}")
            self._name_label.styles.text_style = "bold"
        else:
            self._name_label.update(f"  {presence}{self._base_label}")
            self._name_label.styles.text_style = "none"

    def set_unread(self, unread: bool) -> None:
        """Toggle the unread indicator (bold + dot)."""
        if unread == self._has_unread:
            return
        self._has_unread = unread
        self._refresh_label()

    def set_presence(self, presence: str) -> None:
        """Set the presence state ('active', 'away', or None)."""
        if presence == self._presence:
            return
        self._presence = presence
        self._refresh_label()

    def set_preview(self, user_name: str, text: str) -> None:
        """Update the message preview line below the channel name."""
        # Flatten to single line
        flat = text.replace("\n", " ").strip()
        preview = f"{user_name}: {flat}"
        if len(preview) > self.MAX_PREVIEW_LEN:
            preview = preview[: self.MAX_PREVIEW_LEN] + "\u2026"
        self._preview_text = preview
        # Escape Rich markup brackets to prevent injection from message content
        safe_preview = preview.replace("[", "\\[")
        self._preview_label.update(f"    {safe_preview}")
        self._preview_label.display = True


class Sidebar(ListView):
    """Left panel: scrollable list of channels and DMs with collapsible categories."""

    class ChannelSelected(TextualMessage):
        """Posted when a channel is selected."""

        def __init__(self, channel: Channel) -> None:
            self.channel = channel
            super().__init__()

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._categories: dict[str, CategoryHeader] = {}

    async def load_channels(self, channels: list[Channel]) -> None:
        """Populate the sidebar with categorized channel items."""
        await self.clear()
        self._categories.clear()

        # Group channels by category
        groups: dict[str, list[Channel]] = {}
        for ch in channels:
            if ch.channel_type in (ChannelType.PRIVATE, ChannelType.PUBLIC):
                key = "channels"
            elif ch.channel_type == ChannelType.DM:
                key = "dms"
            else:
                key = "dm_groups"
            groups.setdefault(key, []).append(ch)

        # Render in order: DMs, DM Groups, Channels (private + public)
        category_defs = [
            ("dms", "DMs"),
            ("dm_groups", "DM Groups"),
            ("channels", "Channels"),
        ]

        for key, label in category_defs:
            items = groups.get(key, [])
            if not items:
                continue
            # Sort within category: private before public, then by last_activity desc
            if key == "channels":
                items.sort(key=lambda c: (0 if c.channel_type == ChannelType.PRIVATE else 1, -c.last_activity))
            else:
                items.sort(key=lambda c: -c.last_activity)

            header = CategoryHeader(label, key)
            self._categories[key] = header
            await self.append(header)
            for ch in items:
                await self.append(ChannelListItem(ch, key))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, CategoryHeader):
            event.item.toggle()
            self._toggle_category_items(event.item.category_key, event.item.expanded)
        elif isinstance(event.item, ChannelListItem):
            self.post_message(self.ChannelSelected(event.item.channel))

    def update_preview(self, channel_id: str, user_name: str, text: str) -> None:
        """Update the message preview for a channel."""
        for child in self.children:
            if isinstance(child, ChannelListItem) and child.channel.id == channel_id:
                child.set_preview(user_name, text)
                break

    def mark_unread(self, channel_id: str, unread: bool = True) -> None:
        """Set or clear the unread indicator for a channel."""
        for child in self.children:
            if isinstance(child, ChannelListItem) and child.channel.id == channel_id:
                child.set_unread(unread)
                break

    def move_to_top(self, channel_id: str) -> None:
        """Move a channel to the top of its category (just after the header).

        This provides a lightweight re-sort when a new message is sent or
        received, without rebuilding the entire sidebar.
        """
        # Find the ChannelListItem for this channel
        target: ChannelListItem | None = None
        for child in self.children:
            if isinstance(child, ChannelListItem) and child.channel.id == channel_id:
                target = child
                break
        if target is None:
            return

        category_key = target.category_key
        header = self._categories.get(category_key)
        if header is None:
            return

        # Find the position right after the category header
        header_index: int | None = None
        for i, child in enumerate(self.children):
            if child is header:
                header_index = i
                break
        if header_index is None:
            return

        # The first item slot is header_index + 1
        first_slot = header_index + 1

        # Find current index of the target
        target_index: int | None = None
        for i, child in enumerate(self.children):
            if child is target:
                target_index = i
                break
        if target_index is None or target_index == first_slot:
            # Already at the top of its category — nothing to do
            return

        self.move_child(target, before=first_slot)

    def update_presence(self, user_presence: dict[str, str]) -> None:
        """Update presence indicators for DM channels.

        Args:
            user_presence: mapping of user_id -> presence ("active" or "away")
        """
        for child in self.children:
            if isinstance(child, ChannelListItem) and child.channel.channel_type == ChannelType.DM:
                user_id = child.channel.user_id
                if user_id and user_id in user_presence:
                    child.set_presence(user_presence[user_id])

    def _toggle_category_items(self, category_key: str, visible: bool) -> None:
        """Show or hide all channel items under a category."""
        for child in self.children:
            if isinstance(child, ChannelListItem) and child.category_key == category_key:
                child.display = visible
