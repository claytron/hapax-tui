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
