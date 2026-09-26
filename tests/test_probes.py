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
