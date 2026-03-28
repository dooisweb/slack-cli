"""Sidebar widget — channel and DM list with collapsible categories."""

from textual.message import Message as TextualMessage
from textual.widgets import Label, ListItem, ListView

from slack_tui.models import Channel, ChannelType


_TYPE_PREFIX = {
    ChannelType.PUBLIC: "#",
    ChannelType.PRIVATE: "\U0001f512",  # lock emoji
    ChannelType.DM: "",
    ChannelType.MPDM: "",
}


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

    def __init__(self, channel: Channel, category_key: str) -> None:
        self.channel = channel
        self.category_key = category_key
        self._has_unread = False
        prefix = _TYPE_PREFIX.get(channel.channel_type, "")
        self._base_label = f"{prefix} {channel.name}" if prefix else channel.name
        super().__init__(Label(f"  {self._base_label}"), id=f"channel-{channel.id}")

    def set_unread(self, unread: bool) -> None:
        """Toggle the unread indicator (bold + dot)."""
        if unread == self._has_unread:
            return
        self._has_unread = unread
        lbl = self.query_one(Label)
        if unread:
            lbl.update(f"  ● {self._base_label}")
            lbl.styles.text_style = "bold"
        else:
            lbl.update(f"  {self._base_label}")
            lbl.styles.text_style = ""


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

    def mark_unread(self, channel_id: str, unread: bool = True) -> None:
        """Set or clear the unread indicator for a channel."""
        for child in self.children:
            if isinstance(child, ChannelListItem) and child.channel.id == channel_id:
                child.set_unread(unread)
                break

    def _toggle_category_items(self, category_key: str, visible: bool) -> None:
        """Show or hide all channel items under a category."""
        for child in self.children:
            if isinstance(child, ChannelListItem) and child.category_key == category_key:
                child.display = visible
