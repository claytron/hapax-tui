"""Repair what has exactly one sensible repair; see docs/superpowers/specs/2026-09-27-hapax-fix-design.md."""

from dataclasses import dataclass, replace

from .parse import Document, parse
from .rules import LATEST, validate
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


_FIXES = {
    "section.unclosed": _close,
    "section.unclosed_eof": _close,
    "section.stray_close": _stray,
    "version": _version,
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
