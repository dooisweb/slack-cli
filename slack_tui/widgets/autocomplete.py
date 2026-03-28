"""Autocomplete dropdown widget for slash commands."""

from textual.message import Message as TextualMessage
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class AutocompleteOption(Static):
    """A single option in the autocomplete dropdown."""

    DEFAULT_CSS = """
    AutocompleteOption {
        height: 1;
        padding: 0 1;
    }
    AutocompleteOption.highlighted {
        background: $accent;
        color: $text;
    }
    """

    def __init__(self, text: str, description: str = "") -> None:
        self.option_text = text
        display = f"{text}  [dim]{description}[/]" if description else text
        super().__init__(display)


class AutocompleteDropdown(Widget):
    """Floating dropdown that shows autocomplete suggestions above the input."""

    DEFAULT_CSS = """
    AutocompleteDropdown {
        height: auto;
        max-height: 8;
        dock: bottom;
        display: none;
        background: $surface;
        border: solid $accent;
        overflow-y: auto;
    }
    AutocompleteDropdown.visible {
        display: block;
    }
    """

    highlighted_index: reactive[int] = reactive(0)

    class OptionSelected(TextualMessage):
        """Posted when user selects an autocomplete option."""

        def __init__(self, text: str) -> None:
            self.text = text
            super().__init__()

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._options: list[tuple[str, str]] = []

    def show(self, options: list[tuple[str, str]]) -> None:
        """Show dropdown with given options as (text, description) pairs."""
        if not options:
            self.hide()
            return
        self._options = options
        self.highlighted_index = 0
        self.remove_children()
        for text, desc in options:
            self.mount(AutocompleteOption(text, desc))
        self.add_class("visible")
        self._update_highlight()

    def hide(self) -> None:
        """Hide the dropdown."""
        self._options = []
        self.remove_class("visible")
        self.remove_children()

    @property
    def is_visible(self) -> bool:
        return self.has_class("visible")

    def move_up(self) -> None:
        if self._options:
            self.highlighted_index = (self.highlighted_index - 1) % len(self._options)

    def move_down(self) -> None:
        if self._options:
            self.highlighted_index = (self.highlighted_index + 1) % len(self._options)

    def select_current(self) -> str | None:
        """Select the currently highlighted option. Returns the text or None."""
        if self._options and 0 <= self.highlighted_index < len(self._options):
            text = self._options[self.highlighted_index][0]
            self.hide()
            return text
        return None

    def watch_highlighted_index(self) -> None:
        self._update_highlight()

    def _update_highlight(self) -> None:
        for i, child in enumerate(self.query(AutocompleteOption)):
            if i == self.highlighted_index:
                child.add_class("highlighted")
            else:
                child.remove_class("highlighted")
