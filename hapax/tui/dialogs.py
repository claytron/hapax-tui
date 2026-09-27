"""Modal dialogs: confirm or notice, and the new-file form."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from .sections import HEADER, TEXT, header_choices


class Dialog(ModalScreen[bool]):
    """A title, some lines, and buttons; dismisses True for `yes`. With yes=None it is a notice."""

    BINDINGS = [("escape", "dismiss(False)", "Cancel")]
    DEFAULT_CSS = """
    Dialog { align: center middle; }
    Dialog > Vertical { width: 80; height: auto; max-height: 90%; border: thick $accent; padding: 1 2; }
    Dialog Horizontal { height: auto; margin-top: 1; }
    """

    def __init__(self, title: str, lines: list[str], yes: str | None, no: str = "Cancel"):
        super().__init__()
        self.title_text, self.lines, self.yes, self.no = title, lines, yes, no

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self.title_text, classes="title")
            yield Static("\n".join(self.lines), markup=False)
            with Horizontal():
                if self.yes:
                    yield Button(self.yes, id="yes", variant="primary")
                yield Button(self.no if self.yes else "OK", id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")


def header_fields(fw, values: dict[str, str | None]):
    """One labelled widget per header directive, with ids h-KEY; shared by the header tab and the new-file dialog."""
    for key in HEADER:
        yield Label(key)
        value = values.get(key)
        choices = header_choices(key, fw)
        if choices is None:
            yield Input(value or "", id=f"h-{key}", restrict=TEXT, compact=True)
            continue
        current = value.upper() if value else None
        if current and current not in choices:  # an invalid value stays visible, with its finding
            choices = (*choices, current)
        yield Select([(c, c) for c in choices], id=f"h-{key}", value=current or Select.NULL, compact=True)


def header_value(widget: Input | Select) -> str | None:
    value = widget.value
    return None if value is Select.NULL or not str(value).strip() else str(value).strip()
