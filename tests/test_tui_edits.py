from hapax import LATEST, parse
from hapax.parse import AutomationEntry, CcEntry, DrumEntry, Finding, Severity
from hapax.tui.edits import (
    add_row, add_section, analyse, body_text, breaks, comment_text, comment_value, delete_line, insert_line,
    move_row, new_file_path, new_file_text, open_text, row_text, rows, set_body, set_directive, set_line, tab_of,
)

TEXT = """\
VERSION 1
TRACKNAME Synth
[CC]
74 Cutoff # filter

# envelope
75 Reso
[/CC]
[COMMENT]
Hello
[/COMMENT]
"""


def lines(text=TEXT):
    return text.split("\n")


def section(ls, name):
    return next(s for s in parse("\n".join(ls)).sections if s.name == name)


def test_rows_are_the_non_blank_lines_between_the_tags():
    doc = parse(TEXT)
    assert rows(doc, doc.sections[0]) == [4, 6, 7]


def test_tab_of():
    doc = parse(TEXT)
    assert [tab_of(doc, n) for n in (0, 1, 3, 5, 8, 10)] == [None, None, 0, 0, 0, 1]


def test_set_line_keeps_the_line_ending():
    assert set_line(["a\r", "b\r"], 1, "x") == ["x\r", "b\r"]
    assert set_line(["a", "b"], 2, "x\r") == ["a", "x"]


def test_inserted_lines_follow_crlf():
    assert insert_line(["a\r", "b\r", ""], 1, "x") == ["a\r", "x\r", "b\r", ""]
    assert insert_line(["a", ""], 0, "x") == ["x", "a", ""]


def test_delete_line():
    assert delete_line(["a", "b", "c"], 2) == ["a", "c"]


def test_move_row_swaps_rows_and_skips_blank_lines():
    ls = lines()
    doc = parse(TEXT)
    moved, n = move_row(ls, doc, doc.sections[0], 4, 1)
    assert n == 6
    assert moved[3:7] == ["# envelope", "", "74 Cutoff # filter", "75 Reso"]


def test_move_row_stops_at_either_end():
    doc = parse(TEXT)
    assert move_row(lines(), doc, doc.sections[0], 4, -1) is None
    assert move_row(lines(), doc, doc.sections[0], 7, 1) is None


def test_move_row_keeps_each_position_s_line_ending():
    text = "[CC]\r\n74 A\r\n75 B\n[/CC]\r\n"
    doc = parse(text)
    moved, _ = move_row(lines(text), doc, doc.sections[0], 2, 1)
    assert moved[1:3] == ["75 B\r", "74 A"]


def test_add_row_after_the_cursor_or_first():
    ls = lines()
    s = section(ls, "CC")
    assert add_row(ls, s, 7, "76 Env") == ([*ls[:7], "76 Env", *ls[7:]], 8)
    assert add_row(ls, s, None, "73 First")[1] == 4


def test_add_section_goes_before_the_final_newline():
    assert add_section(["VERSION 1", ""], "PC") == ["VERSION 1", "[PC]", "[/PC]", ""]
    assert add_section(["VERSION 1"], "PC") == ["VERSION 1", "[PC]", "[/PC]"]
    assert add_section(["VERSION 1\r", ""], "PC") == ["VERSION 1\r", "[PC]\r", "[/PC]\r", ""]


def test_set_body_round_trips_and_replaces():
    ls = lines()
    s = section(ls, "COMMENT")
    assert body_text(ls, s) == "Hello"
    assert set_body(ls, s, "Hello") == ls
    assert set_body(ls, s, "One\nTwo")[9:12] == ["One", "Two", "[/COMMENT]"]
    assert set_body(ls, s, "")[8:10] == ["[COMMENT]", "[/COMMENT]"]


def test_a_comment_that_closes_its_section_breaks_the_file():
    ls = lines()
    before = analyse(ls, LATEST)[1]
    _, after = analyse(set_body(ls, section(ls, "COMMENT"), "Hi\n[/COMMENT]\nmore"), LATEST)
    assert {f.code for f in breaks(before, after)} >= {"section.stray_close"}


def test_breaks_ignores_structure_that_was_already_there():
    syntax = Finding(Severity.ERROR, "syntax", "x", 3)
    assert breaks([syntax], [syntax]) == []
    assert breaks([], [syntax]) == [syntax]


def test_set_directive_changes_adds_and_removes():
    ls = lines()
    doc = parse(TEXT)
    assert set_directive(ls, doc, "TRACKNAME", "Peak")[1] == "TRACKNAME Peak"
    assert set_directive(ls, doc, "OUTCHAN", "3")[2] == "OUTCHAN 3"
    assert set_directive(ls, doc, "TRACKNAME", None)[1] == "[CC]"
    assert set_directive(ls, doc, "OUTCHAN", None) == ls


def test_set_directive_changes_the_last_duplicate():
    text = "OUTCHAN 1\nOUTCHAN 2\n"
    assert set_directive(lines(text), parse(text), "OUTCHAN", "3") == ["OUTCHAN 1", "OUTCHAN 3", ""]


def test_row_text_from_form_values():
    assert row_text(CcEntry, None, {"cc": "76", "default": "", "name": "Env"}) == "76 Env"
    original = parse(TEXT).sections[0].entries[0]
    assert row_text(CcEntry, original, {"cc": "74", "default": "10", "name": "Cut"}) == "74:DEFAULT=10 Cut # filter"
    assert row_text(DrumEntry, None, {"row": "1", "trig": "", "chan": "cv1", "note": "", "name": "K"}) == \
        "1:NULL:cv1:NULL K"


def test_row_text_for_a_new_automation_lane():
    values = {"type": "NRPN", "cc": "", "msb": "", "lsb": "2000", "depth": "7", "cv": "", "default": "5"}
    assert row_text(AutomationEntry, None, values) == "NRPN::2000:7 DEFAULT=5"


def test_a_blank_name_is_a_syntax_error_not_the_name_none():
    ls = lines()
    text = row_text(CcEntry, None, {"cc": "76", "default": "", "name": ""})
    before = analyse(ls, LATEST)[1]
    _, after = analyse(add_row(ls, section(ls, "CC"), 7, text)[0], LATEST)
    assert [f.code for f in breaks(before, after)] == ["syntax"]


def test_a_blank_number_is_a_syntax_error():
    ls = lines()
    text = row_text(CcEntry, None, {"cc": "", "default": "", "name": "X"})
    before = analyse(ls, LATEST)[1]
    _, after = analyse(add_row(ls, section(ls, "CC"), 7, text)[0], LATEST)
    assert [f.code for f in breaks(before, after)] == ["syntax"]


def test_comment_rows():
    assert comment_value("  # envelope\r") == " envelope"
    assert comment_text("  # envelope", " env") == "  # env"


def test_open_text():
    assert open_text("﻿VERSION 1\n", LATEST)[:2][0] == "VERSION 1\n"
    assert [a.code for a in open_text("﻿VERSION 1\n", LATEST)[1]] == ["file.bom"]
    assert [f.code for f in open_text("VERSION 1\n[CC]\n74\n[/CC]\n", LATEST)[2]] == ["syntax"]
    assert [f.code for f in open_text("[FOO]\n[/FOO]\n", LATEST)[2]] == ["section.unknown_empty"]
    encoding = Finding(Severity.ERROR, "encoding", "not valid UTF-8", 0)
    assert open_text(encoding, LATEST) == ("", [], [encoding])
    assert open_text("VERSION 1\n[CC]\n74 A\n", LATEST)[2] == []  # closed by the fixer


def test_new_file_text_writes_only_the_fields_set():
    values = {"TRACKNAME": "Peak", "TYPE": "POLY", "OUTPORT": None, "OUTCHAN": "1"}
    assert new_file_text(values) == "VERSION 1\nTRACKNAME Peak\nTYPE POLY\nOUTCHAN 1\n"


def test_new_file_path(tmp_path):
    (tmp_path / "Peak.txt").write_text("VERSION 1\n")
    assert new_file_path(tmp_path, "Synth") == tmp_path / "Synth.txt"
    assert new_file_path(tmp_path, "Synth.txt") == tmp_path / "Synth.txt"
    for bad in ("", " ", ".txt", "peak.TXT", "a/b", ".hidden"):
        assert isinstance(new_file_path(tmp_path, bad), str), bad


def test_inserting_after_a_last_line_without_a_newline_keeps_crlf():
    assert insert_line(["a\r", "b"], 2, "x") == ["a\r", "b\r", "x"]
    assert insert_line(["a", "b"], 2, "x") == ["a", "b", "x"]


def test_add_section_to_a_crlf_file_without_a_final_newline():
    lines = ["VERSION 1\r", "[CC]\r", "[/CC]"]
    assert add_section(lines, "PC") == ["VERSION 1\r", "[CC]\r", "[/CC]\r", "[PC]\r", "[/PC]"]
