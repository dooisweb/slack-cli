"""Chat panel — right side container with messages and input."""

from textual.app import ComposeResult
from textual.containers import Vertical

from slack_tui.widgets.autocomplete import AutocompleteDropdown
from slack_tui.widgets.message_input import MessageInput
from slack_tui.widgets.message_view import MessageView


class ChatPanel(Vertical):
    """Right panel containing message view and input."""

    def compose(self) -> ComposeResult:
        yield MessageView(id="message-view")
        yield AutocompleteDropdown(id="autocomplete")
        yield MessageInput(id="message-input")
