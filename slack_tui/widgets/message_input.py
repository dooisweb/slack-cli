"""Message input widget — text input with send-on-Enter and autocomplete support."""

from textual.events import Key
from textual.message import Message as TextualMessage
from textual.widgets import Input


class MessageInput(Input):
    """Text input for composing messages."""

    class MessageSubmitted(TextualMessage):
        """Posted when the user presses Enter with text."""

        def __init__(self, text: str) -> None:
            self.text = text
            super().__init__()

    class AutocompleteRequest(TextualMessage):
        """Posted when the input text changes and starts with /."""

        def __init__(self, text: str) -> None:
            self.text = text
            super().__init__()

    class AutocompleteDismiss(TextualMessage):
        """Posted when autocomplete should be dismissed."""

    def __init__(self, **kwargs) -> None:
        super().__init__(placeholder="Type a message... (/ for commands)", **kwargs)
        self._autocomplete_active = False

    @property
    def autocomplete_active(self) -> bool:
        return self._autocomplete_active

    @autocomplete_active.setter
    def autocomplete_active(self, value: bool) -> None:
        self._autocomplete_active = value

    def _find_emoji_prefix(self, text: str, cursor: int) -> str | None:
        """Check if cursor is inside an emoji shortcode like ':thumb'."""
        # Search backwards from cursor for an opening ':'
        left = text[:cursor]
        colon_pos = left.rfind(":")
        if colon_pos == -1:
            return None
        fragment = left[colon_pos:]
        # Must be :word_chars with no spaces, at least 2 chars after :
        if " " in fragment or len(fragment) < 3:
            return None
        return fragment

    def on_input_changed(self, event: Input.Changed) -> None:
        text = event.value
        if text.startswith("/"):
            self.post_message(self.AutocompleteRequest(text))
        elif self._find_emoji_prefix(text, self.cursor_position):
            self.post_message(self.AutocompleteRequest(text))
        else:
            self.post_message(self.AutocompleteDismiss())

    def on_key(self, event: Key) -> None:
        if self._autocomplete_active:
            if event.key == "up":
                event.prevent_default()
                event.stop()
                from slack_tui.widgets.autocomplete import AutocompleteDropdown
                dropdown = self.screen.query_one("#autocomplete", AutocompleteDropdown)
                dropdown.move_up()
                return
            elif event.key == "down":
                event.prevent_default()
                event.stop()
                from slack_tui.widgets.autocomplete import AutocompleteDropdown
                dropdown = self.screen.query_one("#autocomplete", AutocompleteDropdown)
                dropdown.move_down()
                return
            elif event.key == "tab":
                event.prevent_default()
                event.stop()
                from slack_tui.widgets.autocomplete import AutocompleteDropdown
                dropdown = self.screen.query_one("#autocomplete", AutocompleteDropdown)
                selected = dropdown.select_current()
                if selected:
                    # Check if we're completing an emoji (selected is a unicode char)
                    emoji_prefix = self._find_emoji_prefix(self.value, self.cursor_position)
                    if emoji_prefix and not selected.startswith("/"):
                        # Replace the :shortcode with the emoji character
                        left = self.value[:self.cursor_position]
                        right = self.value[self.cursor_position:]
                        colon_pos = left.rfind(":")
                        self.value = left[:colon_pos] + selected + " " + right
                        self.cursor_position = colon_pos + len(selected) + 1
                    else:
                        self.value = selected + " "
                        self.cursor_position = len(self.value)
                    self.post_message(self.AutocompleteRequest(self.value))
                return
            elif event.key == "escape":
                event.prevent_default()
                event.stop()
                self.post_message(self.AutocompleteDismiss())
                return

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Dismiss autocomplete on Enter, then submit normally
        if self._autocomplete_active:
            self.post_message(self.AutocompleteDismiss())
        text = event.value.strip()
        if text:
            self.post_message(self.MessageSubmitted(text))
            self.clear()
