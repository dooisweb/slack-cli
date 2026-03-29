"""Message display widget — scrollable message history."""

import re
import subprocess
import webbrowser
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime

import emoji

from rich.style import Style
from rich.text import Text
from textual.events import Click
from textual.message import Message as TextualMessage
from textual.widgets import RichLog

from slack_tui.image_render import human_size, render_image
from slack_tui.models import FileAttachment, Message, SearchResult

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

# Slack shortcode names that differ from the emoji package alias names
_SLACK_EMOJI_ALIASES: dict[str, str] = {
    "simple_smile": "slightly_smiling_face",
    "smile": "grinning_face_with_smiling_eyes",
    "+1": "thumbsup",
    "thumbsup": "thumbsup",
    "-1": "thumbsdown",
    "hankey": "pile_of_poo",
    "shipit": "chipmunk",
    "white_check_mark": "white_heavy_check_mark",
    "heavy_check_mark": "heavy_check_mark",
    "slightly_frowning_face": "slightly_frowning_face",
    "laughing": "grinning_squinting_face",
    "satisfied": "grinning_squinting_face",
}

# Slack skin-tone modifier pattern: :skin-tone-N: (N = 2..6)
_SKIN_TONE_RE = re.compile(r":skin-tone-([2-6]):")
# Mapping from Slack skin tone number to Unicode modifier
_SKIN_TONE_MODIFIERS = {
    "2": "\U0001F3FB",  # light
    "3": "\U0001F3FC",  # medium-light
    "4": "\U0001F3FD",  # medium
    "5": "\U0001F3FE",  # medium-dark
    "6": "\U0001F3FF",  # dark
}

# Match a Slack emoji shortcode (possibly followed by a skin tone modifier)
_SLACK_SHORTCODE_RE = re.compile(r":([a-zA-Z0-9_+\-]+):(?::skin-tone-([2-6]):)?")


def _convert_emoji_shortcodes(text: str) -> str:
    """Replace Slack emoji shortcodes with Unicode emoji characters."""

    def _replace(match: re.Match) -> str:
        name = match.group(1)
        skin_tone = match.group(2)

        # Try Slack-specific alias mapping first
        mapped = _SLACK_EMOJI_ALIASES.get(name, name)

        # Try emoji package alias lookup (handles most Slack names)
        result = emoji.emojize(f":{mapped}:", language="alias")

        # If alias didn't resolve, try default language
        if result == f":{mapped}:":
            result = emoji.emojize(f":{mapped}:")

        # If still unresolved, try original name with default language
        if result.startswith(":") and result.endswith(":") and name != mapped:
            result = emoji.emojize(f":{name}:", language="alias")
            if result == f":{name}:":
                result = emoji.emojize(f":{name}:")

        # Append skin tone modifier if present and emoji was resolved
        if skin_tone and not (result.startswith(":") and result.endswith(":")):
            result += _SKIN_TONE_MODIFIERS.get(skin_tone, "")

        return result

    return _SLACK_SHORTCODE_RE.sub(_replace, text)

# Prefixes for link actions
_LINK_PREFIX = "open:"
_IMAGE_PREFIX = "img:"
_SEARCH_NAV_PREFIX = "searchnav:"
_THREAD_PREFIX = "thread:"
_THREAD_CLOSE_PREFIX = "threadclose:"


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
    text = _convert_emoji_shortcodes(text)
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

    ALLOW_SELECT = True

    class ThreadViewRequest(TextualMessage):
        """Posted when the user clicks [View Thread]."""

        def __init__(self, thread_ts: str) -> None:
            self.thread_ts = thread_ts
            super().__init__()

    class ThreadCloseRequest(TextualMessage):
        """Posted when the user clicks '< Close Thread'."""
        pass

    class SearchNavigateRequest(TextualMessage):
        """Posted when the user clicks a channel name in search results."""

        def __init__(self, channel_id: str) -> None:
            self.channel_id = channel_id
            super().__init__()

    # Group messages from same user within this many seconds
    _GROUP_THRESHOLD = 300  # 5 minutes

    def __init__(self, **kwargs) -> None:
        super().__init__(markup=True, wrap=True, auto_scroll=True, **kwargs)
        self._user_color_map: dict[str, str] = {}
        self._last_date_label: str | None = None
        self._image_cache: dict[str, bytes] = {}  # file_id -> image bytes
        self._last_user_id: str | None = None
        self._last_timestamp: float = 0.0

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
            # Reset grouping across date boundaries
            self._last_user_id = None
            self._last_timestamp = 0.0
            self.write(Text(""))  # blank line before separator
            separator = Text()
            separator.append(f"── {label} ", style="bold dim")
            separator.append("─" * 40, style="dim")
            self.write(separator)

    def on_click(self, event: Click) -> None:
        """Handle clicks on links and image view buttons."""
        import logging
        log = logging.getLogger(__name__)
        style = event.style
        log.debug("Click at (%s,%s) style.link=%s", event.x, event.y,
                   getattr(style, 'link', None) if style else None)
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
        elif style.link.startswith(_THREAD_PREFIX):
            thread_ts = style.link[len(_THREAD_PREFIX):]
            self.post_message(self.ThreadViewRequest(thread_ts))
        elif style.link.startswith(_THREAD_CLOSE_PREFIX):
            self.post_message(self.ThreadCloseRequest())
        elif style.link.startswith(_SEARCH_NAV_PREFIX):
            encoded_id = style.link[len(_SEARCH_NAV_PREFIX):]
            try:
                channel_id = urlsafe_b64decode(encoded_id.encode()).decode()
                self.post_message(self.SearchNavigateRequest(channel_id))
            except Exception:
                pass

    def _open_cached_image(self, file_id: str) -> None:
        """Open a cached image in the system viewer."""
        import os
        import shutil
        import tempfile
        data = self._image_cache.get(file_id)
        if not data:
            return
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(data)
            path = f.name
        # Try dedicated image viewers first, fall back to xdg-open
        viewers = ["eog", "feh", "display", "sxiv", "imv", "xdg-open"]
        for viewer in viewers:
            if shutil.which(viewer):
                try:
                    subprocess.Popen(
                        [viewer, path],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                    return
                except Exception:
                    continue
        webbrowser.open(f"file://{path}")

    def _is_continuation(self, message: Message) -> bool:
        """Check if this message continues a group from the same user."""
        if self._last_user_id != message.user_id:
            return False
        return (message.timestamp - self._last_timestamp) < self._GROUP_THRESHOLD

    def append_message(self, message: Message) -> None:
        """Format and display a single message."""
        self._maybe_write_date_separator(message)

        time_str = datetime.fromtimestamp(message.timestamp).strftime("%H:%M")
        color = self._color_for_user(message.user_id)
        continuation = self._is_continuation(message)

        if not continuation:
            # Blank line to separate from the previous user's messages
            if self._last_user_id is not None:
                self.write(Text(""))
            # Header line: username (bold, colored) + right-aligned timestamp (dim)
            header = Text()
            header.append(f"{message.user_name}", style=f"bold {color}")
            header.append(f"  {time_str}", style="dim")
            self.write(header)

        # Message body, indented 2 spaces
        body = Text()
        body.append("  ")
        body.append_text(_format_text_with_links(message.text))
        self.write(body)

        self._last_user_id = message.user_id
        self._last_timestamp = message.timestamp

        # Show inline placeholder for image attachments (images open from cache via [Open])
        for file in message.files:
            line = Text()
            line.append("    [img] ", style="dim")
            line.append(file.name, style="italic")
            line.append(f" ({human_size(file.size)})  ", style="dim")
            line.append(
                "[Open]",
                style=Style(bold=True, color="blue", underline=True,
                            link=f"{_IMAGE_PREFIX}{file.id}"),
            )
            self.write(line)
            # Render ASCII art inline if the image is already cached
            if file.id in self._image_cache:
                try:
                    art = render_image(self._image_cache[file.id])
                    self.write(art)
                except Exception:
                    pass  # corrupted/unsupported image — just show placeholder

        # Thread indicator for messages with replies
        if message.reply_count > 0:
            thread_line = Text()
            n = message.reply_count
            label = "1 reply" if n == 1 else f"{n} replies"
            thread_line.append(
                f"    View Thread ({label})",
                style=Style(
                    bold=True, color="blue", underline=True,
                    link=f"{_THREAD_PREFIX}{message.ts}",
                ),
            )
            self.write(thread_line)

    def show_thread_header(self, parent_text: str) -> None:
        """Show a header indicating we're in thread view mode."""
        self.clear()
        self._last_date_label = None
        self._last_user_id = None
        self._last_timestamp = 0.0
        # Clickable "< Close Thread" link at the top
        close_line = Text()
        close_line.append(
            "< Close Thread",
            style=Style(
                bold=True, underline=True,
                link=f"{_THREAD_CLOSE_PREFIX}close",
            ),
        )
        self.write(close_line)
        self.write(Text(""))
        header = Text()
        header.append("Thread", style="bold cyan")
        preview = parent_text[:80] + ("..." if len(parent_text) > 80 else "")
        header.append(f": {preview}", style="dim")
        self.write(header)
        sep = Text()
        sep.append("─" * 50, style="dim cyan")
        self.write(sep)
        self.write(Text(""))

    def load_history(self, messages: list[Message]) -> None:
        """Clear and load a batch of historical messages."""
        self.clear()
        self._last_date_label = None
        self._last_user_id = None
        self._last_timestamp = 0.0
        for msg in messages:
            self.append_message(msg)

    def show_search_results(self, query: str, results: list[SearchResult]) -> None:
        """Display formatted search results, replacing current content."""
        self.clear()
        self._last_date_label = None
        self._last_user_id = None
        self._last_timestamp = 0.0

        header = Text()
        header.append("── Search results for ", style="bold dim")
        header.append(f'"{query}"', style="bold")
        header.append(f" ({len(results)} found) ", style="bold dim")
        header.append("─" * 30, style="dim")
        self.write(header)
        self.write(Text(""))

        if not results:
            self.write(Text("  No results found.", style="dim italic"))
            self.write(Text(""))
            self.write(Text("  Use /back to return to the channel view.", style="dim"))
            return

        for result in results:
            time_str = datetime.fromtimestamp(result.timestamp).strftime("%Y-%m-%d %H:%M")

            # Channel name as a clickable link to navigate
            encoded_id = urlsafe_b64encode(result.channel_id.encode()).decode()
            nav_style = Style(
                bold=True, color="cyan", underline=True,
                link=f"{_SEARCH_NAV_PREFIX}{encoded_id}",
            )

            line = Text()
            line.append(f"  #{result.channel_name}", style=nav_style)
            line.append(f"  {result.user_name}", style="bold green")
            line.append(f"  {time_str}", style="dim")
            self.write(line)

            # Message text, indented
            body = Text()
            body.append("    ")
            body.append_text(_format_text_with_links(result.text))
            self.write(body)
            self.write(Text(""))
