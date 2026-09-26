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
