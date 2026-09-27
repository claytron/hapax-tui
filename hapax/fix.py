"""Repair what has exactly one sensible repair; see docs/superpowers/specs/2026-09-27-hapax-fix-design.md."""

import unicodedata
from dataclasses import dataclass, replace

from .parse import AutomationEntry, CcEntry, CcPairEntry, Document, NrpnEntry, Severity, parse
from .rules import LATEST, _automation, _nrpn_key, _target, validate
from .write import eol, render


@dataclass(frozen=True)
class Applied:
    code: str
    line: int  # in the document the fix ran on
    description: str


def _indent(raw: str) -> str:
    return raw[: len(raw) - len(raw.lstrip(" \t"))]


def _last_used(doc: Document, start: int, stop: int) -> int:
    """The last non-blank line from start up to, not including, stop (1-based)."""
    return next(n for n in range(stop - 1, start - 1, -1) if doc.lines[n - 1].strip())


def _close(f, doc, at, fw):
    # section.unclosed is reported at the next header; section.unclosed_eof at the open header.
    stop = f.line if f.code == "section.unclosed" else len(doc.lines) + 1
    section = max((s for s in doc.sections if s.end is None and s.start < stop), key=lambda s: s.start)
    n = _last_used(doc, section.start, stop)
    # ponytail: a CRLF file without a final newline gets "\r" on the new last line only; harmless to the parser.
    close = f"{_indent(doc.lines[section.start - 1])}[/{section.name}]{eol(doc.lines)}"
    return {n: [doc.lines[n - 1], close]}, f"closed [{section.name}]"


def _stray(f, doc, at, fw):
    raw = doc.lines[f.line - 1]
    keep = [_indent(raw) + raw[raw.index("#"):]] if "#" in raw else []
    return {f.line: keep}, f"removed stray {raw.split('#', 1)[0].strip()}"


def _version(f, doc, at, fw):
    entry = at[f.line]
    return {f.line: [render(replace(entry, value="1"))]}, f"VERSION {entry.value} → 1"


# Letters NFKD does not decompose, and punctuation word processors substitute.
_TABLE = str.maketrans({
    "ß": "ss", "æ": "ae", "Æ": "AE", "ø": "o", "Ø": "O",
    "‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
})


def transliterate(text: str) -> str:
    """Nearest ASCII for accented letters and typographic punctuation; anything else is left as is."""
    return "".join(_ascii(ch) for ch in text)


def _ascii(ch: str) -> str:
    decomposed = unicodedata.normalize("NFKD", ch.translate(_TABLE))
    new = "".join(c for c in decomposed if not unicodedata.combining(c))
    return new if new.isascii() else ch  # ガ -> カ would be a different letter, not a fix


def _name_char(f, doc, at, fw):
    entry = at[f.line]
    old = getattr(entry, f.field)
    new = transliterate(old)
    if new == old:
        return None
    return {f.line: [render(replace(entry, **{f.field: new}))]}, f"{old!r} → {new!r}"


def _extra(f, doc, at, fw):
    entry = at[f.line]
    lands = replace(entry, extra=None, default=str(entry.extra))
    kind = f.code.split(".")[0]  # automation or assign
    if entry.default is None and not any(g.severity is Severity.ERROR for g in _target(kind, lands, fw)):
        new, description = lands, f":{entry.extra} → DEFAULT={entry.extra}"
    else:
        new, description = replace(entry, extra=None), f"removed ignored :{entry.extra}"
    return {f.line: [render(new)]}, description


def _lane(e: AutomationEntry):
    """What an [AUTOMATION] line controls; lines with equal lanes are the same lane."""
    match e.type:
        case "CC":
            return "CC", e.cc
        case "CC_PAIR":
            return "CC_PAIR", e.msb, e.lsb
        case "NRPN":
            return "NRPN", *_nrpn_key(e), e.depth
    return None


def _lane_for(e, default: str) -> AutomationEntry:
    match e:
        case CcEntry():
            target = dict(type="CC", cc=e.cc)
        case CcPairEntry():
            target = dict(type="CC_PAIR", msb=e.msb, lsb=e.lsb)
        case NrpnEntry():
            target = dict(type="NRPN", msb=e.msb, lsb=e.lsb, depth=e.depth)
    return AutomationEntry(line=0, raw="", spans={}, default=default, **target)


def _move_default(f, doc, at, fw):
    if not (3, 0) <= fw < (3, 20):  # CC_PAIR before 1.14 has no automation-side equivalent
        return None
    entry = at[f.line]
    lane = _lane_for(entry, str(entry.default))
    if any(g.severity is Severity.ERROR for g in _automation(lane, fw)):  # CC 120-127, bad NRPN address
        return None
    sections = [s for s in doc.sections if s.name == "AUTOMATION"]
    automation = [a for s in sections for a in s.entries]
    edits = {f.line: [render(replace(entry, default=None))]}
    same = next((a for a in automation if _lane(a) == _lane(lane)), None)
    if same and same.default not in (None, lane.default):
        return None
    if same and same.default is None:
        edits[same.line] = [render(replace(same, default=lane.default))]
    elif not same:
        if len(automation) >= 64 or sections and sections[0].end is None:
            return None
        new = render(lane) + eol(doc.lines)
        if sections:
            n = _last_used(doc, sections[0].start, sections[0].end)
            edits[n] = [doc.lines[n - 1], _indent(doc.lines[n - 1]) + new]
        else:
            n = _last_used(doc, 1, len(doc.lines) + 1)
            edits[n] = [doc.lines[n - 1], "[AUTOMATION]" + eol(doc.lines), new, "[/AUTOMATION]" + eol(doc.lines)]
    return edits, f"moved DEFAULT={entry.default} to [AUTOMATION]"


_FIXES = {
    "section.unclosed": _close,
    "section.unclosed_eof": _close,
    "section.stray_close": _stray,
    "version": _version,
    "name.char": _name_char,
    "automation.extra": _extra,
    "assign.extra": _extra,
    "default.ignored": _move_default,
}


def fix(text: str, fw: tuple[int, int] = LATEST) -> tuple[str, list[Applied]]:
    applied = []
    if text.startswith("﻿"):
        text = text[1:]
        applied.append(Applied("file.bom", 1, "removed the byte-order mark"))
    while True:  # every fix removes its finding, so each pass makes progress
        doc = parse(text)
        at = {e.line: e for e in [*doc.directives, *(e for s in doc.sections for e in s.entries)]}
        edits: dict[int, list[str]] = {}
        for f in validate(doc, fw):
            result = _FIXES[f.code](f, doc, at, fw) if f.code in _FIXES else None
            if result and not edits.keys() & result[0].keys():
                edits |= result[0]
                applied.append(Applied(f.code, f.line, result[1]))
        if not edits:
            return text, applied
        lines = doc.lines
        for n in sorted(edits, reverse=True):
            lines[n - 1 : n] = edits[n]
        text = "\n".join(lines)
