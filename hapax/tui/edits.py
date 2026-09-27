"""Pure operations on a document's lines, the editor's source of truth. No Textual imports."""

from collections import Counter
from dataclasses import replace
from pathlib import Path

from ..fix import Applied, fix
from ..parse import Document, Entry, Finding, Section, parse
from ..rules import validate
from ..write import eol, render
from .sections import HEADER

# No typed entry a form could show; the file is fixed in a text editor instead.
STRUCTURAL = {"encoding", "syntax", "section.unknown", "directive.unknown"}
# Also broken structure; the fixer repairs the first three before a file opens, and an edit may not add any.
BREAKING = STRUCTURAL | {"section.unclosed", "section.unclosed_eof", "section.stray_close", "section.unknown_empty"}


def analyse(lines: list[str], fw) -> tuple[Document, list[Finding]]:
    doc = parse("\n".join(lines))
    return doc, validate(doc, fw)


def breaks(before: list[Finding], after: list[Finding]) -> list[Finding]:
    """The structural findings an edit added; the editor refuses such an edit."""
    added = Counter(f.code for f in after if f.code in BREAKING) - Counter(f.code for f in before if f.code in BREAKING)
    return [f for f in after if added[f.code]]


def open_text(text: str | Finding, fw) -> tuple[str, list[Applied], list[Finding]]:
    """What the open gate needs: (fixed text, fixes applied, findings that refuse opening)."""
    if isinstance(text, Finding):  # not UTF-8
        return "", [], [text]
    fixed, applied = fix(text, fw)
    return fixed, applied, [f for f in validate(parse(fixed), fw) if f.code in BREAKING]


def set_line(lines: list[str], n: int, text: str) -> list[str]:
    """Line n replaced, keeping its line ending."""
    new = list(lines)
    new[n - 1] = text.removesuffix("\r") + ("\r" if lines[n - 1].endswith("\r") else "")
    return new


def insert_line(lines: list[str], after: int, text: str) -> list[str]:
    """text as a new line after line `after` (0: first)."""
    return [*lines[:after], text + eol(lines), *lines[after:]]


def delete_line(lines: list[str], n: int) -> list[str]:
    return [*lines[: n - 1], *lines[n:]]


def rows(doc: Document, section: Section) -> list[int]:
    """Line numbers of a section's table rows: every non-blank line between its tags."""
    stop = section.end or len(doc.lines) + 1
    return [n for n in range(section.start + 1, stop) if doc.lines[n - 1].strip()]


def tab_of(doc: Document, line: int) -> int | None:
    """Index of the section holding a line; None for the header and the whole file (line 0)."""
    for i, s in enumerate(doc.sections):
        if s.start <= line <= (s.end or len(doc.lines)):
            return i
    return None


def move_row(lines: list[str], doc: Document, section: Section, n: int, step: int) -> tuple[list[str], int] | None:
    """Swap row n with the row `step` (-1 or 1) away; None at either end. Blank lines stay put."""
    rs = rows(doc, section)
    i = rs.index(n) + step
    if not 0 <= i < len(rs):
        return None
    other = rs[i]
    return set_line(set_line(lines, n, lines[other - 1]), other, lines[n - 1]), other


def add_row(lines: list[str], section: Section, after: int | None, text: str) -> tuple[list[str], int]:
    """text as a new row after line `after`, or first in the section; (lines, its line number)."""
    at = section.start if after is None else after
    return insert_line(lines, at, text), at + 1


def add_section(lines: list[str], name: str) -> list[str]:
    """[name] and [/name] at the end of the file, before its final newline."""
    end = len(lines) - (lines[-1] == "")
    tail = eol(lines)
    return [*lines[:end], f"[{name}]{tail}", f"[/{name}]{tail}", *lines[end:]]


def set_body(lines: list[str], section: Section, text: str) -> list[str]:
    """A section's lines between its tags replaced by text (a COMMENT section's TextArea)."""
    tail = eol(lines)
    body = [line + tail for line in text.split("\n")] if text else []
    return [*lines[: section.start], *body, *lines[section.end - 1 :]]


def body_text(lines: list[str], section: Section) -> str:
    return "\n".join(line.removesuffix("\r") for line in lines[section.start : section.end - 1])


def set_directive(lines: list[str], doc: Document, key: str, value: str | None) -> list[str]:
    """Set, add or (value None) remove a header directive; with duplicates, the last one is the one that counts."""
    existing = [d for d in doc.directives if d.key == key]
    if existing:
        d = existing[-1]
        return delete_line(lines, d.line) if value is None else set_line(lines, d.line, render(replace(d, value=value)))
    if value is None:
        return lines
    return insert_line(lines, doc.directives[-1].line if doc.directives else 0, f"{key} {value}")


def row_text(cls: type[Entry], original: Entry | None, values: dict[str, str]) -> str:
    """The line a row form's values make. Blank is absent or NULL; a blank name renders nothing, a syntax error."""
    fields = {k: v.strip() or ("" if k == "name" else None) for k, v in values.items()}
    entry = replace(original, **fields) if original else cls(line=0, raw="", spans={}, **fields)
    return render(entry)


def comment_text(raw: str, value: str) -> str:
    """A comment row's line after editing the text that follows its '#'."""
    return raw[: raw.index("#") + 1] + value if "#" in raw else f"#{value}"


def comment_value(raw: str) -> str:
    return raw.removesuffix("\r").split("#", 1)[1]


def new_file_text(values: dict[str, str | None]) -> str:
    return "".join(["VERSION 1\n", *(f"{k} {values[k]}\n" for k in HEADER if values.get(k))])


def new_file_path(directory: Path, name: str) -> Path | str:
    """Where a new definition goes, or why it cannot."""
    name = name.strip()
    if not name.removesuffix(".txt"):
        return "enter a file name"
    if "/" in name or name.startswith("."):
        return "a plain file name, not a path or a hidden file"
    if not name.lower().endswith(".txt"):
        name += ".txt"
    if any(p.name.lower() == name.lower() for p in directory.iterdir()):  # SD cards are case-insensitive
        return f"{name} already exists"
    return directory / name
