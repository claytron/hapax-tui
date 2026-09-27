"""The editor: a header form, a table per section, a row form, and the findings panel.

Every action edits self.lines, then re-parses and re-validates everything from them (edits.analyse).
"""

from collections import defaultdict
from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    DataTable, Footer, Header, Input, Label, OptionList, Select, Static, TabbedContent, TabPane, Tabs, TextArea,
)

from ..parse import Directive, Entry, Finding, Section, Severity
from ..rules import check_file_name, fw_str
from .dialogs import Dialog, header_fields, header_value
from .edits import (
    add_row, add_section, analyse, body_text, breaks, comment_text, comment_value, delete_line, move_row, row_text,
    rows, set_body, set_directive, set_line, tab_of,
)
from .sections import COMMENT, HEADER, ORDER, SECTIONS, required


def _cell(value) -> str:
    return "—" if value is None else str(value)


class RowForm(Vertical):
    """Edits one row, or adds one; every change is rendered and validated in place."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, section: Section, n: int | None, adding: bool, editor: "Editor"):
        super().__init__(id="form")
        self.section, self.n, self.adding, self.editor = section, n, adding, editor
        self.cls, columns = SECTIONS[section.name]
        self.original: Entry | None = None if adding else editor.at.get(n)
        self.comment = not adding and self.original is None  # a "# ..." row
        self.columns = (COMMENT,) if self.comment else columns

    def initial(self, field: str) -> str:
        if self.comment:
            return comment_value(self.editor.lines[self.n - 1])
        if self.original is None:
            return "CC" if field == "type" else ""
        value = getattr(self.original, field)
        return "" if value is None else str(value)

    def compose(self) -> ComposeResult:
        with Horizontal():
            for c in self.columns:
                with Vertical(id=f"c-{c.field}", classes="column"):
                    yield Label(c.label)
                    value = self.initial(c.field)
                    if c.choices:
                        choices = c.choices if value in c.choices else (*c.choices, value)
                        yield Select([(x, x) for x in choices], value=value, allow_blank=False, id=f"f-{c.field}")
                    else:
                        yield Input(value, id=f"f-{c.field}", restrict=c.restrict)
                    yield Static("", id=f"m-{c.field}", classes="message", markup=False)
        yield Static("", id="m-row", classes="message", markup=False)

    def on_mount(self) -> None:
        self.show_types()
        self.check()

    def type(self) -> str | None:
        return str(self.query_one("#f-type", Select).value) if any(c.field == "type" for c in self.columns) else None

    def show_types(self) -> None:
        kind = self.type()
        for c in self.columns:
            self.query_one(f"#c-{c.field}").display = c.types is None or kind in c.types

    def values(self) -> dict[str, str]:
        kind = self.type()
        return {
            c.field: str(self.query_one(f"#f-{c.field}").value) if c.types is None or kind in c.types else ""
            for c in self.columns
        }

    def candidate(self) -> tuple[list[str], int]:
        lines = self.editor.lines
        if self.comment:
            return set_line(lines, self.n, comment_text(lines[self.n - 1], self.values()["text"])), self.n
        text = row_text(self.cls, self.original, self.values())
        if self.adding:
            return add_row(lines, self.section, self.n, text)
        return set_line(lines, self.n, text), self.n

    def check(self) -> list[Finding]:
        """Show the candidate's findings under their fields; return what would break the file."""
        lines, n = self.candidate()
        _, found = analyse(lines, self.editor.fw)
        broken = breaks(self.editor.findings, found)
        kind, values = self.type(), self.values()
        blank = [
            c.field for c in self.columns
            if (c.types is None or kind in c.types) and required(c, kind) and not values[c.field].strip()]
        messages = defaultdict(list, {field: ["required"] for field in blank})
        for f in self.editor.visible([f for f in found if f.line == n]):
            if blank and f.code == "syntax":
                continue  # the parser's view of the blank field, said plainly above
            shown = f.field if any(c.field == f.field for c in self.columns) else "row"
            messages[shown].append(f.message)
        messages["row"] += [f"cannot apply: {f.message}" for f in broken if f.line != n]
        for c in (*self.columns, None):
            key = c.field if c else "row"
            self.query_one(f"#m-{key}", Static).update("\n".join(messages[key]))
        return broken

    def on_select_changed(self, event: Select.Changed) -> None:
        event.stop()
        self.show_types()
        self.check()

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self.check()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        if self.check():
            return
        lines, n = self.candidate()
        self.remove()
        self.editor.apply(lines, n)

    def action_cancel(self) -> None:
        self.remove()
        self.editor.focus_row(self.n)


class Editor(Screen):
    BINDINGS = [
        Binding("ctrl+s", "save", "Save"),
        Binding("w", "warnings", "Warnings"),
        Binding("a", "add", "Add row"),
        Binding("d", "delete", "Delete row"),
        Binding("ctrl+up,shift+up", "move(-1)", "Move up"),  # macOS takes ctrl+arrows for Mission Control
        Binding("ctrl+down,shift+down", "move(1)", "Move down"),
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
        return "\n".join(self.lines) != self.saved or self.refused_text()

    def refused_text(self) -> bool:
        """Whether a COMMENT text area shows a refused edit: text that saving would not write."""
        return any(
            area.text != body_text(self.lines, self.doc.sections[int(area.id[4:])]) for area in self.query(TextArea))

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
        self.query(RowForm).remove()  # an open form's line number may now name another row
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

    def current(self) -> tuple[int, DataTable] | None:
        """The active section tab's index and table, unless focus is on another widget (a form, the findings panel)."""
        active = self.query_one(TabbedContent).active
        if not active.startswith("s") or self.doc.sections[int(active[1:])].name == "COMMENT":
            return None
        table = self.query_one(f"#table{active[1:]}", DataTable)
        # Switching tabs leaves focus on the tab bar, and adding a section leaves it nowhere; both mean this table.
        return (int(active[1:]), table) if self.focused in (None, table) or isinstance(self.focused, Tabs) else None

    def cursor_line(self, i: int, table: DataTable) -> int | None:
        found = rows(self.doc, self.doc.sections[i])
        return found[table.cursor_row] if found else None

    async def open_form(self, i: int, n: int | None, adding: bool, field: str | None = None) -> None:
        await self.close_form()
        form = RowForm(self.doc.sections[i], n, adding, self)
        await self.query_one(f"#s{i}", TabPane).mount(form)
        target = form.query(f"#f-{field}") if field else form.query("Input")
        (target.first() if target else form.query("Input, Select").first()).focus()

    async def close_form(self) -> None:
        await self.query("#form").remove()

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        table_id = event.data_table.id or ""
        if table_id == "findings":
            await self.jump(self.shown[int(event.row_key.value)])
        elif table_id.startswith("table"):
            await self.open_form(int(table_id[5:]), int(event.row_key.value), adding=False)

    async def jump(self, f: Finding) -> None:
        """Show a finding where it is: its tab, its row, and the form field it names."""
        tab = tab_of(self.doc, f.line) if f.line else None
        tabs = self.query_one(TabbedContent)
        if f.line and tab is None:
            tabs.active = "header"
            entry = self.at.get(f.line)
            if isinstance(entry, Directive) and entry.key in HEADER:
                self.query_one(f"#h-{entry.key}").focus()
        elif tab is not None and self.doc.sections[tab].name == "COMMENT":
            tabs.active = f"s{tab}"
            area = self.query_one(f"#text{tab}", TextArea)
            area.focus()
            area.move_cursor((f.line - self.doc.sections[tab].start - 1, 0))
        elif tab is not None:
            self.focus_row(f.line)
            if f.field and f.line in self.at:
                await self.open_form(tab, f.line, adding=False, field=f.field)

    async def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        # A form's line numbers belong to its tab. A jump activates the tab and opens the form before this arrives.
        for form in self.query(RowForm):
            if form.parent is not event.pane:
                await form.remove()

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

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        i = int(event.text_area.id[4:])
        new = set_body(self.lines, self.doc.sections[i], event.text_area.text)
        if new == self.lines:
            return
        broken = breaks(self.findings, analyse(new, self.fw)[1])
        self.query_one(f"#textmsg{i}", Static).update(f"not applied: {broken[0].message}" if broken else "")
        if not broken:
            self.apply(new)

    async def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.lines = add_section(self.lines, str(event.option.prompt))
        self.analyse()
        await self.recompose()
        self.on_mount()
        self.query_one(TabbedContent).active = f"s{len(self.doc.sections) - 1}"

    async def action_add(self) -> None:
        if current := self.current():
            i, table = current
            await self.open_form(i, self.cursor_line(i, table), adding=True)

    def action_delete(self) -> None:
        if not (current := self.current()) or (n := self.cursor_line(*current)) is None:
            return

        def delete(ok: bool | None) -> None:
            if ok:
                self.apply(delete_line(self.lines, n))

        self.app.push_screen(Dialog(f"Delete line {n}?", [self.lines[n - 1].strip()], "Delete"), delete)

    def action_move(self, step: int) -> None:
        if not (current := self.current()) or (n := self.cursor_line(*current)) is None:
            return
        i, _ = current
        if moved := move_row(self.lines, self.doc, self.doc.sections[i], n, step):
            self.apply(*moved)

    def action_warnings(self) -> None:
        self.show_warnings = not self.show_warnings
        self.refresh_views()
        self.notify(f"warnings {'shown' if self.show_warnings else 'hidden'}")

    def action_save(self) -> None:
        errors = sum(f.severity is Severity.ERROR for f in self.findings)
        problems = [f"{errors} error{'s' * (errors != 1)} — the Hapax may reject this file."] * bool(errors) + [
            "The COMMENT text shown would break the file; its last text that did not is saved instead."
        ] * self.refused_text()
        if not problems:
            self.write()
            return
        self.app.push_screen(Dialog(" ".join(problems) + " Save anyway?", [], "Save"), lambda ok: ok and self.write())

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
