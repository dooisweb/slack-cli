"""Message display widget — scrollable message history."""

import re
import subprocess
import webbrowser
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime

from rich.style import Style
from rich.text import Text
from textual.events import Click
from textual.widgets import RichLog

from slack_tui.image_render import human_size
from slack_tui.models import FileAttachment, Message

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

# Prefixes for link actions
_LINK_PREFIX = "open:"
_IMAGE_PREFIX = "img:"


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
    result = Text()
    pos = 0

    # Pass 1: replace Slack <url|label> with label, tracking link positions
    expanded = ""
    link_spans: list[tuple[int, int, str]] = []

    for match in _SLACK_LINK_RE.finditer(text):
        url = match.group(1)
        label = match.group(2) or url
        expanded += text[pos:match.start()]
        start = len(expanded)
        expanded += label
        link_spans.append((start, len(expanded), url))
        pos = match.end()
    expanded += text[pos:]

    # Pass 2: find bare URLs not overlapping existing links
    for match in _BARE_URL_RE.finditer(expanded):
        url_start, url_end = match.start(), match.end()
        overlaps = any(s <= url_start < e or s < url_end <= e for s, e, _ in link_spans)
        if not overlaps:
            link_spans.append((url_start, url_end, match.group(0)))

    link_spans.sort(key=lambda s: s[0])

    pos = 0
    for start, end, url in link_spans:
        if start > pos:
            result.append(expanded[pos:start])
        encoded = urlsafe_b64encode(url.encode()).decode()
        link_style = Style(
            bold=True, color="blue", underline=True,
            link=f"{_LINK_PREFIX}{encoded}",
        )
        result.append(expanded[start:end], style=link_style)
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
        self._image_cache: dict[str, bytes] = {}  # file_id -> image bytes

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

    def on_click(self, event: Click) -> None:
        """Handle clicks on links and image view buttons."""
        style = self.get_style_at(event.x, event.y)
        if not style or not style.link:
            return

        if style.link.startswith(_LINK_PREFIX):
            encoded = style.link[len(_LINK_PREFIX):]
            try:
                url = urlsafe_b64decode(encoded.encode()).decode()
                webbrowser.open(url)
            except Exception:
                pass
        elif style.link.startswith(_IMAGE_PREFIX):
            file_id = style.link[len(_IMAGE_PREFIX):]
            self._open_cached_image(file_id)

    def _open_cached_image(self, file_id: str) -> None:
        """Open a cached image in the system viewer."""
        data = self._image_cache.get(file_id)
        if not data:
            return
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(data)
            path = f.name
        try:
            subprocess.Popen(["xdg-open", path],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            webbrowser.open(f"file://{path}")

    def render_image_attachment(self, file: FileAttachment, image_data: bytes) -> None:
        """Render an image as ASCII art inline."""
        from slack_tui.image_render import render_image

        self._image_cache[file.id] = image_data

        # Header line: filename + size + clickable [View]
        header = Text()
        header.append("    [img] ", style="dim")
        header.append(file.name, style="italic")
        header.append(f" ({human_size(file.size)})  ", style="dim")
        header.append(
            "[Open]",
            style=Style(bold=True, color="blue", underline=True,
                        link=f"{_IMAGE_PREFIX}{file.id}"),
        )
        self.write(header)

        # Render ASCII art
        try:
            art = render_image(image_data)
            self.write(art)
        except Exception:
            self.write(Text("    (could not render image)", style="dim italic"))

    def show_image_placeholder(self, file: FileAttachment) -> None:
        """Show a placeholder for an image that hasn't been downloaded yet."""
        line = Text()
        line.append("    [img] ", style="dim")
        line.append(file.name, style="italic")
        line.append(f" ({human_size(file.size)})", style="dim")
        line.append("  loading...", style="dim italic")
        self.write(line)

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

        # Show placeholders for image attachments (actual rendering happens async)
        for file in message.files:
            if file.id in self._image_cache:
                self.render_image_attachment(file, self._image_cache[file.id])
            else:
                self.show_image_placeholder(file)

    def load_history(self, messages: list[Message]) -> None:
        """Clear and load a batch of historical messages."""
        self.clear()
        self._last_date_label = None
        for msg in messages:
            self.append_message(msg)
