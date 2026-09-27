import asyncio
import shutil
from pathlib import Path

from textual.widgets import DataTable, Input, Select, TabbedContent, TextArea

from hapax import LATEST, Severity, parse, validate
from hapax.tui.app import HapaxApp
from hapax.tui.browser import Browser
from hapax.tui.dialogs import Dialog, NewFile
from hapax.tui.editor import Editor, RowForm

PEAK = Path(__file__).parent / "testdata" / "mine" / "Novation_Peak.txt"
SMALL = """\
VERSION 1
TRACKNAME Synth
OUTCHAN 1
[CC]
74 Cutoff # filter
# envelope
130 Big
75 A very long parameter name
[/CC]
[COMMENT]
Hello
[/COMMENT]
"""


def drive(path: Path, script, fw=LATEST, warn=True):
    """Run the app on path headless and hand a pilot to script."""
    async def go():
        app = HapaxApp(path, fw, warn)
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            await script(app, pilot)
    asyncio.run(go())


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_bytes(text.encode("utf-8"))
    return path


def test_a_directory_lists_its_files_with_status(tmp_path):
    write(tmp_path, "Good.txt", "VERSION 1\n")
    write(tmp_path, "Bad.txt", "VERSION 1\nOUTCHAN 17\n")

    async def script(app, pilot):
        assert isinstance(app.screen, Browser)
        table = app.screen.query_one(DataTable)
        assert [table.get_row_at(i) for i in range(table.row_count)] == [["Bad.txt", "1E"], ["Good.txt", "OK"]]

    drive(tmp_path, script)


def test_the_gate_offers_fixes_and_the_editor_starts_unsaved(tmp_path):
    path = write(tmp_path, "Bom.txt", "﻿VERSION 1\n")

    async def script(app, pilot):
        assert isinstance(app.screen, Dialog)
        await pilot.click("#yes")
        await pilot.pause()
        assert isinstance(app.screen, Editor) and app.screen.dirty

    drive(path, script)
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")  # nothing written until save


def test_the_gate_refuses_a_syntax_error(tmp_path):
    path = write(tmp_path, "Broken.txt", "VERSION 1\n[CC]\n74\n[/CC]\n")

    async def script(app, pilot):
        assert isinstance(app.screen, Dialog) and app.screen.yes is None
        await pilot.click("#no")
        await pilot.pause()
        assert isinstance(app.screen, Browser)

    drive(path, script)


def test_w_hides_and_shows_warnings(tmp_path):
    path = write(tmp_path, "Small.txt", SMALL)

    async def script(app, pilot):
        editor = app.screen
        findings = editor.query_one("#findings", DataTable)
        findings.focus()
        both = findings.row_count
        await pilot.press("w")
        assert findings.row_count == 1  # the CC 130 range error
        assert all(f.severity is Severity.ERROR for f in editor.shown)
        await pilot.press("w")
        assert findings.row_count == both

    drive(path, script)


def test_a_header_value_that_is_not_a_choice_shows_and_does_not_dirty(tmp_path):
    path = write(tmp_path, "Chan.txt", "VERSION 1\noutchan 17\ntype poly\n")

    async def script(app, pilot):
        editor = app.screen
        assert editor.query_one("#h-OUTCHAN", Select).value == "17"
        assert editor.query_one("#h-TYPE", Select).value == "POLY"
        assert not editor.dirty
        editor.query_one("#h-OUTCHAN", Select).value = "3"
        await pilot.pause()
        assert editor.lines[1] == "OUTCHAN 3"

    drive(path, script)


def test_saving_with_errors_asks_first(tmp_path):
    path = write(tmp_path, "Chan.txt", "VERSION 1\nOUTCHAN 17\nTRACKNAME Old\n")

    async def script(app, pilot):
        editor = app.screen
        editor.query_one("#h-TRACKNAME", Input).value = "New"
        await pilot.pause()
        await pilot.press("ctrl+s")
        assert isinstance(app.screen, Dialog)  # OUTCHAN 17
        await pilot.click("#yes")
        await pilot.pause()
        assert not editor.dirty

    drive(path, script)
    assert path.read_text() == "VERSION 1\nOUTCHAN 17\nTRACKNAME New\n"


def test_leaving_with_unsaved_changes_asks(tmp_path):
    path = write(tmp_path, "Small.txt", SMALL)

    async def script(app, pilot):
        editor = app.screen
        editor.query_one("#h-OUTCHAN", Select).value = "3"
        await pilot.pause()
        editor.query_one("#findings").focus()
        await pilot.press("escape")
        assert isinstance(app.screen, Dialog)
        await pilot.click("#yes")
        await pilot.pause()
        assert isinstance(app.screen, Browser)

    drive(path, script)
    assert path.read_text() == SMALL


def test_quitting_with_unsaved_changes_asks(tmp_path):
    path = write(tmp_path, "Small.txt", SMALL)

    async def script(app, pilot):
        app.screen.query_one("#h-OUTCHAN", Select).value = "3"
        await pilot.pause()
        await pilot.press("ctrl+q")
        await pilot.pause()
        assert isinstance(app.screen, Dialog)
        await pilot.click("#no")
        await pilot.pause()
        assert isinstance(app.screen, Editor)

    drive(path, script)


def test_editing_a_name_and_saving_changes_only_that_line(tmp_path):
    path = tmp_path / PEAK.name
    shutil.copy(PEAK, path)
    before = path.read_bytes().decode().split("\n")

    async def script(app, pilot):
        editor = app.screen
        assert isinstance(editor, Editor) and not editor.dirty
        cc = next(i for i, s in enumerate(editor.doc.sections) if s.name == "CC")
        editor.query_one(TabbedContent).active = f"s{cc}"
        await pilot.pause()
        table = editor.query_one(f"#table{cc}", DataTable)
        table.focus()
        table.move_cursor(row=1)
        await pilot.press("enter")
        await pilot.pause()
        name = editor.query_one("#f-name", Input)
        name.value = "Renamed"
        name.focus()
        await pilot.press("enter")
        await pilot.pause()
        assert not editor.query(RowForm)
        await pilot.press("ctrl+s")
        await pilot.pause()

    drive(path, script)
    after = path.read_bytes().decode().split("\n")
    changed = [n for n, (a, b) in enumerate(zip(before, after)) if a != b]
    assert len(before) == len(after) and len(changed) == 1
    assert after[changed[0]].split(" ", 1)[1] == "Renamed"


def test_selecting_a_finding_opens_its_row_at_its_field(tmp_path):
    path = write(tmp_path, "Small.txt", SMALL)

    async def script(app, pilot):
        editor = app.screen
        findings = editor.query_one("#findings", DataTable)
        findings.focus()
        findings.move_cursor(row=next(k for k, f in enumerate(editor.shown) if f.code == "cc.range"))
        await pilot.press("enter")
        await pilot.pause()
        assert editor.query_one(TabbedContent).active == "s0"
        assert editor.query_one("#table0", DataTable).cursor_row == 2  # 74, the comment, 130
        assert app.focused.id == "f-cc"

    drive(path, script)


def test_a_row_form_refuses_a_blank_name(tmp_path):
    path = write(tmp_path, "Small.txt", SMALL)

    async def script(app, pilot):
        editor = app.screen
        editor.query_one(TabbedContent).active = "s0"
        await pilot.pause()
        editor.query_one("#table0", DataTable).focus()
        await pilot.press("a")
        await pilot.pause()
        editor.query_one("#f-cc", Input).value = "76"
        editor.query_one("#f-name", Input).focus()
        await pilot.press("enter")
        await pilot.pause()
        assert editor.query(RowForm) and not editor.dirty
        await pilot.press(*"Env #2")
        assert editor.query_one("#f-name", Input).value == "Env 2"
        await pilot.press("enter")
        await pilot.pause()
        assert editor.lines[5] == "76 Env 2"

    drive(path, script)


def test_moving_and_deleting_rows(tmp_path):
    path = write(tmp_path, "Small.txt", SMALL)

    async def script(app, pilot):
        editor = app.screen
        editor.query_one(TabbedContent).active = "s0"
        await pilot.pause()
        editor.query_one("#table0", DataTable).focus()
        await pilot.press("shift+down")
        assert editor.lines[4:6] == ["# envelope", "74 Cutoff # filter"]
        await pilot.press("d")
        await pilot.click("#yes")
        await pilot.pause()
        assert "74 Cutoff # filter" not in editor.lines

    drive(path, script)


def test_a_comment_section_refuses_text_that_closes_it(tmp_path):
    path = write(tmp_path, "Small.txt", SMALL)

    async def script(app, pilot):
        editor = app.screen
        area = editor.query_one("#text1", TextArea)
        area.text = "Hi\n[/COMMENT]"
        await pilot.pause()
        assert editor.lines[10] == "Hello"
        area.text = "Hi there"
        await pilot.pause()
        assert editor.lines[10] == "Hi there"

    drive(path, script)


def test_adding_a_section(tmp_path):
    path = write(tmp_path, "Small.txt", SMALL)

    async def script(app, pilot):
        editor = app.screen
        editor.query_one(TabbedContent).active = "add"
        await pilot.pause()
        editor.query_one("#add-list").focus()
        await pilot.press("enter")  # PC, the first missing section
        await pilot.pause()
        assert editor.lines[-3:] == ["[PC]", "[/PC]", ""]
        assert editor.query_one(TabbedContent).active == "s2"

    drive(path, script)


def test_a_new_file_validates_without_errors(tmp_path):
    write(tmp_path, "Peak.txt", "VERSION 1\n")

    async def script(app, pilot):
        dialog = app.screen
        assert isinstance(dialog, NewFile)
        assert dialog.query_one("#name", Input).value == "New Synth"
        dialog.query_one("#h-TYPE", Select).value = "POLY"
        dialog.query_one("#h-OUTCHAN", Select).value = "1"
        dialog.query_one("#h-TRACKNAME", Input).value = "Synth"
        await pilot.click("#create")
        await pilot.pause()
        assert isinstance(app.screen, Editor)

    drive(tmp_path / "New Synth", script)
    text = (tmp_path / "New Synth.txt").read_text()
    assert text == "VERSION 1\nTRACKNAME Synth\nTYPE POLY\nOUTCHAN 1\n"
    assert [f for f in validate(parse(text)) if f.severity is Severity.ERROR] == []


def test_a_new_file_refuses_an_existing_name(tmp_path):
    write(tmp_path, "Peak.txt", "VERSION 1\n")

    async def script(app, pilot):
        app.screen.query_one("#name", Input).value = "peak"  # SD cards ignore case
        await pilot.click("#create")
        await pilot.pause()
        assert isinstance(app.screen, NewFile)
        assert "already exists" in str(app.screen.query_one("#problem").render())

    drive(tmp_path / "Other.txt", script)


def test_an_open_row_form_closes_when_another_edit_moves_its_line(tmp_path):
    path = write(tmp_path, "Small.txt", SMALL)

    async def script(app, pilot):
        editor = app.screen
        editor.query_one(TabbedContent).active = "s0"
        await pilot.pause()
        table = editor.query_one("#table0", DataTable)
        table.focus()
        table.move_cursor(row=2)  # 130 Big
        await pilot.press("enter")
        await pilot.pause()
        table.focus()
        table.move_cursor(row=0)
        await pilot.press("d")
        await pilot.click("#yes")
        await pilot.pause()
        assert not editor.query(RowForm)  # its line number now names another row

    drive(path, script)


def test_quitting_from_a_dialog_over_unsaved_changes_asks(tmp_path):
    path = write(tmp_path, "Small.txt", SMALL)

    async def script(app, pilot):
        editor = app.screen
        editor.query_one("#h-OUTCHAN", Select).value = "3"
        await pilot.pause()
        editor.query_one(TabbedContent).active = "s0"
        await pilot.pause()
        editor.query_one("#table0", DataTable).focus()
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("ctrl+q")
        await pilot.pause()
        assert app.is_running
        assert isinstance(app.screen, Dialog) and app.screen.yes == "Quit"

    drive(path, script)


def test_a_refused_comment_edit_counts_as_unsaved(tmp_path):
    path = write(tmp_path, "Small.txt", SMALL)

    async def script(app, pilot):
        editor = app.screen
        editor.query_one("#text1", TextArea).text = "Hi\n[/COMMENT]"
        await pilot.pause()
        assert editor.lines[10] == "Hello"
        assert editor.dirty  # the text on screen is not what would be saved

    drive(path, script)


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


def test_a_adds_a_row_right_after_switching_tabs_or_adding_a_section(tmp_path):
    path = write(tmp_path, "Small.txt", SMALL)

    async def script(app, pilot):
        editor = app.screen
        editor.query_one(TabbedContent).active = "s0"  # focus stays on the tab bar
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        assert editor.query(RowForm)
        await pilot.press("escape")
        editor.query_one(TabbedContent).active = "add"
        await pilot.pause()
        editor.query_one("#add-list").focus()
        await pilot.press("enter")  # adds [PC]; focus goes nowhere
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        assert editor.query(RowForm)

    drive(path, script)
