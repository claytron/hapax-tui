import asyncio
from pathlib import Path

from textual.widgets import DataTable, Input, Select

from hapax import LATEST, Severity
from hapax.tui.app import HapaxApp
from hapax.tui.browser import Browser
from hapax.tui.dialogs import Dialog
from hapax.tui.editor import Editor

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
