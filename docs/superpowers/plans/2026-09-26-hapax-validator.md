# Hapax Validator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A pure-Python library (`parse`, `validate`) and a `hapax validate` CLI that report every problem in a Squarp Hapax instrument definition for a chosen firmware.

**Architecture:** `parse()` runs a structure pass over physical lines and parses each directive or entry with one Lark LALR start rule, memoised per `(start rule, text)`; it never raises and returns a lossless `Document`.
`validate(doc, fw)` runs entry rules (one entry plus firmware) and document rules (whole file) and returns sorted `Finding`s carrying a stable `code`, `line`, `span` and `field`.
The CLI owns all I/O.

**Tech Stack:** Python 3.13, uv, Lark 1.3 (LALR, contextual lexer), argparse, pytest.

**Spec:** `docs/superpowers/specs/2026-09-21-hapax-validator-design.md`

## Global Constraints

- Python `>=3.13`; one runtime dependency, `lark`; `pytest` is the only dev dependency.
- Flat package `hapax/` at the repo root; `[project.scripts] hapax = "hapax.cli:main"`.
- Severity: an error is something the target firmware rejects; a warning is something it accepts that is probably not what the author meant. Nothing the target firmware accepts is an error.
- Supported firmware: published releases 1.12–3.21; default `3.21`; anything else exits 2.
- Firmware is `tuple[int, int]`; each firmware rule is a plain comparison beside a comment naming its source. No per-version ruleset.
- `parse` never raises; `validate` is pure (no printing, no files, no exit codes).
- Findings are sorted by line; tests assert `code`, `line`, `span`, never message text.
- Line numbers are 1-based physical lines, comments and blanks included; spans are 0-based, end-exclusive columns in the raw line.
- CLI output is plain text, no colour; exit 0 clean, 1 findings that count, 2 usage or I/O failure; `--strict` makes warnings count.
- Dotfiles are always skipped; a directory expands to the `*.txt` files directly inside it.
- New files end with a newline; no trailing whitespace.

## Review Focus

- A file saved with a UTF-8 byte-order mark (common from Windows editors): expect one `file.bom` warning and line 1 still parsed — Task 1.
- Trailing spaces or tabs after a name: expect them not to be part of the name — Task 1.
- Keywords in any case inside fields (`cc:`, `default=`, `null`, `g1`): expect them to parse like upper case — Task 1.
- A file with several mistakes: expect every one reported, not just the first as the Hapax does — Task 3.
- A folder straight off the SD card, with `._` files, `.txt.bak` backups and `.TXT` extensions: expect only the definitions checked — Task 5.

## Finding codes

Tests assert these; keep them stable.

| Code | Severity | Raised by |
|---|---|---|
| `syntax` | error | a line the grammar rejects |
| `section.unclosed`, `section.stray_close`, `section.unknown` | error | structure pass |
| `section.unknown_empty`, `file.bom` | warning | structure pass |
| `directive.unknown` | error | unknown directive key |
| `<key>.value` (`type.value`, `outchan.value`, …) | error | directive value invalid, missing, or needs newer firmware |
| `version` | warning | `VERSION` not `1` |
| `name.char` | error | character outside the name set |
| `<kind>.range` (`cc.range`, `pc.range`, `cc_pair.range`, `nrpn.range`, `drum.range`, `assign.range`, `automation.range`) | error | value out of range; `field` says which |
| `assign.type`, `automation.type` | error | `CC_PAIR:` before 1.13; `NULL` in AUTOMATION |
| `automation.count` | error | 65th automation lane |
| `tab` | error | tab before 1.14 |
| `encoding` | error | CLI: file not UTF-8 (line 0) |
| `default.ignored` | warning | section default the firmware ignores |
| `cc.unusable` | warning | CC 120–127 in `[CC]` |
| `cc.duplicate`, `pc.duplicate`, `cc_pair.duplicate`, `nrpn.duplicate`, `drum.duplicate`, `assign.duplicate`, `directive.duplicate` | warning | declared twice |
| `pc.count` | warning | 129th PC |
| `drum.not_drum` | warning | drum lanes on a POLY/MPE/POLYAT/AFTR track |
| `inport.mpe` | warning | `TYPE MPE` with `INPORT A` or `B` |
| `assign.extra`, `automation.extra` | warning | `CC:74:100` — the `:100` is dropped |
| `assign.text`, `automation.text` | warning | text between the value and `DEFAULT=` |

---

### Task 1: Project, grammar, model and `parse()`

**Files:**
- Create: `pyproject.toml`, `.python-version`, `hapax/__init__.py`, `hapax/grammar.lark`, `hapax/parse.py`
- Test: `tests/test_parse.py`

**Interfaces:**
- Produces (in `hapax.parse`): `Span(start, end)`, `Severity.ERROR|WARNING`, `Finding(severity, code, message, line, span=None, field=None)`, entry dataclasses `Directive(key, value)`, `CcEntry(cc, default, name)`, `PcEntry(pc, msb, lsb, name)`, `CcPairEntry(msb, lsb, default, name)`, `NrpnEntry(msb, lsb, depth, default, name)`, `DrumEntry(row, trig, chan, note, name)`, `AutomationEntry(type, cc, msb, lsb, depth, cv, extra, default, junk)`, `AssignEntry(AutomationEntry + pot)` — all with `line`, `raw`, `spans: dict[str, Span]`; `Section(name, start, end, entries)`, `Document(lines, directives, sections, parse_findings)`, `parse(text) -> Document`, `SECTIONS`, `_parse_line` (lru-cached, cleared by the performance test).
- Value conventions: integers are `int`; `NULL` is `None`; drum `chan` is `int`, an upper-cased port string such as `"CV1"`, or `None`; `AutomationEntry.type` is one of `CC NRPN CC_PAIR CV PB AT NULL`; `AutomationEntry.default` is the raw upper-cased text (`"100"`, `"-2.5V"`); an omitted NRPN MSB is `None`.

- [ ] **Step 1: Branch and scaffold**

```bash
git switch -c validator
```

`pyproject.toml`:

```toml
[project]
name = "hapax"
version = "0.1.0"
description = "Validate Squarp Hapax instrument definitions"
requires-python = ">=3.13"
dependencies = ["lark>=1.3"]

[project.scripts]
hapax = "hapax.cli:main"

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

`.python-version`:

```text
3.13
```

`hapax/__init__.py` (Task 2 adds the `rules` exports):

```python
from .parse import Document, Finding, Severity, Span, parse

__all__ = ["Document", "Finding", "Severity", "Span", "parse"]
```

Run: `uv sync`
Expected: creates `.venv` and `uv.lock`, installs lark and pytest.

- [ ] **Step 2: Write the failing tests**

`tests/test_parse.py`:

```python
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


def test_section_open_at_end_of_file_is_unclosed():
    [f] = parse("[COMMENT]\nhello\n").parse_findings
    assert (f.code, f.line) == ("section.unclosed", 1)


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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_parse.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'hapax.parse'`.

- [ ] **Step 4: Write the grammar**

`hapax/grammar.lark` (grown from `spike/grammar.lark`; every lowercase rule under a start rule is a field named after the model attribute, `parse.py` aliases the rest):

```lark
// Hapax instrument definition, one start rule per line kind.
// Each line arrives without its comment and trailing whitespace; leading whitespace is kept,
// so token columns are screen columns.
// Shapes only: ranges, enumerations, name characters and firmware rules live in rules.py.

directive: _WS? key [_WS value]

// 74:64 X is shorthand for 74:DEFAULT=64 X (probe E03)
cc_entry: _WS? cc [_COLON default] _WS name
pc_entry: _WS? pc [_COLON pc_msb _COLON pc_lsb] _WS name
ccpair_entry: _WS? msb _COLON lsb [_COLON pair_default] _WS name
// A bare fourth field is a default (probe E04)
nrpn_entry: _WS? nrpn_msb _COLON lsb _COLON depth [_COLON default] _WS name
drum_entry: _WS? row _COLON trig _COLON chan _COLON note _WS name
assign_entry: _WS? pot _WS _target _tail
automation_entry: _WS? _target _tail

// CC:74:100 loads but the :100 is dropped (probe E05)
// PB and AT: "any value after the TYPE will be ignored" (template)
_target: TYPE_CC cc [_COLON extra]
       | TYPE_NRPN nrpn_msb _COLON lsb _COLON depth
       | TYPE_CC_PAIR msb _COLON lsb
       | TYPE_CV cv
       | TYPE_PB [PB_TAIL]
       | TYPE_AT [PB_TAIL]
       | NULL

// Text between the value and DEFAULT= loads (probe P06 pot 4)
_tail: (_WS junk)* [_WS line_default]

key: KEY
value: VALUE
name: NAME
cc: INT
pc: INT
pc_msb: INT | NULL
pc_lsb: INT | NULL
msb: INT
lsb: INT
nrpn_msb: INT?
depth: INT
default: DEFAULT? INT
pair_default: DEFAULT INT
row: INT
trig: INT | NULL
chan: INT | NULL | CVPORT
note: INT | NULL
pot: INT
extra: INT
cv: INT
junk: JUNK
line_default: DEFAULT DEFVAL

TYPE_CC: "CC:"i
TYPE_NRPN: "NRPN:"i
TYPE_CC_PAIR: "CC_PAIR:"i
TYPE_CV: "CV:"i
TYPE_PB: "PB"i
TYPE_AT: "AT"i
PB_TAIL: /:\S*/
NULL: "NULL"i
DEFAULT.2: "DEFAULT="i
DEFVAL: /-?[0-9]+(\.[0-9]+)?V?/i
CVPORT: /(CVG|CV|G)[0-9]+/i
KEY: /[A-Za-z_]+/
VALUE: /\S.*/
NAME: /\S.*/
JUNK: /\S+/
INT: /[0-9]+/
_COLON: ":"
_WS: /[ \t]+/
```

- [ ] **Step 5: Write the model and parser**

`hapax/parse.py`:

```python
"""Parse Hapax instrument definitions into a lossless model. Never raises."""

import re
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from lark import Lark, Token, Tree, UnexpectedCharacters, UnexpectedInput, UnexpectedToken


@dataclass(frozen=True)
class Span:
    start: int  # 0-based column in the raw line
    end: int  # exclusive


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Finding:
    severity: Severity
    code: str  # stable id, e.g. "cc.range"; tests and future silencing key on it
    message: str
    line: int  # 1-based; 0 = whole file
    span: Span | None = None
    field: str | None = None  # model field, e.g. "lsb"


@dataclass(frozen=True, kw_only=True)
class Entry:
    line: int
    raw: str  # the line exactly as on disk
    spans: dict[str, Span]  # field name -> columns


@dataclass(frozen=True, kw_only=True)
class Directive(Entry):
    key: str  # upper-cased
    value: str | None = None


@dataclass(frozen=True, kw_only=True)
class CcEntry(Entry):
    cc: int
    default: int | None = None
    name: str


@dataclass(frozen=True, kw_only=True)
class PcEntry(Entry):
    pc: int
    msb: int | None = None
    lsb: int | None = None
    name: str


@dataclass(frozen=True, kw_only=True)
class CcPairEntry(Entry):
    msb: int
    lsb: int
    default: int | None = None
    name: str


@dataclass(frozen=True, kw_only=True)
class NrpnEntry(Entry):
    msb: int | None = None  # None when omitted, as in ":2000:7"
    lsb: int
    depth: int
    default: int | None = None
    name: str


@dataclass(frozen=True, kw_only=True)
class DrumEntry(Entry):
    row: int
    trig: int | None
    chan: int | str | None  # 1-16, "CV1"/"G2"/"CVG3", or None
    note: int | None
    name: str


@dataclass(frozen=True, kw_only=True)
class AutomationEntry(Entry):
    type: str  # CC NRPN CC_PAIR CV PB AT NULL
    cc: int | None = None
    msb: int | None = None  # NRPN MSB, or CC_PAIR MSB CC
    lsb: int | None = None
    depth: int | None = None
    cv: int | None = None
    extra: int | None = None  # the dropped :v in CC:74:100
    default: str | None = None  # raw, upper-cased: "100", "-2.5V"
    junk: bool = False  # text between the value and DEFAULT=


@dataclass(frozen=True, kw_only=True)
class AssignEntry(AutomationEntry):
    pot: int


@dataclass
class Section:
    name: str  # upper-cased
    start: int
    end: int | None  # None if never closed
    entries: list[Entry]


@dataclass
class Document:
    lines: list[str]  # raw, verbatim
    directives: list[Directive]
    sections: list[Section]
    parse_findings: list[Finding]


_START = {
    "CC": ("cc_entry", CcEntry),
    "PC": ("pc_entry", PcEntry),
    "CC_PAIR": ("ccpair_entry", CcPairEntry),
    "NRPN": ("nrpn_entry", NrpnEntry),
    "DRUMLANES": ("drum_entry", DrumEntry),
    "ASSIGN": ("assign_entry", AssignEntry),
    "AUTOMATION": ("automation_entry", AutomationEntry),
}
SECTIONS = {*_START, "COMMENT"}

_PARSER = Lark(
    (Path(__file__).parent / "grammar.lark").read_text(),
    parser="lalr",
    maybe_placeholders=True,
    start=["directive", *(start for start, _ in _START.values())],
)
_HEADER = re.compile(r"[ \t]*\[(/?)([^\]]*)\][ \t]*$")
_ALIAS = {"pc_msb": "msb", "pc_lsb": "lsb", "nrpn_msb": "msb", "pair_default": "default", "line_default": "default"}
_TYPES = {
    "TYPE_CC": "CC", "TYPE_NRPN": "NRPN", "TYPE_CC_PAIR": "CC_PAIR", "TYPE_CV": "CV",
    "TYPE_PB": "PB", "TYPE_AT": "AT", "NULL": "NULL",
}
_FRIENDLY = {
    "INT": "a number", "NULL": "NULL", "_COLON": "':'", "_WS": "a space", "NAME": "a name",
    "VALUE": "a value", "KEY": "a keyword", "DEFAULT": "DEFAULT=", "DEFVAL": "a default value",
    "CVPORT": "CVx, Gx or CVGx", "JUNK": "text", "PB_TAIL": "':'", "$END": "end of line",
    "TYPE_CC": "CC:", "TYPE_NRPN": "NRPN:", "TYPE_CC_PAIR": "CC_PAIR:", "TYPE_CV": "CV:",
    "TYPE_PB": "PB", "TYPE_AT": "AT",
}


def _span(token: Token) -> Span:
    return Span(token.column - 1, token.end_column - 1)


def _value(token: Token):
    match token.type:
        case "INT":
            return int(token)
        case "NULL":
            return None
        case "KEY" | "CVPORT" | "DEFVAL":
            return token.upper()
        case _:
            return str(token)


def _fields(tree: Tree) -> tuple[dict, dict[str, Span]]:
    values, spans = {}, {}
    for child in tree.children:
        if child is None:  # an absent [optional]
            continue
        if isinstance(child, Token):
            if child.type in _TYPES:
                values["type"], spans["type"] = _TYPES[child.type], _span(child)
            continue  # PB_TAIL: ignored by the Hapax
        name = _ALIAS.get(child.data, str(child.data))
        token = child.children[-1] if child.children else None
        if token is None:  # the omitted NRPN MSB
            values[name] = None
        elif name == "junk":
            values["junk"] = True
            first = spans.get("junk", _span(token))
            spans["junk"] = Span(first.start, _span(token).end)
        else:
            values[name], spans[name] = _value(token), _span(token)
    return values, spans


def _syntax(e: UnexpectedInput, text: str) -> tuple[Span, str]:
    if isinstance(e, UnexpectedToken) and e.token.type != "$END":
        span, found = _span(e.token), f"'{e.token}'"
    elif isinstance(e, UnexpectedCharacters):
        span, found = Span(e.column - 1, e.column), f"'{e.char}'"
    else:
        span, found = Span(len(text), len(text) + 1), "end of line"
    expected = getattr(e, "expected", None) or getattr(e, "allowed", None) or ()
    names = sorted({_FRIENDLY.get(n, n) for n in expected})
    listed = f"{', '.join(names[:-1])} or {names[-1]}" if len(names) > 1 else "".join(names)
    return span, f"expected {listed}, found {found}"


@lru_cache(maxsize=4096)
def _parse_line(start: str, text: str):
    """(values, spans, None) or (None, None, (span, message)).

    Cached so re-parsing a document after an edit only parses the edited line.
    Callers must not mutate the returned dicts.
    """
    try:
        tree = _PARSER.parse(text, start=start)
    except UnexpectedInput as e:
        return None, None, _syntax(e, text)
    return *_fields(tree), None


def _error(code: str, message: str, line: int, span: Span | None = None) -> Finding:
    return Finding(Severity.ERROR, code, message, line, span)


def parse(text: str) -> Document:
    findings = []
    if text.startswith("﻿"):
        text = text[1:]
        findings.append(Finding(
            Severity.WARNING, "file.bom", "file starts with a byte-order mark; untested on the Hapax, save without one", 1))
    doc = Document(text.split("\n"), [], [], findings)
    section: Section | None = None
    reported: set[int] = set()  # start lines of unknown sections already reported

    for n, raw in enumerate(doc.lines, 1):
        body = raw.split("#", 1)[0].rstrip()
        if not body.strip():
            continue

        if m := _HEADER.match(body):
            close, name = m[1], m[2].upper()
            indent = len(body) - len(body.lstrip())
            span = Span(indent, len(body))
            if close and section and name == section.name:
                section.end = n
                section = None
            elif close:
                findings.append(_error("section.stray_close", f"[/{name}] closes a section that is not open", n, span))
            else:
                if section:  # P15: reported at the next header
                    findings.append(_error(
                        "section.unclosed", f"[{section.name}] from line {section.start} is not closed", n, span))
                section = Section(name, n, None, [])
                doc.sections.append(section)
            continue

        if section and section.name == "COMMENT":
            continue
        if section and section.name not in _START:  # A11: reported on its first entry
            if section.start not in reported:
                reported.add(section.start)
                findings.append(_error("section.unknown", f"unknown section [{section.name}]", n))
            continue

        start, cls = _START[section.name] if section else ("directive", Directive)
        values, spans, error = _parse_line(start, body)
        if error:
            findings.append(_error("syntax", error[1], n, error[0]))
            continue
        entry = cls(line=n, raw=raw, spans=dict(spans), **values)
        (section.entries if section else doc.directives).append(entry)

    if section:  # open at end of file; unprobed (round 4, F04/F05)
        findings.append(_error("section.unclosed", f"[{section.name}] is never closed", section.start))
    for s in doc.sections:
        if s.name not in SECTIONS and s.start not in reported:
            findings.append(Finding(Severity.WARNING, "section.unknown_empty", f"unknown section [{s.name}]", s.start))
    return doc
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_parse.py -q`
Expected: all pass.
If Lark raises `GrammarError` (a reduce/reduce conflict), rename the colliding field rules rather than loosening shapes, and add the new name to `_ALIAS`.
If a syntax-error test fails only on `span.start`, print the exception type and `e.column`; the contextual lexer can report the token that the root lexer matched, which starts at the same column.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .python-version uv.lock hapax tests/test_parse.py
git commit -m "Parse definitions into a lossless model with Lark"
```

---

### Task 2: Entry rules and `validate()`

**Files:**
- Create: `hapax/rules.py`
- Modify: `hapax/__init__.py`
- Test: `tests/test_rules.py`

**Interfaces:**
- Consumes: everything Task 1 produces.
- Produces (in `hapax.rules`): `RELEASES: tuple[str, ...]`, `LATEST = (3, 21)`, `parse_fw(text) -> tuple[int, int]` (raises `ValueError` naming the supported releases), `fw_str(fw) -> str` (`(3, 0)` → `"3.00"`), `validate(doc, fw=LATEST) -> list[Finding]`, and `_document(doc, fw)` — a generator Task 3 fills in.

- [ ] **Step 1: Write the failing tests**

`tests/test_rules.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rules.py -q`
Expected: collection error, `ImportError: cannot import name 'LATEST' from 'hapax'`.

- [ ] **Step 3: Write the rules**

`hapax/rules.py`:

```python
"""Validation rules. Each constant and firmware comparison cites its source: a probe ID, a firmware version, or the template."""

import re
import string

from .parse import (
    AssignEntry, AutomationEntry, CcEntry, CcPairEntry, Directive, Document, DrumEntry,
    Entry, Finding, NrpnEntry, PcEntry, Severity, Span,
)

# squarp.net/hapax/firmware; below 1.12 the parser was "less strict" in undocumented ways.
RELEASES = (
    "1.12", "1.13", "1.14", "1.15", "1.16", "2.00", "2.01", "2.02", "2.03", "2.10",
    "2.11", "2.12", "2.13", "2.20", "2.21", "3.00", "3.10", "3.20", "3.21",
)
LATEST = (3, 21)

# Probes P01, P02, C01-C23; identical on 2.21 and 3.10. Tab is whitespace from 1.14.
NAME_CHARS = frozenset(string.ascii_letters + string.digits + " \t_-+!\"$'()*,./:<=>?@")
DIRECTIVES = {"VERSION", "TRACKNAME", "TYPE", "OUTPORT", "OUTCHAN", "INPORT", "INCHAN", "MAXRATE"}
TYPES = {"POLY", "DRUM", "MPE", "NULL"}
TYPES_3_20 = {"POLYAT", "AFTR"}  # 3.20 changelog; B01 rejected on 3.10
OUTPORTS = {"A", "B", "C", "D", "USBD", "USBH", "NULL"} | {f"{p}{x}" for p in ("CVG", "CV", "G") for x in range(1, 5)}
INPORTS = {"NONE", "ALLACTIVE", "A", "B", "USBD", "USBH", "CVG", "NULL"}
VIRTUAL_PORT = re.compile(r"(USBD|USBH)([0-9]+)")  # 1-16, from 3.00 (B03 rejected on 2.21)
CV_OUTPUT = re.compile(r"(CVG|CV|G)[1-4]")  # drum CHAN, template
MAXRATES = {192, 96, 64, 48, 32, 24, 16, 12, 8, 6, 4, 3, 2, 1}  # template; B05 rejects 5


def parse_fw(text: str) -> tuple[int, int]:
    if text not in RELEASES:
        raise ValueError(f"unsupported firmware {text!r}; choose one of {', '.join(RELEASES)}")
    major, minor = text.split(".")
    return int(major), int(minor)


def fw_str(fw: tuple[int, int]) -> str:
    return f"{fw[0]}.{fw[1]:02}"


def _error(code, message, entry, field=None):
    return Finding(Severity.ERROR, code, message, entry.line, entry.spans.get(field), field)


def _warning(code, message, entry, field=None):
    return Finding(Severity.WARNING, code, message, entry.line, entry.spans.get(field), field)


def _num(text: str) -> int | None:
    return int(text) if text.isascii() and text.isdigit() else None


def _range(kind, entry, field, lo, hi, label):
    value = getattr(entry, field)
    if value is not None and not lo <= value <= hi:
        yield _error(f"{kind}.range", f"{label} must be {lo}–{hi}, not {value}", entry, field)


def _name(entry, field="name"):
    text = getattr(entry, field)
    for i, ch in enumerate(text):
        if ch not in NAME_CHARS:
            start = entry.spans[field].start + i
            why = "names are ASCII only" if not ch.isascii() else "not allowed in names"
            yield Finding(Severity.ERROR, "name.char", f"{ch!r}: {why}", entry.line, Span(start, start + 1), field)
            return


def _section_default(kind, entry, fw, hi):
    if entry.default is None:
        return
    # 3.20 changelog: section defaults ignored in 3.00 and 3.10. 2.21 applies them (E01);
    # 3.10 does not even range-check them (A07).
    if (3, 0) <= fw < (3, 20):
        yield _warning(
            "default.ignored",
            f"DEFAULT is ignored on {fw_str(fw)} (honoured from 3.20); set it on the [AUTOMATION] line instead",
            entry, "default")
    else:
        yield from _range(kind, entry, "default", 0, hi, "DEFAULT")


def _nrpn_address(kind, entry):
    yield from _range(kind, entry, "msb", 0, 127, "MSB")
    # 1.12: LSB above 127 only when MSB is 0 or omitted (P04); 1:200:7 is rejected (A13)
    yield from _range(kind, entry, "lsb", 0, 127 if entry.msb else 16383, "LSB")
    if entry.depth not in (7, 14):
        yield _error(f"{kind}.range", f"DEPTH must be 7 or 14, not {entry.depth}", entry, "depth")


def _directive(e: Directive, fw):
    if e.key not in DIRECTIVES:  # P11
        yield _error("directive.unknown", f"unknown directive {e.key}", e, "key")
        return
    code = f"{e.key.lower()}.value"
    if e.value is None:
        yield _error(code, f"{e.key} needs a value", e, "key")
        return
    value = e.value.upper()
    bad = f"{e.key} {e.value} is not valid"
    match e.key:
        case "VERSION":
            if value != "1":  # B06 loads
                yield _warning("version", "VERSION should be 1", e, "value")
        case "TRACKNAME":
            yield from _name(e, "value")
        case "TYPE":
            if value in TYPES_3_20 and fw < (3, 20):
                yield _error(code, f"TYPE {value} needs firmware 3.20", e, "value")
            elif value not in TYPES | TYPES_3_20:
                yield _error(code, f"{bad}: POLY, DRUM, MPE, POLYAT, AFTR or NULL", e, "value")
        case "OUTPORT" | "INPORT":
            ports = OUTPORTS if e.key == "OUTPORT" else INPORTS
            virtual = VIRTUAL_PORT.fullmatch(value)
            if virtual and 1 <= int(virtual[2]) <= 16:
                if fw < (3, 0):
                    yield _error(code, f"virtual port {value} needs firmware 3.00", e, "value")
            elif value not in ports:
                yield _error(code, f"{bad}: {', '.join(sorted(ports))}, USBD1–16 or USBH1–16", e, "value")
        case "OUTCHAN" | "INCHAN":
            extra = {"NULL", "ALL"} if e.key == "INCHAN" else {"NULL"}
            n = _num(value)
            if value not in extra and not (n is not None and 1 <= n <= 16):
                yield _error(code, f"{bad}: 1–16 or {' or '.join(sorted(extra))}", e, "value")
        case "MAXRATE":
            if value != "NULL" and _num(value) not in MAXRATES:
                yield _error(code, f"{bad}: NULL, 192, 96, 64, 48, 32, 24, 16, 12, 8, 6, 4, 3, 2 or 1", e, "value")


def _cc(e: CcEntry, fw):
    yield from _range("cc", e, "cc", 0, 127, "CC")  # P12
    if 120 <= e.cc <= 127:  # A03 loads; A14, A15 reject 120 in ASSIGN and AUTOMATION
        yield _warning("cc.unusable", f"CC {e.cc} can be named but not used in [ASSIGN] or [AUTOMATION]", e, "cc")
    yield from _section_default("cc", e, fw, 127)
    yield from _name(e)


def _pc(e: PcEntry, fw):
    # PC is 1-128 in the file and 0-127 on the wire (manual §5.7); A08, A09. Do not "fix".
    yield from _range("pc", e, "pc", 1, 128, "PC")
    yield from _range("pc", e, "msb", 0, 127, "MSB")
    yield from _range("pc", e, "lsb", 0, 127, "LSB")
    yield from _name(e)


def _cc_pair(e: CcPairEntry, fw):
    # Ranges from the template; unprobed.
    yield from _range("cc_pair", e, "msb", 0, 127, "MSB CC")
    yield from _range("cc_pair", e, "lsb", 0, 127, "LSB CC")
    if e.default is not None and fw < (1, 14):  # 1.14 changelog: [CC_PAIR] defaults loaded
        yield _warning("default.ignored", "CC_PAIR DEFAULT is ignored before 1.14", e, "default")
    else:
        yield from _section_default("cc_pair", e, fw, 16383)
    yield from _name(e)


def _nrpn(e: NrpnEntry, fw):
    yield from _nrpn_address("nrpn", e)
    yield from _section_default("nrpn", e, fw, 16383 if e.depth == 14 else 127)
    yield from _name(e)


def _drum(e: DrumEntry, fw):
    rows = 16 if fw >= (3, 10) else 8  # 3.10 changelog; P05 row 16 rejected on 2.21
    yield from _range("drum", e, "row", 1, rows, "ROW")
    yield from _range("drum", e, "trig", 0, 127, "TRIG")
    if isinstance(e.chan, int):
        yield from _range("drum", e, "chan", 1, 16, "CHAN")
    elif e.chan is not None and not CV_OUTPUT.fullmatch(e.chan):
        yield _error("drum.range", f"CHAN {e.chan} must be 1–16, CVx, Gx or CVGx (x 1–4)", e, "chan")
    yield from _range("drum", e, "note", 0, 127, "NOTE")
    yield from _name(e)


def _line_default(kind, e: AutomationEntry):
    d = e.default
    if d is None or e.type in ("PB", "AT", "NULL"):  # template: ignored for PB and AT
        return
    if e.type == "CV":
        volts = d.endswith("V")
        ok = -5 <= float(d[:-1]) <= 5 if volts else _num(d) is not None and _num(d) <= 65535
        allowed = "0–65535 or -5V to 5V"
    else:
        hi = {"CC": 127, "CC_PAIR": 16383, "NRPN": 16383 if e.depth == 14 else 127}[e.type]
        ok = _num(d) is not None and _num(d) <= hi
        allowed = f"0–{hi}"
    if not ok:
        yield _error(f"{kind}.range", f"DEFAULT must be {allowed}, not {d}", e, "default")


def _target(kind, e: AutomationEntry, fw):
    match e.type:
        case "CC":
            yield from _range(kind, e, "cc", 0, 119, "CC")  # A14, A15
            if e.extra is not None:  # E05: loads, the value is silently dropped
                yield _warning(f"{kind}.extra", f"':{e.extra}' is ignored; write DEFAULT={e.extra}", e, "extra")
        case "NRPN":
            yield from _nrpn_address(kind, e)
        case "CC_PAIR":
            if fw < (1, 13):  # keyword table from 1.13; D01, D02 load on 3.10
                yield _error(f"{kind}.type", "CC_PAIR: needs firmware 1.13", e, "type")
            yield from _range(kind, e, "msb", 0, 127, "MSB CC")
            yield from _range(kind, e, "lsb", 0, 127, "LSB CC")
        case "CV":
            yield from _range(kind, e, "cv", 1, 4, "CV")
        case "NULL" if kind == "automation":
            yield _error("automation.type", "NULL is not an automation type", e, "type")
    if e.junk and e.type not in ("PB", "AT"):  # P06 pot 4 loads; effect unverified
        yield _warning(f"{kind}.text", "text before DEFAULT= loads, but its effect is unverified", e, "junk")
    yield from _line_default(kind, e)


def _assign(e: AssignEntry, fw):
    yield from _range("assign", e, "pot", 1, 8, "POT")
    yield from _target("assign", e, fw)


def _automation(e: AutomationEntry, fw):
    # DEFAULT= here is honoured on every firmware probed, and is the only default 3.00-3.10 apply (E02).
    yield from _target("automation", e, fw)


_ENTRY_RULES = {
    Directive: _directive, CcEntry: _cc, PcEntry: _pc, CcPairEntry: _cc_pair, NrpnEntry: _nrpn,
    DrumEntry: _drum, AssignEntry: _assign, AutomationEntry: _automation,
}


def _document(doc: Document, fw):
    yield from ()  # Task 3


def validate(doc: Document, fw: tuple[int, int] = LATEST) -> list[Finding]:
    findings = list(doc.parse_findings)
    entries: list[Entry] = [*doc.directives, *(e for s in doc.sections for e in s.entries)]
    for e in entries:
        findings.extend(_ENTRY_RULES[type(e)](e, fw))
    findings.extend(_document(doc, fw))
    return sorted(findings, key=lambda f: (f.line, f.span.start if f.span else -1))
```

`hapax/__init__.py`:

```python
from .parse import Document, Finding, Severity, Span, parse
from .rules import LATEST, RELEASES, parse_fw, validate

__all__ = ["LATEST", "RELEASES", "Document", "Finding", "Severity", "Span", "parse", "parse_fw", "validate"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add hapax tests/test_rules.py
git commit -m "Check ranges, names, directives and firmware rules per entry"
```

---

### Task 3: Document rules

**Files:**
- Modify: `hapax/rules.py` (replace the `_document` stub)
- Test: `tests/test_rules.py` (append)

**Interfaces:**
- Consumes: `Document`, entry classes, `_error`, `_warning`, `fw_str` from Tasks 1–2.
- Produces: `_document(doc, fw)` yielding the tab, duplicate, count, drum-type and MPE findings.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rules.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rules.py -q`
Expected: FAIL on duplicate, count, tab, drum-type and MPE cases (`[] != [...]`); the `assign.extra`, `assign.text`, `cc.unusable` and "every mistake" cases already pass.

- [ ] **Step 3: Implement**

Replace the `_document` stub in `hapax/rules.py`:

```python
def _null(v):
    return "NULL" if v is None else v


def _nrpn_key(e):
    # 0:1026:7 and :1026:7 address the same parameter as 8:2:7 (template)
    return divmod(e.lsb, 128) if not e.msb else (e.msb, e.lsb)


def _duplicates(entries, key, code, label):
    first = {}
    for e in entries:
        k = key(e)
        if k in first:
            yield _warning(code, f"{label(e)} is already defined on line {first[k]}", e)
        else:
            first[k] = e.line


def _document(doc: Document, fw):
    if fw < (1, 14):  # 1.14 changelog: tabs no longer break loading
        for n, raw in enumerate(doc.lines, 1):
            if (i := raw.find("\t")) >= 0:
                yield Finding(Severity.ERROR, "tab", "tabs break loading before 1.14; use spaces", n, Span(i, i + 1))

    yield from _duplicates(doc.directives, lambda d: d.key, "directive.duplicate", lambda d: d.key)  # B07 loads

    def section(name):
        return [e for s in doc.sections if s.name == name for e in s.entries]

    cc, pc, pairs, nrpn = section("CC"), section("PC"), section("CC_PAIR"), section("NRPN")
    drums, assign, automation = section("DRUMLANES"), section("ASSIGN"), section("AUTOMATION")
    yield from _duplicates(cc, lambda e: e.cc, "cc.duplicate", lambda e: f"CC {e.cc}")  # A05 loads
    yield from _duplicates(
        pc, lambda e: (e.pc, e.msb, e.lsb), "pc.duplicate",
        lambda e: f"PC {e.pc}:{_null(e.msb)}:{_null(e.lsb)}")
    yield from _duplicates(
        pairs, lambda e: (e.msb, e.lsb), "cc_pair.duplicate", lambda e: f"CC pair {e.msb}:{e.lsb}")
    yield from _duplicates(
        nrpn, _nrpn_key, "nrpn.duplicate", lambda e: "NRPN {}:{}".format(*_nrpn_key(e)))
    yield from _duplicates(drums, lambda e: e.row, "drum.duplicate", lambda e: f"drum row {e.row}")  # P05 loads
    yield from _duplicates(assign, lambda e: e.pot, "assign.duplicate", lambda e: f"pot {e.pot}")

    if len(automation) > 64:  # P08: the 65th lane is rejected
        yield _error("automation.count", "more than 64 automation lanes", automation[64])
    if len(pc) > 128:  # template limit; P09 shows 3.10 loads 129
        yield _warning("pc.count", "more than 128 PCs; the template's limit", pc[128])

    last = {d.key: d for d in doc.directives if d.value}  # which duplicate wins is unprobed; assume the last
    track_type = last["TYPE"].value.upper() if "TYPE" in last else None
    # The hardware discards [DRUMLANES] on a non-DRUM track; TYPE NULL keeps the current type, which may be DRUM.
    if drums and track_type in ("POLY", "MPE", "POLYAT", "AFTR"):
        yield _warning("drum.not_drum", f"[DRUMLANES] is discarded on a {track_type} track", drums[0])
    inport = last.get("INPORT")
    if track_type == "MPE" and inport and inport.value.upper() in ("A", "B"):  # 3.20 changelog
        yield _warning("inport.mpe", f"MPE cannot use DIN input port {inport.value.upper()}", inport, "value")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add hapax/rules.py tests/test_rules.py
git commit -m "Add document rules: duplicates, lane and PC counts, tabs, track type"
```

---

### Task 4: Hardware probes, corpus and performance

**Files:**
- Test: `tests/test_probes.py`, `tests/test_corpus.py`
- Modify: `hapax/rules.py` or `hapax/grammar.lark` only if a probe or the author's corpus disagrees (see Step 3)

**Interfaces:**
- Consumes: `parse`, `validate`, `Severity`, `LATEST` from `hapax`; `hapax.parse._parse_line` for the cold-cache timing.

- [ ] **Step 1: Write the tests**

`tests/test_probes.py`:

```python
"""The validator's first error must land where the hardware reported it."""

from pathlib import Path

import pytest

from hapax import Severity, parse, validate

PROBES = Path(__file__).parent.parent / "testdata" / "probes"

# First rejected line, or None for "loads". Transcribed from RESULTS.md and r2/RESULTS.md (OS 3.10).
ON_3_10 = {
    "P00_BASE": None, "P01_NAMES": 23, "P02_TRKNAME": None, "P03_CCSYN": 20, "P04_NRPN": None,
    "P05_DRUM16": None, "P06_ASSIGN": None, "P07_AUTO": None, "P08_AUTO65": 90, "P09_PC129": None,
    "P10_CCPAIR": None, "P11_UNKDIR": 9, "P12_BADENT": 18, "P13_MINIMAL": None, "P14_NOVER": None,
    "P15_UNTERM": 19, "P16_LOWER": None, "P17_CRLF": None,
    "A01_CC_SHORTHAND": None, "A02_CC_LEADZERO": None, "A03_CC_120": None, "A04_CC_127": None,
    "A05_CC_DUP": None, "A06_CC_NONAME": 6, "A07_CC_DEF128": None, "A08_PC_0": 6, "A09_PC_129": 6,
    "A10_DRUM_ON_POLY": None, "A11_UNKNOWN_SECT": 6, "A12_LOWER_SECT": None,
    "A13_NRPN_MSB1_LSB200": 6, "A14_ASSIGN_CC120": 6, "A15_AUTO_CC120": 6,
    "B01_TYPE_POLYAT": 4, "B02_TYPE_lower": None, "B03_OUTPORT_USBD1": None, "B04_OUTCHAN_17": 4,
    "B05_MAXRATE_5": 4, "B06_VERSION_2": None, "B07_DUP_DIRECTIVE": None, "B08_TRACKNAME_AMP": 3,
    "D01_AUTO_CCPAIR": None, "D02_ASSIGN_CCPAIR": None,
    **{f"C{i:02}": None for i in range(1, 24)},
    **{f"C{i:02}": 5 for i in (4, 7, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22)},
}
# Round 3 on 2.21 (r3/RESULTS.md): P05, every r2 file and the E files; differences from 3.10 only.
ON_2_21 = {
    **{k: v for k, v in ON_3_10.items() if not k.startswith("P")},
    "P05_DRUM16": 11, "A07_CC_DEF128": 6, "B03_OUTPORT_USBD1": 4,
    "E01_CC_SECTION_DEFAULT": None, "E02_AUTO_LINE_DEFAULT": None, "E03_CC_SHORTHAND_DEFAULT": None,
    "E04_NRPN_BARE_DEFAULT": None, "E05_ASSIGN_EXTRA_FIELD": None,
}


def key(path):
    return path.stem[:3] if path.stem.startswith("C") else path.stem


def probe_files(outcomes):
    return [p for p in sorted(PROBES.rglob("*.txt")) if key(p) in outcomes]


def check(path, fw):
    return validate(parse(path.read_text(encoding="utf-8")), fw)


def first_error(path, fw):
    errors = [f.line for f in check(path, fw) if f.severity is Severity.ERROR]
    return errors[0] if errors else None


def test_every_recorded_probe_is_found():
    assert len(probe_files(ON_3_10)) == 66
    assert len(probe_files(ON_2_21)) == 54


@pytest.mark.parametrize("path", probe_files(ON_3_10), ids=lambda p: p.stem)
def test_probe_on_3_10(path):
    assert first_error(path, (3, 10)) == ON_3_10[key(path)]


@pytest.mark.parametrize("path", probe_files(ON_2_21), ids=lambda p: p.stem)
def test_probe_on_2_21(path):
    assert first_error(path, (2, 21)) == ON_2_21[key(path)]


@pytest.mark.parametrize("stem, fw, code", [
    ("P00_BASE", (3, 10), "default.ignored"),
    ("P04_NRPN", (3, 10), "default.ignored"),
    ("P05_DRUM16", (3, 10), "drum.duplicate"),
    ("P06_ASSIGN", (3, 10), "assign.extra"),
    ("P06_ASSIGN", (3, 10), "assign.text"),
    ("P09_PC129", (3, 10), "pc.count"),
    ("P10_CCPAIR", (3, 10), "default.ignored"),
    ("A03_CC_120", (3, 10), "cc.unusable"),
    ("A05_CC_DUP", (3, 10), "cc.duplicate"),
    ("A07_CC_DEF128", (3, 10), "default.ignored"),
    ("A10_DRUM_ON_POLY", (3, 10), "drum.not_drum"),
    ("B06_VERSION_2", (3, 10), "version"),
    ("B07_DUP_DIRECTIVE", (3, 10), "directive.duplicate"),
    ("E01_CC_SECTION_DEFAULT", (3, 10), "default.ignored"),
    ("E03_CC_SHORTHAND_DEFAULT", (3, 10), "default.ignored"),
    ("E05_ASSIGN_EXTRA_FIELD", (2, 21), "assign.extra"),
])
def test_accepted_probes_that_should_warn(stem, fw, code):
    [path] = PROBES.rglob(f"{stem}.txt")
    assert code in [f.code for f in check(path, fw) if f.severity is Severity.WARNING]
```

`tests/test_corpus.py`:

```python
import time
from pathlib import Path

import pytest

from hapax import LATEST, Severity, parse, validate
from hapax.parse import _parse_line

TESTDATA = Path(__file__).parent.parent / "testdata"
MINE = sorted((TESTDATA / "mine").glob("*.txt"))
COMMUNITY = sorted(p for p in (TESTDATA / "community").rglob("*.txt") if p.name != "template.txt")


def check(path, fw=LATEST):
    return validate(parse(path.read_text(encoding="utf-8")), fw)


def test_corpus_is_present():
    assert (len(MINE), len(COMMUNITY)) == (14, 154)


@pytest.mark.parametrize("path", MINE, ids=lambda p: p.name)
def test_authors_files_have_no_errors_on_3_10(path):
    assert [f for f in check(path, (3, 10)) if f.severity is Severity.ERROR] == []


@pytest.mark.parametrize("path", COMMUNITY, ids=lambda p: str(p.relative_to(TESTDATA / "community")))
def test_community_files_validate_without_raising(path):
    check(path)


@pytest.mark.parametrize("rel, line, code", [
    ("uptown/flash.txt", 13, "directive.unknown"),  # OUTAN
    ("toraiz/as-1.txt", 79, "syntax"),  # 105:LPF VEL
    ("pandamidi/future_impact.txt", 13, "syntax"),  # DEFAULT=NULL
])
def test_known_community_mistakes(rel, line, code):
    assert (code, line) in [(f.code, f.line) for f in check(TESTDATA / "community" / rel)]


def test_novation_peak_validates_in_under_50ms_cold():
    text = (TESTDATA / "mine" / "Novation_Peak.txt").read_text(encoding="utf-8")
    _parse_line.cache_clear()
    start = time.perf_counter()
    validate(parse(text), (3, 10))
    assert time.perf_counter() - start < 0.05
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/test_probes.py tests/test_corpus.py -q`
Expected: all pass. These suites pin the rules to the hardware, so a failure here is information, not noise.

- [ ] **Step 3: If anything fails, find which side is wrong before changing code**

- A probe mismatch: open the probe file at the reported line and the hardware's line, and read the matching `RESULTS.md` row.
  The hardware is the authority; change the rule, and cite the probe in its comment.
- An error in `testdata/mine/` on 3.10: these files load on the author's 3.10, so the rule is too strict.
  Check the rule against the spec and the probes; loosen it or turn it into a warning, and record why in a comment.
  Never edit files under `testdata/`.
- The count assertions: `ON_3_10` matches 66 files and `ON_2_21` 54; if a count differs, a key does not match a file stem.

Rerun until green: `uv run pytest -q`.

- [ ] **Step 4: Commit**

```bash
git add tests/test_probes.py tests/test_corpus.py hapax
git commit -m "Pin the validator to the hardware probes and the corpus"
```

---

### Task 5: CLI

**Files:**
- Create: `hapax/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `parse` from `hapax.parse`; `validate`, `parse_fw`, `fw_str`, `LATEST`, `RELEASES` from `hapax.rules`; `Finding`, `Severity`.
- Produces: `main(argv: list[str] | None = None) -> int`, the `hapax` console script.

- [ ] **Step 1: Write the failing tests**

`tests/test_cli.py`:

```python
import pytest

from hapax.cli import main


def run(args):
    try:
        return main(args)
    except SystemExit as e:  # argparse usage errors
        return e.code


def write(directory, name, text):
    path = directory / name
    path.write_text(text)
    return path


def test_clean_directory_skips_dotfiles_and_backups(tmp_path, capsys):
    write(tmp_path, "A.txt", "VERSION 1\n")
    write(tmp_path, "B.TXT", "VERSION 1\n")
    write(tmp_path, "._A.txt", "\x00\x01")  # macOS resource fork
    write(tmp_path, "C.txt.bak", "junk")  # 3.00 ignores .txt.bak
    assert run(["validate", str(tmp_path)]) == 0
    assert capsys.readouterr().out == (
        "A.txt  OK\n"
        "B.TXT  OK\n"
        "\n"
        "2 files, 0 errors, 0 warnings — Hapax OS 3.21\n"
    )


def test_findings_are_listed_under_their_file(tmp_path, capsys):
    path = write(tmp_path, "bad.txt", "VERSION 2\nOUTCHAN 17\n")
    assert run(["validate", "--fw", "3.10", str(path)]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"{path}  1 error, 1 warning"
    assert out[1].startswith("  W line 1: ")
    assert out[2].startswith("  E line 2: ")
    assert out[-1] == "1 file, 1 error, 1 warning — Hapax OS 3.10"


def test_warnings_count_only_with_strict(tmp_path):
    path = write(tmp_path, "w.txt", "VERSION 2\n")
    assert run(["validate", str(path)]) == 0
    assert run(["validate", "--strict", str(path)]) == 1


def test_file_that_is_not_utf8_is_an_error_and_others_still_run(tmp_path, capsys):
    (tmp_path / "a.txt").write_bytes(b"TRACKNAME \xff\n")
    write(tmp_path, "b.txt", "VERSION 1\n")
    assert run(["validate", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "a.txt  1 error\n  E file: " in out
    assert "b.txt  OK" in out


def test_no_paths_means_the_current_directory(tmp_path, monkeypatch, capsys):
    write(tmp_path, "A.txt", "VERSION 1\n")
    monkeypatch.chdir(tmp_path)
    assert run(["validate"]) == 0
    assert capsys.readouterr().out.startswith("A.txt  OK\n")


@pytest.mark.parametrize("args", [
    ["validate", "does-not-exist"],
    ["validate", "--fw", "3.11", "."],
    ["validate", "--fw", "1.11", "."],
    [],
])
def test_usage_and_io_failures_exit_2(args, tmp_path, monkeypatch):
    write(tmp_path, "A.txt", "VERSION 1\n")
    monkeypatch.chdir(tmp_path)
    assert run(args) == 2


def test_no_txt_files_exits_2(tmp_path):
    assert run(["validate", str(tmp_path)]) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'hapax.cli'`.

- [ ] **Step 3: Implement**

`hapax/cli.py`:

```python
"""hapax validate [--strict] [--fw VERSION] [paths...]"""

import argparse
import sys
from pathlib import Path

from .parse import Finding, Severity, parse
from .rules import LATEST, RELEASES, fw_str, parse_fw, validate


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _files(paths: list[Path]) -> list[tuple[str, Path]] | str:
    """(display name, path) pairs, or an error message."""
    files = []
    for p in paths:
        if p.is_dir():
            files += [
                (f.name, f) for f in sorted(p.glob("*.txt", case_sensitive=False))
                if f.is_file() and not f.name.startswith(".")  # macOS writes ._Name.txt beside every copy
            ]
        elif p.is_file():
            if not p.name.startswith("."):
                files.append((str(p), p))
        else:
            return f"{p}: no such file or directory"
    return files or "no .txt files found"


def _check(path: Path, fw) -> list[Finding]:
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as e:
        return [Finding(Severity.ERROR, "encoding", f"not valid UTF-8 (byte {e.start})", 0)]
    return validate(parse(text), fw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hapax", description="Squarp Hapax instrument definition tools")
    commands = parser.add_subparsers(dest="command", required=True)
    cmd = commands.add_parser("validate", help="check instrument definitions before copying them to the SD card")
    cmd.add_argument("paths", nargs="*", type=Path, default=[Path(".")], help="files or directories (default: .)")
    cmd.add_argument(
        "--fw", default=fw_str(LATEST),
        help=f"target firmware, {RELEASES[0]} to {RELEASES[-1]} (default: %(default)s)")
    cmd.add_argument("--strict", action="store_true", help="warnings also fail the exit code")
    args = parser.parse_args(argv)

    try:
        fw = parse_fw(args.fw)
    except ValueError as e:
        parser.error(str(e))
    files = _files(args.paths)
    if isinstance(files, str):
        print(f"hapax: {files}", file=sys.stderr)
        return 2

    width = max(len(name) for name, _ in files) + 2
    errors = warnings = 0
    for name, path in files:
        try:
            findings = _check(path, fw)
        except OSError as e:
            print(f"hapax: {e}", file=sys.stderr)
            return 2
        errs = sum(f.severity is Severity.ERROR for f in findings)
        warns = len(findings) - errs
        errors, warnings = errors + errs, warnings + warns
        status = ", ".join([_plural(errs, "error")] * bool(errs) + [_plural(warns, "warning")] * bool(warns)) or "OK"
        print(f"{name:<{width}}{status}")
        for f in findings:
            where = f"line {f.line}" if f.line else "file"
            print(f"  {'E' if f.severity is Severity.ERROR else 'W'} {where}: {f.message}")

    print(f"\n{_plural(len(files), 'file')}, {_plural(errors, 'error')}, "
          f"{_plural(warnings, 'warning')} — Hapax OS {fw_str(fw)}")
    return 1 if errors or (args.strict and warnings) else 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 5: Run it for real**

Run: `uv run hapax validate --fw 3.10 testdata/mine`
Expected: 14 files, 0 errors, a few hundred warnings (the spec's example says 304, mostly `default.ignored`), exit 1 only if there are errors — `echo $?` prints `0`.

Run: `uv run hapax validate testdata/community/uptown`
Expected: `flash.txt` lists `E line 13: unknown directive OUTAN`; exit 1.

- [ ] **Step 6: Commit**

```bash
git add hapax/cli.py tests/test_cli.py
git commit -m "Add the hapax validate command"
```
