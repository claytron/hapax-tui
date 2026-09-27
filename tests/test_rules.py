import pytest

from hapax import LATEST, parse, validate
from hapax.parse import Severity, Span
from hapax.rules import fw_str, parse_fw


def findings(text, fw=LATEST):
    return validate(parse(text), fw)


def errors(text, fw=LATEST):
    return [f.code for f in findings(text, fw) if f.severity is Severity.ERROR]


def codes(text, fw=LATEST):
    return [(f.code, f.line) for f in findings(text, fw)]


@pytest.mark.parametrize("section, text, code", [
    ("CC", "127 x", None),
    ("CC", "128 x", "cc.range"),  # P12
    ("CC", "0:DEFAULT=127 x", None),
    ("CC", "0:DEFAULT=128 x", "cc.range"),
    ("PC", "1 x", None),
    ("PC", "128 x", None),
    ("PC", "0 x", "pc.range"),  # A08
    ("PC", "129 x", "pc.range"),  # A09
    ("PC", "1:127:127 x", None),
    ("PC", "1:128:0 x", "pc.range"),
    ("CC_PAIR", "0:127 x", None),
    ("CC_PAIR", "128:0 x", "cc_pair.range"),
    ("CC_PAIR", "1:33:DEFAULT=16383 x", None),
    ("CC_PAIR", "1:33:DEFAULT=16384 x", "cc_pair.range"),
    ("NRPN", "127:127:7 x", None),
    ("NRPN", "128:0:7 x", "nrpn.range"),
    ("NRPN", ":16383:14 x", None),
    ("NRPN", "0:16384:7 x", "nrpn.range"),
    ("NRPN", "1:128:7 x", "nrpn.range"),  # A13
    ("NRPN", "0:1:8 x", "nrpn.range"),
    ("NRPN", "0:1:7:DEFAULT=128 x", "nrpn.range"),
    ("NRPN", "0:1:14:DEFAULT=16383 x", None),
    ("DRUMLANES", "16:127:16:127 x", None),
    ("DRUMLANES", "17:NULL:NULL:NULL x", "drum.range"),
    ("DRUMLANES", "1:128:NULL:NULL x", "drum.range"),
    ("DRUMLANES", "1:NULL:17:NULL x", "drum.range"),
    ("DRUMLANES", "1:NULL:0:NULL x", "drum.range"),
    ("DRUMLANES", "1:NULL:G4:NULL x", None),
    ("DRUMLANES", "1:NULL:CVG5:NULL x", "drum.range"),
    ("DRUMLANES", "1:NULL:NULL:128 x", "drum.range"),
    ("ASSIGN", "8 CC:119", None),
    ("ASSIGN", "9 CC:1", "assign.range"),
    ("ASSIGN", "0 CC:1", "assign.range"),
    ("ASSIGN", "1 CC:120", "assign.range"),  # A14
    ("ASSIGN", "1 CV:4", None),
    ("ASSIGN", "1 CV:5", "assign.range"),
    ("ASSIGN", "1 CV:0", "assign.range"),
    ("ASSIGN", "1 CV:1 DEFAULT=65535", None),
    ("ASSIGN", "1 CV:1 DEFAULT=65536", "assign.range"),
    ("ASSIGN", "1 CV:1 DEFAULT=5V", None),
    ("ASSIGN", "1 CV:1 DEFAULT=-5V", None),
    ("ASSIGN", "1 CV:1 DEFAULT=5.1V", "assign.range"),
    ("ASSIGN", "1 CC:1 DEFAULT=127", None),
    ("ASSIGN", "1 CC:1 DEFAULT=128", "assign.range"),
    ("ASSIGN", "1 CC:1 DEFAULT=1V", "assign.range"),
    ("ASSIGN", "1 NRPN:0:1:14 DEFAULT=16383", None),
    ("ASSIGN", "1 NRPN:0:1:7 DEFAULT=128", "assign.range"),
    ("ASSIGN", "1 PB DEFAULT=99999", None),
    ("ASSIGN", "1 NULL", None),
    ("AUTOMATION", "CC:120", "automation.range"),  # A15
    ("AUTOMATION", "NULL", "automation.type"),
    ("AUTOMATION", "CC:119 DEFAULT=127", None),
])
def test_ranges(section, text, code):
    assert errors(f"[{section}]\n{text}\n[/{section}]\n") == ([code] if code else [])


@pytest.mark.parametrize("ch", list("!\"$'()*,./:<=>?@_-+ "))  # C01-C12, P01, P02
def test_name_characters_accepted(ch):
    assert errors(f"[CC]\n74 A{ch}B\n[/CC]\n") == []


@pytest.mark.parametrize("ch", list("%&;[\\]^`{|}~é"))  # C04, C07, C13-C22, P01
def test_name_characters_rejected(ch):
    [f] = findings(f"[CC]\n74 A{ch}B\n[/CC]\n")
    assert (f.code, f.line, f.span, f.field) == ("name.char", 2, Span(4, 5), "name")


@pytest.mark.parametrize("text", [
    "TRACKNAME A&B",  # B08
    "[PC]\n1 A&B\n[/PC]",
    "[CC_PAIR]\n1:33 A&B\n[/CC_PAIR]",
    "[NRPN]\n0:1:7 A&B\n[/NRPN]",
    "[DRUMLANES]\n1:NULL:NULL:36 A&B\n[/DRUMLANES]",
])
def test_every_name_is_checked(text):
    assert "name.char" in errors(text)


@pytest.mark.parametrize("text, code", [
    ("VERSION 1", None),
    ("VERSION 2", "version"),  # B06, a warning
    ("TYPE poly", None),  # B02
    ("TYPE Drum", None),
    ("TYPE MPE", None),
    ("TYPE NULL", None),
    ("TYPE MONO", "type.value"),
    ("OUTPORT A", None),
    ("OUTPORT D", None),
    ("OUTPORT E", "outport.value"),
    ("OUTPORT cv4", None),
    ("OUTPORT CV5", "outport.value"),
    ("OUTPORT G1", None),
    ("OUTPORT CVG2", None),
    ("OUTPORT USBD16", None),
    ("OUTPORT USBH17", "outport.value"),
    ("OUTCHAN 16", None),
    ("OUTCHAN 17", "outchan.value"),  # B04
    ("OUTCHAN 0", "outchan.value"),
    ("OUTCHAN ALL", "outchan.value"),
    ("INPORT ALLACTIVE", None),
    ("INPORT NONE", None),
    ("INPORT C", "inport.value"),
    ("INPORT CVG", None),
    ("INPORT USBH3", None),
    ("INCHAN ALL", None),
    ("INCHAN 17", "inchan.value"),
    ("MAXRATE 1", None),
    ("MAXRATE 192", None),
    ("MAXRATE 5", "maxrate.value"),  # B05
    ("MAXRATE NULL", None),
    ("OUTAN 4", "directive.unknown"),  # P11
    ("TRACKNAME", "trackname.value"),
])
def test_directive_values(text, code):
    assert [f.code for f in findings(text)] == ([code] if code else [])


@pytest.mark.parametrize("text, before, after, code", [
    ("[ASSIGN]\n1 CC_PAIR:1:33\n[/ASSIGN]", (1, 12), (1, 13), "assign.type"),
    ("[AUTOMATION]\nCC_PAIR:1:33\n[/AUTOMATION]", (1, 12), (1, 13), "automation.type"),
    ("OUTPORT USBD1", (2, 21), (3, 0), "outport.value"),  # B03 on 2.21
    ("INPORT USBH16", (2, 21), (3, 0), "inport.value"),
    ("[DRUMLANES]\n9:NULL:NULL:36 x\n[/DRUMLANES]", (3, 0), (3, 10), "drum.range"),  # P05 on 2.21
    ("TYPE POLYAT", (3, 10), (3, 20), "type.value"),  # B01
    ("TYPE AFTR", (3, 10), (3, 20), "type.value"),
])
def test_firmware_thresholds(text, before, after, code):
    assert code in errors(text, before)
    assert code not in errors(text, after)


@pytest.mark.parametrize("text", [
    "[CC]\n74:DEFAULT=100 x\n[/CC]",  # E01
    "[CC]\n74:100 x\n[/CC]",  # E03
    "[NRPN]\n0:1:7:64 x\n[/NRPN]",  # E04
    "[CC_PAIR]\n1:33:DEFAULT=8192 x\n[/CC_PAIR]",
])
@pytest.mark.parametrize("fw, expected", [
    ((2, 21), []),
    ((3, 0), [("default.ignored", 2)]),
    ((3, 10), [("default.ignored", 2)]),
    ((3, 20), []),
])
def test_section_defaults_are_ignored_on_3_00_to_3_10(text, fw, expected):
    assert codes(text, fw) == expected


def test_section_default_range_is_unchecked_on_3_10():  # A07
    assert codes("[CC]\n74:DEFAULT=128 x\n[/CC]", (3, 10)) == [("default.ignored", 2)]
    assert codes("[CC]\n74:DEFAULT=128 x\n[/CC]", (2, 21)) == [("cc.range", 2)]


def test_cc_pair_default_is_ignored_before_1_14():
    assert codes("[CC_PAIR]\n1:33:DEFAULT=8192 x\n[/CC_PAIR]", (1, 13)) == [("default.ignored", 2)]


def test_default_firmware_is_3_21():
    assert LATEST == (3, 21)
    assert validate(parse("TYPE POLYAT")) == []


def test_findings_are_sorted_and_carry_field_and_span():
    fs = findings("OUTCHAN 17\n[NRPN]\n1:200:7 x\n[/NRPN]\n")
    assert [(f.line, f.code, f.field, f.span) for f in fs] == [
        (1, "outchan.value", "value", Span(8, 10)),
        (3, "nrpn.range", "lsb", Span(2, 5)),
    ]


def test_parse_fw():
    assert parse_fw("3.10") == (3, 10)
    assert parse_fw("1.12") == (1, 12)
    assert fw_str((3, 0)) == "3.00"
    for bad in ["1.11", "3.11", "3.1", "4", "latest"]:
        with pytest.raises(ValueError):
            parse_fw(bad)


@pytest.mark.parametrize("text, expected", [
    ("[CC]\n31 a\n31 b\n[/CC]", [("cc.duplicate", 3)]),  # A05
    ("[CC]\n120 a\n[/CC]", [("cc.unusable", 2)]),  # A03
    ("[PC]\n1 a\n1:NULL:NULL b\n1:0:NULL c\n[/PC]", [("pc.duplicate", 3)]),
    ("[NRPN]\n0:1026:7 a\n8:2:7 b\n:1026:7 c\n[/NRPN]", [("nrpn.duplicate", 3), ("nrpn.duplicate", 4)]),
    ("[CC_PAIR]\n1:33 a\n1:33 b\n[/CC_PAIR]", [("cc_pair.duplicate", 3)]),
    ("[DRUMLANES]\n1:NULL:NULL:36 a\n1:NULL:NULL:37 b\n[/DRUMLANES]", [("drum.duplicate", 3)]),  # P05
    ("TYPE POLY\n[DRUMLANES]\n1:NULL:NULL:36 a\n[/DRUMLANES]", [("drum.not_drum", 3)]),  # A10
    ("TYPE NULL\n[DRUMLANES]\n1:NULL:NULL:36 a\n[/DRUMLANES]", []),
    ("TYPE MPE\nINPORT A", [("inport.mpe", 2)]),
    ("TYPE POLY\nTYPE DRUM", [("directive.duplicate", 2)]),  # B07
    ("[ASSIGN]\n1 CC:1\n1 CC:2\n[/ASSIGN]", [("assign.duplicate", 3)]),
    ("[ASSIGN]\n1 CC:74:100\n[/ASSIGN]", [("assign.extra", 2)]),  # E05
    ("[ASSIGN]\n4 CC:12 Name Text DEFAULT=100\n[/ASSIGN]", [("assign.text", 2)]),  # P06
    ("[ASSIGN]\n5 PB whatever\n[/ASSIGN]", []),
    ("[AUTOMATION]\nCC:71 DEFAULT=20\n[/AUTOMATION]", []),  # P07
])
def test_warnings(text, expected):
    assert codes(text) == expected


def test_65th_automation_lane_is_an_error():  # P08
    body = "\n".join(f"CC:{i}" for i in range(65))
    assert codes(f"[AUTOMATION]\n{body}\n[/AUTOMATION]") == [("automation.count", 66)]


def test_129th_pc_warns():  # P09
    body = "\n".join(f"{i} x{i}" for i in range(1, 129))
    assert codes(f"[PC]\n{body}\n1:1:NULL y\n[/PC]") == [("pc.count", 130)]


@pytest.mark.parametrize("fw, expected", [((1, 13), [("tab", 1), ("tab", 3)]), ((1, 14), [])])
def test_tabs_break_loading_before_1_14(fw, expected):
    fs = findings("VERSION\t1\n# ok\n[CC]\t# x\n[/CC]", fw)
    assert [(f.code, f.line) for f in fs] == expected
    if expected:
        assert fs[0].span == Span(7, 8)


def test_every_mistake_is_reported_not_just_the_first():
    text = "OUTCHAN 17\n[CC]\n128 a\n74 b&c\n[/CC]\n[ASSIGN]\n9 CC:1\n[/ASSIGN]\n"
    assert codes(text) == [("outchan.value", 1), ("cc.range", 3), ("name.char", 4), ("assign.range", 7)]


@pytest.mark.parametrize("text, span", [
    ("TRACKNAME Foo ", Span(13, 14)),
    ("[CC]\n74 Cutoff \n[/CC]", Span(9, 10)),
    ("[CC]\n74 Cutoff　\n[/CC]", Span(9, 10)),
])
def test_trailing_unicode_whitespace_is_part_of_the_name(text, span):
    [f] = findings(text)
    assert (f.code, f.span) == ("name.char", span)


@pytest.mark.parametrize("ch", list("%&;[\\]^`{|}~é"))  # G01: [COMMENT] rejects what names reject
def test_comment_characters_are_checked(ch):
    [f] = findings(f"[COMMENT]\nA{ch}B\n[/COMMENT]\n")
    assert (f.code, f.line, f.span) == ("name.char", 2, Span(1, 2))


def test_comment_text_with_accepted_characters_is_clean():
    assert findings("[COMMENT]\n  Plain line, with: punctuation! (ok) 1+1=2 @ 50\n[/COMMENT]\n") == []


@pytest.mark.parametrize("text, span", [
    ("[CC]\n1 L16-567890123456\n[/CC]", Span(17, 18)),  # H01: the CC list shows 15 characters
    ("[PC]\n1 L16-567890123456\n[/PC]", Span(17, 18)),
    ("[NRPN]\n0:1:7 L16-567890123456\n[/NRPN]", Span(21, 22)),
    ("[CC_PAIR]\n1:33 L16-567890123456\n[/CC_PAIR]", Span(20, 21)),
    ("[DRUMLANES]\n1:NULL:NULL:36 L16-567890123456\n[/DRUMLANES]", Span(30, 31)),
])
def test_names_longer_than_15_characters_warn(text, span):
    [f] = findings(text)
    assert (f.code, f.line, f.severity, f.span) == ("name.long", 2, Severity.WARNING, span)


def test_15_character_name_is_clean():
    assert findings("[CC]\n1 L15-56789012345\n[/CC]") == []


def test_tracknames_longer_than_9_characters_warn():  # H02: the track header shows 9
    [f] = findings("TRACKNAME H02-567890")
    assert (f.code, f.severity, f.span) == ("name.long", Severity.WARNING, Span(19, 20))
    assert findings("TRACKNAME H02-56789") == []
