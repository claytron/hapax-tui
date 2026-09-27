import pytest

from hapax.parse import Severity, Span, parse


def entry(text, section):
    doc = parse(f"[{section}]\n{text}\n[/{section}]\n")
    assert doc.parse_findings == []
    [e] = doc.sections[0].entries
    assert e.line == 2
    return e


@pytest.mark.parametrize("section, text, expected", [
    ("CC", "74 Cutoff", dict(cc=74, default=None, name="Cutoff")),
    ("CC", "71:DEFAULT=64 Resonance", dict(cc=71, default=64, name="Resonance")),
    ("CC", "22:default=100 lower", dict(cc=22, default=100)),
    ("CC", "24:100 shorthand", dict(cc=24, default=100, name="shorthand")),  # E03
    ("CC", "026 lead zero", dict(cc=26, name="lead zero")),  # A02
    ("CC", "30:DEFAULT=100\tTab sep", dict(cc=30, default=100, name="Tab sep")),
    ("CC", "74 A=B:C DEFAULT=1", dict(cc=74, name="A=B:C DEFAULT=1")),
    ("CC", "  74 Indented", dict(cc=74, name="Indented")),
    ("CC", "74 Cutoff \t ", dict(name="Cutoff")),
    ("PC", "3 FAT LEAD", dict(pc=3, msb=None, lsb=None, name="FAT LEAD")),
    ("PC", "123:34:NULL HARMONICA", dict(pc=123, msb=34, lsb=None)),
    ("CC_PAIR", "1:33 Mod 14bit", dict(msb=1, lsb=33, default=None, name="Mod 14bit")),
    ("CC_PAIR", "7:39:DEFAULT=8192 Vol", dict(msb=7, lsb=39, default=8192)),
    ("NRPN", "0:1:7 Plain", dict(msb=0, lsb=1, depth=7, default=None)),
    ("NRPN", ":2000:7 BAR", dict(msb=None, lsb=2000, depth=7, name="BAR")),
    ("NRPN", "0:2:7:DEFAULT=64 D", dict(default=64)),
    ("NRPN", "0:3:7:64 Bare", dict(default=64)),  # E04
    ("DRUMLANES", "1:NULL:2:60 KICK", dict(row=1, trig=None, chan=2, note=60, name="KICK")),
    ("DRUMLANES", "2:100:cv1:NULL NULL", dict(trig=100, chan="CV1", note=None, name="NULL")),
    ("DRUMLANES", "3:null:g1:Null x", dict(trig=None, chan="G1", note=None)),
    ("ASSIGN", "1 CC:74", dict(pot=1, type="CC", cc=74, extra=None, default=None, junk=False)),
    ("ASSIGN", "1 cc:74 default=5", dict(cc=74, default="5")),
    ("ASSIGN", "3 CC:16:127", dict(cc=16, extra=127)),  # E05
    ("ASSIGN", "4 CC:12 Name Text DEFAULT=100", dict(cc=12, junk=True, default="100")),  # P06
    ("ASSIGN", "5 PB", dict(type="PB")),
    ("ASSIGN", "5 pb:anything", dict(type="PB")),
    ("ASSIGN", "6 AT", dict(type="AT")),
    ("ASSIGN", "7 NRPN:0:1:7 DEFAULT=64", dict(type="NRPN", msb=0, lsb=1, depth=7, default="64")),
    ("ASSIGN", "8 CV:1 DEFAULT=-2.5v", dict(type="CV", cv=1, default="-2.5V")),
    ("ASSIGN", "2 CC_PAIR:1:33", dict(type="CC_PAIR", msb=1, lsb=33)),  # D02
    ("ASSIGN", "1 NULL", dict(type="NULL")),
    ("AUTOMATION", "CC:71 DEFAULT=20", dict(type="CC", cc=71, default="20")),
    ("AUTOMATION", "nrpn::2000:14", dict(type="NRPN", msb=None, lsb=2000, depth=14)),
])
def test_entry_shapes(section, text, expected):
    e = entry(text, section)
    for field, value in expected.items():
        assert getattr(e, field) == value, field


@pytest.mark.parametrize("text, key, value", [
    ("VERSION 1", "VERSION", "1"),
    ("trackname My Synth", "TRACKNAME", "My Synth"),  # P16
    ("TYPE poly", "TYPE", "poly"),
    ("  OUTPORT\tA", "OUTPORT", "A"),
    ("TRACKNAME", "TRACKNAME", None),
])
def test_directives(text, key, value):
    doc = parse(text)
    assert doc.parse_findings == []
    [d] = doc.directives
    assert (d.key, d.value) == (key, value)


def test_comments_blank_lines_and_crlf_keep_physical_line_numbers():
    doc = parse("# comment\r\n\r\nVERSION 1 # trailing\r\n[CC]\r\n9 N09 hash#CUT\r\n[/CC]\r\n")
    assert (doc.directives[0].line, doc.directives[0].value) == (3, "1")
    [e] = doc.sections[0].entries
    assert (e.line, e.name) == (5, "N09 hash")
    assert doc.lines[4] == "9 N09 hash#CUT\r"


def test_spans_are_columns_in_the_raw_line():
    e = entry("  :2000:7 BAR", "NRPN")
    assert "msb" not in e.spans
    assert (e.spans["lsb"], e.spans["depth"], e.spans["name"]) == (Span(3, 7), Span(8, 9), Span(10, 13))


def test_assign_text_span_covers_every_word():
    e = entry("4 CC:12 Name Text DEFAULT=100", "ASSIGN")
    assert (e.spans["junk"], e.spans["default"]) == (Span(8, 17), Span(26, 29))


@pytest.mark.parametrize("section, text, message, start", [
    ("CC", "74", "expected ':' or a space, found end of line", 2),  # A06
    ("CC", "23:DEFAULT=NULL x", "expected a number", 11),  # P03
    ("CC", "105:LPF VEL", "expected DEFAULT= or a number", 4),  # toraiz/as-1
])
def test_syntax_errors_name_what_was_expected(section, text, message, start):
    [f] = parse(f"[{section}]\n{text}\n[/{section}]\n").parse_findings
    assert (f.code, f.line, f.severity, f.span.start) == ("syntax", 2, Severity.ERROR, start)
    assert f.message.startswith(message)


def test_unclosed_section_is_reported_at_the_next_header():  # P15
    doc = parse("[CC]\n74 x\n\n[NRPN]\n0:1:7 y\n[/NRPN]\n")
    [f] = doc.parse_findings
    assert (f.code, f.line) == ("section.unclosed", 4)
    assert doc.sections[0].end is None
    assert len(doc.sections[1].entries) == 1


@pytest.mark.parametrize("text", ["[COMMENT]\nhello\n", "[CC]\n74 x\n"])
def test_section_open_at_end_of_file_loads_but_warns(text):  # F04, F05
    [f] = parse(text).parse_findings
    assert (f.code, f.line, f.severity) == ("section.unclosed_eof", 1, Severity.WARNING)


def test_stray_close():
    [f] = parse("[/CC]\n").parse_findings
    assert (f.code, f.line) == ("section.stray_close", 1)


def test_unknown_section_is_reported_on_its_first_entry_only():  # A11
    [f] = parse("[FOO]\n74 x\n75 y\n[/FOO]\n").parse_findings
    assert (f.code, f.line, f.severity) == ("section.unknown", 2, Severity.ERROR)


def test_empty_unknown_section_warns():
    [f] = parse("[FOO]\n[/FOO]\n").parse_findings
    assert (f.code, f.severity) == ("section.unknown_empty", Severity.WARNING)


def test_section_names_are_case_insensitive():  # A12
    doc = parse("[cc]\n74 x\n[/Cc]\n")
    assert doc.parse_findings == []
    assert doc.sections[0].name == "CC"


def test_comment_section_is_not_parsed():
    assert parse("[COMMENT]\nanything: at all = here\n[/COMMENT]\n").parse_findings == []


def test_leading_bom_warns_and_line_one_still_parses():
    doc = parse("﻿VERSION 1\n")
    assert [f.code for f in doc.parse_findings] == ["file.bom"]
    assert doc.directives[0].key == "VERSION"


@pytest.mark.parametrize("text", ["", "\n\n", "[", "]", "[[CC]]", ":::", "\x00\x01", "é" * 50, "[CC]\n\t\t\n"])
def test_parse_never_raises(text):
    parse(text)
