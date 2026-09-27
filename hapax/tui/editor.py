"""The editor: a header form, a table per section, a row form, and the findings panel.

Every action edits self.lines, then re-parses and re-validates everything from them (edits.analyse).
"""

from collections import defaultdict
from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    DataTable, Footer, Header, Input, Label, OptionList, Select, Static, TabbedContent, TabPane, TextArea,
)

from ..parse import Finding, Section, Severity
from ..rules import check_file_name, fw_str
from .dialogs import Dialog, header_fields, header_value
from .edits import analyse, body_text, rows, set_directive, tab_of
from .sections import ORDER, SECTIONS


def _cell(value) -> str:
    return "—" if value is None else str(value)


class Editor(Screen):
    BINDINGS = [
        Binding("ctrl+s", "save", "Save"),
        Binding("w", "warnings", "Warnings"),
        Binding("escape", "leave", "Back"),
    ]
    DEFAULT_CSS = """
    Editor TabbedContent { height: 1fr; }
    Editor TabPane { height: 1fr; }
    Editor DataTable { height: 1fr; }
    Editor #findings { height: 10; border-top: solid $accent; }
    Editor TextArea { height: 1fr; }
    RowForm { height: auto; border-top: solid $accent; }
    RowForm Horizontal { height: auto; }
    RowForm .column { width: 1fr; height: auto; }
    RowForm #c-name, RowForm #c-text { width: 3fr; }
    .message { color: $warning; }
    """

    def __init__(self, path: Path, saved: str, text: str, fw, warn: bool):
        super().__init__()
        self.path, self.saved, self.fw, self.show_warnings = path, saved, fw, warn
        self.lines = text.split("\n")
        self.shown: list[Finding] = []
        self.analyse()

    def analyse(self) -> None:
        self.doc, found = analyse(self.lines, self.fw)
        self.findings = check_file_name(self.path.name) + found
        self.at = {e.line: e for e in [*self.doc.directives, *(e for s in self.doc.sections for e in s.entries)]}

    def visible(self, findings: list[Finding]) -> list[Finding]:
        return [f for f in findings if self.show_warnings or f.severity is Severity.ERROR]

    @property
    def dirty(self) -> bool:
        return "\n".join(self.lines) != self.saved

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(id="tabs"):
            with TabPane("Header", id="header"), VerticalScroll():
                yield from header_fields(self.fw, {d.key: d.value for d in self.doc.directives})
            for i, s in enumerate(self.doc.sections):
                with TabPane(s.name, id=f"s{i}"):
                    if s.name == "COMMENT":
                        yield TextArea(body_text(self.lines, s), id=f"text{i}")
                        yield Static("", id=f"textmsg{i}", classes="message", markup=False)
                    else:
                        yield DataTable(id=f"table{i}", cursor_type="row")
            with TabPane("+", id="add"):
                yield Label("Add a section at the end of the file:")
                present = {s.name for s in self.doc.sections}
                yield OptionList(*(name for name in ORDER if name not in present), id="add-list")
        yield DataTable(id="findings", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#findings", DataTable).add_columns(" ", "where", "code", "message")
        self.refresh_views()

    def refresh_views(self) -> None:
        """Tables, tab badges, findings panel and title from self.doc and self.findings."""
        shown = self.visible(self.findings)
        by_line = defaultdict(list)
        for f in shown:
            by_line[f.line].append(f)
        tabs = self.query_one(TabbedContent)
        badges = defaultdict(lambda: [0, 0])
        for f in shown:
            if f.line:
                tab = tab_of(self.doc, f.line)
                badges["header" if tab is None else f"s{tab}"][f.severity is Severity.WARNING] += 1
        labels = {"header": "Header", **{f"s{i}": f"{s.name}({len(s.entries)})" for i, s in enumerate(self.doc.sections)}}
        for tab_id, label in labels.items():
            errors, warnings = badges[tab_id]
            tabs.get_tab(tab_id).label = label + f" ●{errors}" * bool(errors) + f" ○{warnings}" * bool(warnings)
        for i, s in enumerate(self.doc.sections):
            if s.name != "COMMENT":
                self.fill(i, s, by_line)
        self.shown = shown
        table = self.query_one("#findings", DataTable)
        row = table.cursor_row
        table.clear()
        for k, f in enumerate(shown):
            mark = Text("● E", "red") if f.severity is Severity.ERROR else Text("○ W", "yellow")
            table.add_row(mark, self.where(f), f.code, f.message, key=str(k))
        table.move_cursor(row=row)
        self.sub_title = f"{self.path.name}{' *' * self.dirty} — Hapax OS {fw_str(self.fw)}"

    def fill(self, i: int, s: Section, by_line) -> None:
        table = self.query_one(f"#table{i}", DataTable)
        _, columns = SECTIONS[s.name]
        if not table.columns:
            table.add_columns(" ", *(c.label for c in columns), "")
        row = table.cursor_row
        table.clear()
        for n in rows(self.doc, s):
            found = by_line.get(n, [])
            mark = "●" if any(f.severity is Severity.ERROR for f in found) else "○" if found else " "
            entry = self.at.get(n)
            if entry:
                cells = [_cell(getattr(entry, c.field)) for c in columns]
            else:  # a comment line
                cells = [Text(self.lines[n - 1].strip(), "dim"), *[""] * (len(columns) - 1)]
            table.add_row(mark, *cells, found[0].message if found else "", key=str(n))
        table.move_cursor(row=row)

    def where(self, f: Finding) -> str:
        if not f.line:
            return "file"
        tab = tab_of(self.doc, f.line)
        return f"{'header' if tab is None else self.doc.sections[tab].name} line {f.line}"

    def apply(self, lines: list[str], focus: int | None = None) -> None:
        self.lines = lines
        self.analyse()
        self.refresh_views()
        if focus:
            self.focus_row(focus)

    def focus_row(self, n: int | None) -> None:
        tab = tab_of(self.doc, n) if n else None
        if tab is None or self.doc.sections[tab].name == "COMMENT":
            return
        self.query_one(TabbedContent).active = f"s{tab}"
        table = self.query_one(f"#table{tab}", DataTable)
        found = rows(self.doc, self.doc.sections[tab])
        if n in found:
            table.move_cursor(row=found.index(n))
        table.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id and event.input.id.startswith("h-"):
            self.set_header(event.input.id[2:], header_value(event.input))

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id and event.select.id.startswith("h-"):
            self.set_header(event.select.id[2:], header_value(event.select))

    def set_header(self, key: str, value: str | None) -> None:
        current = next((d.value for d in reversed(self.doc.directives) if d.key == key), None)
        # Selects post Changed on mount; only a real change edits, so opening never marks the file unsaved.
        same = current == value if key == "TRACKNAME" else (current or "").upper() == (value or "").upper()
        if not same:
            self.apply(set_directive(self.lines, self.doc, key, value))

    def action_warnings(self) -> None:
        self.show_warnings = not self.show_warnings
        self.refresh_views()
        self.notify(f"warnings {'shown' if self.show_warnings else 'hidden'}")

    def action_save(self) -> None:
        errors = sum(f.severity is Severity.ERROR for f in self.findings)
        if not errors:
            self.write()
            return
        title = f"{errors} error{'s' * (errors != 1)} — the Hapax may reject this file. Save anyway?"
        self.app.push_screen(Dialog(title, [], "Save"), lambda ok: ok and self.write())

    def write(self) -> None:
        text = "\n".join(self.lines)
        try:
            self.path.write_bytes(text.encode("utf-8"))
        except OSError as e:
            self.notify(str(e), severity="error")
            return
        self.saved = text
        self.refresh_views()
        self.notify(f"saved {self.path.name}")

    def action_leave(self) -> None:
        if not self.dirty:
            self.dismiss()
            return
        self.app.push_screen(Dialog("Discard unsaved changes?", [], "Discard"), lambda ok: ok and self.dismiss())
