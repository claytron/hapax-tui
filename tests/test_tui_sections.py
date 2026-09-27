import re
from dataclasses import fields

import pytest

from hapax.parse import Directive, Severity
from hapax.rules import RELEASES, _directive, parse_fw
from hapax.tui.sections import HEADER, SECTIONS, header_choices


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
