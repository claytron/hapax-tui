"""Turn model entries back into lines; see docs/superpowers/specs/2026-09-27-hapax-fix-design.md."""

from .parse import (
    AssignEntry, AutomationEntry, CcEntry, CcPairEntry, CommentLine, Directive, DrumEntry, Entry, NrpnEntry, PcEntry,
)


def _null(v) -> str:
    return "NULL" if v is None else str(v)


def _blank(v) -> str:
    return "" if v is None else str(v)


def _default(v) -> str:
    return "" if v is None else f":DEFAULT={v}"


def _target(e: AutomationEntry) -> str:
    match e.type:
        case "CC":
            target = f"CC:{e.cc}" + ("" if e.extra is None else f":{e.extra}")
        case "NRPN":
            target = f"NRPN:{_blank(e.msb)}:{e.lsb}:{e.depth}"
        case "CC_PAIR":
            target = f"CC_PAIR:{e.msb}:{e.lsb}"
        case "CV":
            target = f"CV:{e.cv}"
        case _:  # PB, AT, NULL
            target = e.type
    parts = [target]
    if e.junk:  # the model records only that it is there; keep it verbatim
        span = e.spans["junk"]
        parts.append(e.raw[span.start:span.end])
    if e.default is not None:
        parts.append(f"DEFAULT={e.default}")
    return " ".join(parts)


def _body(e: Entry) -> str:
    match e:
        case Directive():
            return e.key if e.value is None else f"{e.key} {e.value}"
        case CcEntry():
            return f"{e.cc}{_default(e.default)} {e.name}"
        case PcEntry():
            address = "" if e.msb is None and e.lsb is None else f":{_null(e.msb)}:{_null(e.lsb)}"
            return f"{e.pc}{address} {e.name}"
        case CcPairEntry():
            return f"{e.msb}:{e.lsb}{_default(e.default)} {e.name}"
        case NrpnEntry():
            return f"{_blank(e.msb)}:{e.lsb}:{e.depth}{_default(e.default)} {e.name}"
        case DrumEntry():
            return f"{e.row}:{_null(e.trig)}:{_null(e.chan)}:{_null(e.note)} {e.name}"
        case AssignEntry():  # before AutomationEntry, its base class
            return f"{e.pot} {_target(e)}"
        case AutomationEntry():
            return _target(e)
        case CommentLine():
            return e.text
    raise TypeError(f"cannot render {type(e).__name__}")


def render(entry: Entry) -> str:
    """The entry as one canonical line, keeping the original's indentation, trailing comment and line ending."""
    body = entry.raw.split("#", 1)[0].rstrip(" \t\r")
    indent = body[: len(body) - len(body.lstrip(" \t"))]
    return indent + _body(entry) + entry.raw[len(body):]


def eol(lines: list[str]) -> str:
    """The ending for inserted lines: CRLF files keep a "\\r" before each "\\n"."""
    return "\r" if lines[0].endswith("\r") else ""
