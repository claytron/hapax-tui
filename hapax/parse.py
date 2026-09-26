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
        body = raw.split("#", 1)[0].rstrip(" \t\r")  # only what _WS matches; other whitespace is a name character error
        if not body.strip(" \t"):
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
