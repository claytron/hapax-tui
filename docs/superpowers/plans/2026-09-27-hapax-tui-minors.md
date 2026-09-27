# Hapax TUI Review Minors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the five minor findings the TUI's final review deferred: CRLF endings when appending to a file without a final newline, unclear blank-field messages, row keys acting on an unfocused table, saving over refused COMMENT text, and editor options missing from `--help`.

**Architecture:** Each fix is local to one function or two: `edits.insert_line` for line endings, a `required` flag in `sections.Column` read by `RowForm.check`, a focus check in `Editor.current`, a shared `Editor.refused_text` used by `dirty` and `action_save`, and an epilog on the `validate`/`fix` parser.

**Tech Stack:** Python 3.14, uv, Textual 8.2, pytest (pilot tests under `asyncio.run`).

**Spec:** `docs/superpowers/specs/2026-09-27-hapax-tui-design.md`; the findings come from the final review of `docs/superpowers/plans/2026-09-27-hapax-tui.md`.

## Global Constraints

- No new dependencies.
- Work on branch `tui` (the TUI is not merged yet); one commit per task.
- Lines no action touches are written back byte for byte.
- Tests assert codes, lines, exact file text, and which field a message is under; the only message text asserted is the form's own `required`, and the `--help` usage line.
- Run tests with `uv run pytest`; the suite starts at 1613 passing and must stay green after every task.
- New files end with a newline; no trailing whitespace; one sentence per line in Markdown.

## Review Focus

1. `insert_line` at the end of a file that does end with a newline: callers never do this (they insert before the final `""`), and it must stay that way — `add_section` and `set_directive` are the callers to check. Task 1.
2. A `[AUTOMATION]` or `[ASSIGN]` form whose lane type changes after a field went blank: the `required` message must follow the new type (NRPN's MSB may be blank, CC_PAIR's may not). Task 2 pins the flags against the parser for every type; the form reads `type()` on every check.
3. Row keys typed while a row form's Input has focus (`shift+↓`, `d` with modifiers): with Task 3's focus check they do nothing, instead of moving rows under an open form. Task 3.
4. Saving with both errors and refused COMMENT text: one dialog naming both. Task 4.
5. `hapax -h` still exits 0 and still lists `validate` and `fix`. Task 5.

---

### Task 1: CRLF endings when appending to a file without a final newline

**Files:**
- Modify: `hapax/tui/edits.py` (`insert_line`, `add_section`)
- Test: `tests/test_tui_edits.py`

**Interfaces:**
- Consumes: `hapax.write.eol(lines)`.
- Produces: `insert_line(lines, after, text)` and `add_section(lines, name)` with unchanged signatures.

Background for the implementer: `parse` splits on `"\n"`, so a file ending in a newline has `""` as its last line, and a file without one ends in its last real line, which has no `"\r"` even in a CRLF file.
Inserting after that last line must give it the file's ending and leave the new line without one, so the file still has no final newline and every line break is the same.
`add_section` then becomes two `insert_line` calls, so the rule lives in one place.
The fixer's `_close` has the same limitation (its `ponytail:` comment); it is out of scope here.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tui_edits.py`:

```python
def test_inserting_after_a_last_line_without_a_newline_keeps_crlf():
    assert insert_line(["a\r", "b"], 2, "x") == ["a\r", "b\r", "x"]
    assert insert_line(["a", "b"], 2, "x") == ["a", "b", "x"]


def test_add_section_to_a_crlf_file_without_a_final_newline():
    lines = ["VERSION 1\r", "[CC]\r", "[/CC]"]
    assert add_section(lines, "PC") == ["VERSION 1\r", "[CC]\r", "[/CC]\r", "[PC]\r", "[/PC]"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_tui_edits.py -q`
Expected: 2 failed, 23 passed (`['a\r', 'b', 'x\r']` and a mixed-ending section).

- [ ] **Step 3: Fix `insert_line` and route `add_section` through it**

In `hapax/tui/edits.py`, replace `insert_line` with:

```python
def insert_line(lines: list[str], after: int, text: str) -> list[str]:
    """text as a new line after line `after` (0: first)."""
    if after == len(lines):  # after a last line with no newline: it gets one, and text becomes the last line
        return [*lines[:-1], lines[-1].removesuffix("\r") + eol(lines), text]
    return [*lines[:after], text + eol(lines), *lines[after:]]
```

and the body of `add_section` (keep its signature and docstring) with:

```python
    end = len(lines) - (lines[-1] == "")
    return insert_line(insert_line(lines, end, f"[{name}]"), end + 1, f"[/{name}]")
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest -q`
Expected: PASS, 1615 tests.

- [ ] **Step 5: Commit**

```bash
git add hapax/tui/edits.py tests/test_tui_edits.py
git commit -m "Keep CRLF endings when appending to a file without a final newline"
```

---

### Task 2: Name a blank required field under the field

**Files:**
- Modify: `hapax/tui/sections.py` (`Column`, new `required`, `_target`, `NAME`, `SECTIONS`)
- Modify: `hapax/tui/editor.py` (`RowForm.check`, the `.sections` import)
- Test: `tests/test_tui_sections.py`, `tests/test_tui_app.py`

**Interfaces:**
- Consumes: `edits.row_text`, `parse.parse`; `RowForm.type()`, `RowForm.values()`.
- Produces: `Column.required: bool | frozenset[str]` (default `False`) and `sections.required(column, kind: str | None) -> bool`.

Background for the implementer: a blank field renders as nothing or as `None`, so a blank required field gives a `syntax` finding.
That finding is what refuses the edit, and it must keep doing so, but its message ("expected ':' or a space, found end of line") is the parser's, and it shows under the row.
The form now puts `required` under each blank required field and hides the `syntax` messages for that line while any required field is blank.
Which fields are required is declared per column and pinned by a test that blanks each field in turn and checks the parser agrees, for every section and lane type.
The one type-dependent case is the lane's MSB: `NRPN::2000:7` may omit it, `CC_PAIR:1:33` may not.

- [ ] **Step 1: Write the failing tests**

In `tests/test_tui_sections.py`, change the imports to:

```python
from hapax.parse import Directive, Severity, parse
from hapax.rules import RELEASES, _directive, parse_fw
from hapax.tui.edits import row_text
from hapax.tui.sections import HEADER, SECTIONS, TEXT, header_choices, required
```

and append:

```python
def _kinds(columns):
    """The lane types a section's form can show, or [None] for a section without them."""
    return next((c.choices for c in columns if c.field == "type"), [None])


@pytest.mark.parametrize("name", SECTIONS)
def test_required_marks_exactly_the_fields_a_line_cannot_leave_blank(name):
    cls, columns = SECTIONS[name]
    for kind in _kinds(columns):
        shown = [c for c in columns if c.types is None or kind in c.types]
        filled = {c.field: "" for c in columns} | {
            c.field: kind if c.field == "type" else "X" if c.restrict == TEXT else "1" for c in shown}
        for c in shown:
            if c.field == "type":
                continue
            text = row_text(cls, None, filled | {c.field: ""})
            syntax = any(f.code == "syntax" for f in parse(f"[{name}]\n{text}\n[/{name}]").parse_findings)
            assert syntax == required(c, kind), (kind, c.field, text)
```

Append to `tests/test_tui_app.py`:

```python
def test_a_blank_required_field_is_named_under_the_field(tmp_path):
    path = write(tmp_path, "Small.txt", SMALL)

    async def script(app, pilot):
        editor = app.screen
        editor.query_one(TabbedContent).active = "s0"
        await pilot.pause()
        editor.query_one("#table0", DataTable).focus()
        await pilot.press("a")
        await pilot.pause()
        editor.query_one("#f-cc", Input).value = "76"
        await pilot.pause()
        assert str(editor.query_one("#m-name").render()) == "required"
        assert str(editor.query_one("#m-row").render()) == ""  # not the parser's "expected …"

    drive(path, script)
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_tui_sections.py tests/test_tui_app.py -q -k "required"`
Expected: FAIL with `ImportError: cannot import name 'required'` (collection error in `test_tui_sections.py`).
Then `uv run pytest tests/test_tui_app.py -q -k blank_required` — Expected: FAIL, `assert '' == 'required'`.

- [ ] **Step 3: Declare required columns**

In `hapax/tui/sections.py`, add a field to `Column` after `types`, and the function after the class:

```python
    required: bool | frozenset[str] = False  # blank makes the line unparseable; a set: only for those types


def required(column: Column, kind: str | None) -> bool:
    """Whether the form must refuse this field blank, for the lane type `kind` (None outside [ASSIGN]/[AUTOMATION])."""
    return column.required if isinstance(column.required, bool) else kind in column.required
```

In `_target`, replace the `cc`, `msb`, `lsb`, `depth` and `cv` columns with:

```python
        Column("cc", "CC", types=only("CC"), required=True),
        Column("msb", "MSB", types=only("NRPN", "CC_PAIR"), required=only("CC_PAIR")),  # NRPN::2000:7 omits it
        Column("lsb", "LSB", types=only("NRPN", "CC_PAIR"), required=True),
        Column("depth", "DEPTH", types=only("NRPN"), required=True),
        Column("cv", "CV", types=only("CV"), required=True),
```

Replace `NAME` and the `SECTIONS` entries from `"CC"` through `"ASSIGN"` with:

```python
NAME = Column("name", "NAME", TEXT, required=True)
DEFAULT = Column("default", "DEFAULT")
SECTIONS = {
    "CC": (CcEntry, (Column("cc", "CC", required=True), DEFAULT, NAME)),
    "PC": (PcEntry, (Column("pc", "PC", required=True), Column("msb", "MSB"), Column("lsb", "LSB"), NAME)),
    "CC_PAIR": (CcPairEntry, (
        Column("msb", "MSB CC", required=True), Column("lsb", "LSB CC", required=True), DEFAULT, NAME)),
    "NRPN": (NrpnEntry, (
        Column("msb", "MSB"), Column("lsb", "LSB", required=True), Column("depth", "DEPTH", required=True), DEFAULT,
        NAME)),
    "DRUMLANES": (DrumEntry, (
        Column("row", "ROW", required=True), Column("trig", "TRIG"), Column("chan", "CHAN", PORT),
        Column("note", "NOTE"), NAME)),
    "ASSIGN": (AssignEntry, (
        Column("pot", "POT", required=True), *_target(("CC", "NRPN", "CC_PAIR", "CV", "PB", "AT", "NULL")))),
```

(`"AUTOMATION"` and the closing `}` stay as they are.)

Run: `uv run pytest tests/test_tui_sections.py -q`
Expected: PASS, 155 tests.

- [ ] **Step 4: Show `required` in the form**

In `hapax/tui/editor.py`, change the sections import to:

```python
from .sections import COMMENT, HEADER, ORDER, SECTIONS, required
```

In `RowForm.check`, replace:

```python
        messages = defaultdict(list)
        for f in self.editor.visible([f for f in found if f.line == n]):
            shown = f.field if any(c.field == f.field for c in self.columns) else "row"
            messages[shown].append(f.message)
```

with:

```python
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
```

`check` still returns `broken`, which holds the `syntax` finding, so `enter` is still refused.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest -q`
Expected: PASS, 1623 tests.

- [ ] **Step 6: Commit**

```bash
git add hapax/tui/sections.py hapax/tui/editor.py tests/test_tui_sections.py tests/test_tui_app.py
git commit -m "Say which required field is blank, under the field"
```

---

### Task 3: Row keys act only on a focused table

**Files:**
- Modify: `hapax/tui/editor.py` (`Editor.current`)
- Test: `tests/test_tui_app.py`

**Interfaces:**
- Consumes: `Editor.current()`, used by `action_add`, `action_delete` and `action_move`.
- Produces: `Editor.current()` returns `None` unless the active section's table has focus.

Background for the implementer: `a`, `d` and `ctrl`/`shift`+arrows are screen bindings, so they fire whenever the focused widget does not consume the key: the findings panel, a Select, or an Input (for `shift+↓`).
They act on the active tab's cursor row, which the author may not be looking at.
Requiring the table's focus in `current()` covers all three actions at once.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tui_app.py`:

```python
def test_row_keys_act_only_when_the_table_has_focus(tmp_path):
    path = write(tmp_path, "Small.txt", SMALL)

    async def script(app, pilot):
        editor = app.screen
        editor.query_one(TabbedContent).active = "s0"
        await pilot.pause()
        editor.query_one("#findings").focus()
        await pilot.press("d", "shift+down", "a")
        await pilot.pause()
        assert app.screen is editor and not editor.query(RowForm)
        assert editor.lines == SMALL.split("\n")

    drive(path, script)
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_tui_app.py -q -k table_has_focus`
Expected: FAIL, `assert (Dialog() is Editor())` (the delete dialog opened).

- [ ] **Step 3: Check focus in `current`**

In `hapax/tui/editor.py`, replace `Editor.current` with:

```python
    def current(self) -> tuple[int, DataTable] | None:
        """The active section tab's index and table, if it has one and it has focus: row keys act on what is focused."""
        active = self.query_one(TabbedContent).active
        if not active.startswith("s") or self.doc.sections[int(active[1:])].name == "COMMENT":
            return None
        table = self.query_one(f"#table{active[1:]}", DataTable)
        return (int(active[1:]), table) if table.has_focus else None
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest -q`
Expected: PASS, 1624 tests.

- [ ] **Step 5: Commit**

```bash
git add hapax/tui/editor.py tests/test_tui_app.py
git commit -m "Act on rows only from a focused table"
```

---

### Task 4: Ask before saving over refused COMMENT text

**Files:**
- Modify: `hapax/tui/editor.py` (`Editor.dirty`, new `Editor.refused_text`, `Editor.action_save`)
- Test: `tests/test_tui_app.py`

**Interfaces:**
- Consumes: `edits.body_text`; `dialogs.Dialog`.
- Produces: `Editor.refused_text() -> bool`.

Background for the implementer: when text typed into a COMMENT section would break the file, the lines keep their last good text and the text area keeps what was typed.
`dirty` already counts that as unsaved (so leaving asks); `ctrl+s` still wrote silently, saving text other than what is on screen.
Saving now asks when that is so, in the same dialog as the errors question; with errors alone the title is unchanged: `N errors — the Hapax may reject this file. Save anyway?`.
Once any change to the text area applies, `set_body` takes the whole text, so later keystrokes are not lost; nothing else changes there.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tui_app.py`:

```python
def test_saving_with_refused_comment_text_asks(tmp_path):
    path = write(tmp_path, "Note.txt", "VERSION 1\n[COMMENT]\nHello\n[/COMMENT]\n")

    async def script(app, pilot):
        editor = app.screen
        editor.query_one("#text0", TextArea).text = "Hi\n[CC]"
        await pilot.pause()
        editor.query_one("#findings").focus()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.screen, Dialog)

    drive(path, script)
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_tui_app.py -q -k refused_comment_text_asks`
Expected: FAIL, `assert False` (no dialog; the file is written).

- [ ] **Step 3: Share the check and ask on save**

In `hapax/tui/editor.py`, replace the body of the `dirty` property and add `refused_text` after it:

```python
    def dirty(self) -> bool:
        return "\n".join(self.lines) != self.saved or self.refused_text()

    def refused_text(self) -> bool:
        """Whether a COMMENT text area shows a refused edit: text that saving would not write."""
        return any(
            area.text != body_text(self.lines, self.doc.sections[int(area.id[4:])]) for area in self.query(TextArea))
```

(Keep the `@property` decorator on `dirty`.)

Replace the body of `action_save` with:

```python
        errors = sum(f.severity is Severity.ERROR for f in self.findings)
        problems = [f"{errors} error{'s' * (errors != 1)} — the Hapax may reject this file."] * bool(errors) + [
            "The COMMENT text shown would break the file; its last text that did not is saved instead."
        ] * self.refused_text()
        if not problems:
            self.write()
            return
        self.app.push_screen(Dialog(" ".join(problems) + " Save anyway?", [], "Save"), lambda ok: ok and self.write())
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest -q`
Expected: PASS, 1625 tests.

- [ ] **Step 5: Commit**

```bash
git add hapax/tui/editor.py tests/test_tui_app.py
git commit -m "Ask before saving over refused COMMENT text"
```

---

### Task 5: Show the editor's usage in `hapax --help`

**Files:**
- Modify: `hapax/cli.py` (the `ArgumentParser` in `main`)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: an epilog on the top-level parser.

Background for the implementer: `-h` and `--help` go to the `validate`/`fix` parser, because the editor's parser lives in `hapax/tui/app.py` and importing it loads Textual.
A static epilog names the editor's usage instead; `RawDescriptionHelpFormatter` keeps its line breaks.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_help_shows_how_to_open_the_editor(capsys):
    assert run(["--help"]) == 0
    assert "hapax [--fw VERSION] [--[no-]warn] [PATH]" in capsys.readouterr().out
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_cli.py -q -k help`
Expected: FAIL, the usage line is not in the help output.

- [ ] **Step 3: Add the epilog**

In `hapax/cli.py`, replace:

```python
    parser = argparse.ArgumentParser(
        prog="hapax", description="Squarp Hapax instrument definition tools; with no command, the editor")
```

with:

```python
    parser = argparse.ArgumentParser(
        prog="hapax", description="Squarp Hapax instrument definition tools; with no command, the editor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(  # the editor parses its own options (tui/app.py), so they are not arguments here
            "editor:\n"
            "  hapax [--fw VERSION] [--[no-]warn] [PATH]\n"
            "  PATH: a directory to browse (default: .), a file to edit, or a new file to create"))
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest -q`
Expected: PASS, 1626 tests.
Run: `uv run hapax --help`
Expected: the `validate` and `fix` commands as before, then the `editor:` block.

- [ ] **Step 5: Commit**

```bash
git add hapax/cli.py tests/test_cli.py
git commit -m "Show the editor's usage in hapax --help"
```
