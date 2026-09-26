# /// script
# requires-python = ">=3.13"
# dependencies = ["lark"]
# ///
"""Lark spike: run the grammar over every probe and corpus file.

uv run spike/spike.py
"""

import re
import sys
import time
from functools import lru_cache
from pathlib import Path

from lark import Lark, UnexpectedInput

ROOT = Path(__file__).parent.parent
TD = ROOT / "testdata"

START = {
    "CC": "cc_entry",
    "PC": "pc_entry",
    "CC_PAIR": "ccpair_entry",
    "NRPN": "nrpn_entry",
    "DRUMLANES": "drum_entry",
    "ASSIGN": "assign_entry",
    "AUTOMATION": "automation_entry",
}
PARSER = Lark(
    (Path(__file__).parent / "grammar.lark").read_text(),
    parser="lalr",
    start=["directive", *START.values()],
)
HEADER = re.compile(r"\s*\[(/?)([^\]]*)\]\s*$")


@lru_cache(maxsize=4096)
def parse_line(start, text):
    return PARSER.parse(text, start=start)


def scan(text):
    """Yield (line, kind, detail) for every line; kind is 'ok', 'grammar' or 'structure'."""
    section = None
    for n, raw in enumerate(text.splitlines(), 1):
        body = raw.split("#", 1)[0].rstrip()
        if not body.strip():
            continue
        if m := HEADER.match(body):
            close, name = m[1], m[2].upper()
            if close:
                if name != section:
                    yield n, "structure", f"stray [/{name}]"
                section = None
            elif section:
                yield n, "structure", f"[{section}] not closed"
                section = name
            else:
                section = name
            continue
        if section == "COMMENT":
            continue
        if section is not None and section not in START:
            yield n, "structure", f"entry in unknown section [{section}]"
            continue
        start = START[section] if section else "directive"
        try:
            yield n, "ok", (start, parse_line(start, body))
        except UnexpectedInput as e:
            exp = getattr(e, "expected", None) or getattr(e, "allowed", None)
            yield n, "grammar", f"col {e.column}: expected {sorted(exp or [])}"
    if section:
        yield n + 1, "structure", f"[{section}] not closed at EOF"


def first_error(path):
    for n, kind, detail in scan(path.read_text(encoding="utf-8")):
        if kind != "ok":
            return n, kind, detail
    return None


# Hardware outcomes: first rejected line, or None for "loads". From the RESULTS.md files, OS 3.10.
HW = {
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
    "E01_CC_SECTION_DEFAULT": None, "E02_AUTO_LINE_DEFAULT": None,
    "E03_CC_SHORTHAND_DEFAULT": None, "E04_NRPN_BARE_DEFAULT": None,
    "E05_ASSIGN_EXTRA_FIELD": None,
}
HW |= {f"C{i:02}": None for i in range(1, 24)}
HW |= {f"C{i:02}": 5 for i in (4, 7, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22)}


def probes():
    print("== probes (grammar + structure only; ranges, charset, enums are rules)")
    for path in sorted(TD.glob("probes/**/*.txt")):
        key = path.stem if path.stem[0] != "C" else path.stem[:3]
        hw = HW[key]
        got = first_error(path)
        line = got[0] if got else None
        mark = "same" if line == hw else ("RULE" if got is None else "DIFF")
        print(f"  {mark:4} {path.stem:26} hw={hw!s:5} grammar={line!s:5} {got[2] if got else ''}")


def corpus(label, paths):
    print(f"== {label}: {len(paths)} files")
    names = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            print(f"  not UTF-8: {path.relative_to(TD)} {e}")
            continue
        for n, kind, detail in scan(text):
            if kind != "ok":
                print(f"  {path.relative_to(TD)}:{n} {kind}: {detail}")
            elif detail[0] != "directive":
                tree = detail[1]
                name = next((t for t in tree.scan_values(lambda t: t.type == "NAME")), None)
                if name is not None:
                    names.append((path.relative_to(TD), n, str(name)))
    odd = [x for x in names if re.search(r"[:=]|DEFAULT", x[2], re.I)]
    print(f"  {len(names)} names; {len(odd)} containing : = or DEFAULT:")
    for p, n, name in odd:
        print(f"    {p}:{n} {name!r}")


def timing():
    path = TD / "mine/Novation_Peak.txt"
    text = path.read_text()
    parse_line.cache_clear()
    t = time.perf_counter()
    list(scan(text))
    cold = time.perf_counter() - t
    t = time.perf_counter()
    list(scan(text))
    warm = time.perf_counter() - t
    print(f"== timing {path.name} ({len(text.splitlines())} lines): cold {cold*1000:.1f} ms, warm {warm*1000:.2f} ms")


if __name__ == "__main__":
    probes()
    corpus("mine", sorted(TD.glob("mine/*.txt")))
    corpus("community", sorted(p for p in TD.glob("community/**/*.txt") if p.name != "template.txt"))
    timing()
    sys.exit(0)
