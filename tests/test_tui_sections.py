import re
from dataclasses import fields

import pytest

from hapax.parse import Directive, Severity, parse
from hapax.rules import RELEASES, _directive, parse_fw
from hapax.tui.edits import row_text
from hapax.tui.sections import HEADER, SECTIONS, TEXT, header_choices, required


@pytest.mark.parametrize("name", SECTIONS)
def test_every_column_is_a_field_of_its_entry(name):
    cls, columns = SECTIONS[name]
    names = {f.name for f in fields(cls)}
    assert {c.field for c in columns} <= names


@pytest.mark.parametrize("fw", RELEASES)
@pytest.mark.parametrize("key", HEADER)
def test_every_header_choice_is_valid_on_its_firmware(key, fw):
    fw = parse_fw(fw)
    for value in header_choices(key, fw) or ():
        d = Directive(line=1, raw="", spans={}, key=key, value=value)
        assert [f for f in _directive(d, fw) if f.severity is Severity.ERROR] == [], value


def test_choices_follow_the_firmware():
    assert "POLYAT" not in header_choices("TYPE", (3, 10))
    assert "POLYAT" in header_choices("TYPE", (3, 20))
    assert "USBD16" not in header_choices("OUTPORT", (2, 21))
    assert "USBD16" in header_choices("OUTPORT", (3, 0))
    assert header_choices("TRACKNAME", (3, 21)) is None


@pytest.mark.parametrize("name", SECTIONS)
def test_no_field_accepts_what_would_change_the_line_shape(name):
    for column in SECTIONS[name][1]:
        if column.choices:
            continue
        # A name is the rest of the line, so only a comment can cut it short.
        bad = ("Osc #2",) if column.field == "name" else ("#", "74:3", "7 4", "1#")
        for value in bad:
            assert not re.fullmatch(column.restrict, value), (column.field, value)


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
