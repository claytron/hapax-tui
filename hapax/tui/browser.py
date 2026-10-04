"""The directory's definitions and their status."""

from pathlib import Path

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Header

from ..files import check, expand
from ..parse import Severity
from .lists import DataTable


def status(path: Path, fw, warn: bool) -> str:
    """As `hapax validate` summarises a file: OK, or counts like 2E 1W."""
    try:
        findings = check(path, fw)
    except OSError:
        return "unreadable"
    errors = sum(f.severity is Severity.ERROR for f in findings)
    warnings = (len(findings) - errors) * warn
    return " ".join([f"{errors}E"] * bool(errors) + [f"{warnings}W"] * bool(warnings)) or "OK"


class Browser(Screen):
    BINDINGS = [("n", "new", "New")]

    def __init__(self, directory: Path):
        super().__init__()
        self.directory = directory

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="files", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(DataTable).add_columns("name", "status")

    def on_screen_resume(self) -> None:
        self.sub_title = str(self.directory)
        table = self.query_one(DataTable)
        table.clear()
        files = expand([self.directory])
        for name, path in [] if isinstance(files, str) else files:
            table.add_row(name, status(path, self.app.fw, self.app.warn), key=str(path))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.app.open_file(Path(event.row_key.value))

    def action_new(self) -> None:
        self.app.new_file(self.directory)
