"""Modal dialogs: confirm or notice, and the new-file form."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from ..rules import check_file_name
from .edits import new_file_path, new_file_text
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


class NewFile(ModalScreen[Path | None]):
    """File name and header fields; creating writes the file and dismisses with its path."""

    BINDINGS = [("escape", "dismiss(None)", "Cancel")]
    DEFAULT_CSS = """
    NewFile { align: center middle; }
    NewFile > Vertical { width: 80; height: auto; max-height: 95%; border: thick $accent; padding: 1 2; }
    NewFile Horizontal { height: auto; margin-top: 1; }
    NewFile #problem { color: $warning; }
    """

    def __init__(self, directory: Path, fw, name: str = ""):
        super().__init__()
        self.directory, self.fw, self.name_text = directory, fw, name

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("New instrument definition")
            yield Label("File name")
            yield Input(self.name_text, id="name", restrict=TEXT)
            yield Static("", id="problem", markup=False)
            yield from header_fields(self.fw, {})
            with Horizontal():
                yield Button("Create", id="create", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.check_name(self.name_text)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "name":
            self.check_name(event.value)

    def check_name(self, name: str) -> None:
        found = check_file_name(name)
        self.query_one("#problem", Static).update(found[0].message if found else "")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        path = new_file_path(self.directory, self.query_one("#name", Input).value)
        if isinstance(path, str):
            self.query_one("#problem", Static).update(path)
            return
        values = {key: header_value(self.query_one(f"#h-{key}")) for key in HEADER}
        try:
            path.write_bytes(new_file_text(values).encode("utf-8"))
        except OSError as e:
            self.query_one("#problem", Static).update(str(e))
            return
        self.dismiss(path)
