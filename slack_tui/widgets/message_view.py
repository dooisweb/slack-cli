"""Message display widget — scrollable message history."""

import re
from datetime import datetime

from rich.text import Text
from textual.widgets import RichLog

from slack_tui.models import Message

# Rotating palette for user name colors
_USER_COLORS = [
    "cyan",
    "green",
    "magenta",
    "yellow",
    "blue",
    "red",
    "#ff8700",   # orange
    "#af87ff",   # purple
    "#5fd7ff",   # light blue
    "#87d787",   # light green
    "#ff87af",   # pink
    "#d7af5f",   # gold
]

# Slack markup: <url> or <url|label>
_SLACK_LINK_RE = re.compile(r"<(https?://[^|>]+)(?:\|([^>]+))?>")
# Bare URLs not inside < >
_BARE_URL_RE = re.compile(r"(?<![<|])(https?://\S+)")


def _date_label(dt: datetime) -> str:
    """Return a human-friendly date label."""
    today = datetime.now().date()
    msg_date = dt.date()
    delta = (today - msg_date).days

    if delta == 0:
        return "Today"
    elif delta == 1:
        return "Yesterday"
    elif delta < 7:
        return f"{delta} days ago"
    else:
        return msg_date.strftime("%b %d, %Y")


def _format_text_with_links(text: str) -> Text:
    """Parse Slack markup and bare URLs into Rich Text with styled links."""
    # First pass: expand Slack <url|label> and <url> markup to plain text,
    # tracking where the links are
    result = Text()
    pos = 0

    # Combine both patterns: process Slack links first, then bare URLs
    # We'll do two passes: first replace Slack markup, then find bare URLs

    # Pass 1: replace Slack <url|label> with label, tracking link positions
    expanded = ""
    link_spans: list[tuple[int, int, str]] = []  # (start, end, url)

    for match in _SLACK_LINK_RE.finditer(text):
        url = match.group(1)
        label = match.group(2) or url
        expanded += text[pos:match.start()]
        start = len(expanded)
        expanded += label
        link_spans.append((start, len(expanded), url))
        pos = match.end()
    expanded += text[pos:]

    # Pass 2: find bare URLs in the expanded text (not overlapping existing links)
    for match in _BARE_URL_RE.finditer(expanded):
        url_start, url_end = match.start(), match.end()
        # Skip if this overlaps with an already-tracked link
        overlaps = any(s <= url_start < e or s < url_end <= e for s, e, _ in link_spans)
        if not overlaps:
            link_spans.append((url_start, url_end, match.group(0)))

    # Sort spans by start position
    link_spans.sort(key=lambda s: s[0])

    # Build Rich Text with link styling
    pos = 0
    for start, end, url in link_spans:
        if start > pos:
            result.append(expanded[pos:start])
        result.append(expanded[start:end], style=f"bold blue link {url}")
        pos = end
    if pos < len(expanded):
        result.append(expanded[pos:])

    return result


class MessageView(RichLog):
    """Scrollable message history display."""

    def __init__(self, **kwargs) -> None:
        super().__init__(markup=True, wrap=True, auto_scroll=True, **kwargs)
        self._user_color_map: dict[str, str] = {}
        self._last_date_label: str | None = None

    def _color_for_user(self, user_id: str) -> str:
        """Assign a consistent color to each user."""
        if user_id not in self._user_color_map:
            idx = len(self._user_color_map) % len(_USER_COLORS)
            self._user_color_map[user_id] = _USER_COLORS[idx]
        return self._user_color_map[user_id]

    def _maybe_write_date_separator(self, message: Message) -> None:
        """Write a date separator if the date changed."""
        dt = datetime.fromtimestamp(message.timestamp)
        label = _date_label(dt)
        if label != self._last_date_label:
            self._last_date_label = label
            separator = Text()
            separator.append(f"── {label} ", style="bold dim")
            separator.append("─" * 40, style="dim")
            self.write(separator)

    def append_message(self, message: Message) -> None:
        """Format and display a single message."""
        self._maybe_write_date_separator(message)

        time_str = datetime.fromtimestamp(message.timestamp).strftime("%H:%M")
        color = self._color_for_user(message.user_id)

        formatted = Text()
        formatted.append(f"[{time_str}] ", style="dim")
        formatted.append(f"{message.user_name}", style=f"bold {color}")
        formatted.append(": ")
        formatted.append_text(_format_text_with_links(message.text))
        self.write(formatted)

    def load_history(self, messages: list[Message]) -> None:
        """Clear and load a batch of historical messages."""
        self.clear()
        self._last_date_label = None
        for msg in messages:
            self.append_message(msg)
