# tests/test_fix.py
from pathlib import Path

import pytest

from hapax import LATEST, Severity, parse, validate
from hapax.fix import fix

TESTDATA = Path(__file__).parent / "testdata"
CORPUS = sorted(TESTDATA.rglob("*.txt"))


def fixed(text, fw=LATEST):
    return fix(text, fw)[0]


def applied(text, fw=LATEST):
    return [(a.code, a.line) for a in fix(text, fw)[1]]


def codes(text, fw=LATEST):
    return {f.code for f in validate(parse(text), fw)}


@pytest.mark.parametrize("before, after", [
    ("﻿VERSION 1\n", "VERSION 1\n"),
    ("VERSION 2\n", "VERSION 1\n"),
    ("VERSION 2 # why not\n", "VERSION 1 # why not\n"),
    ("[CC]\n1 a\n\n[PC]\n1 b\n[/PC]\n", "[CC]\n1 a\n[/CC]\n\n[PC]\n1 b\n[/PC]\n"),
    ("[CC]\n1 a\n", "[CC]\n1 a\n[/CC]\n"),
    ("[CC]\n1 a\n\n\n", "[CC]\n1 a\n[/CC]\n\n\n"),
    ("[CC]\n1 a", "[CC]\n1 a\n[/CC]"),  # no trailing newline stays that way
    ("  [CC]\n  1 a\n", "  [CC]\n  1 a\n  [/CC]\n"),
    ("[CC]\n[/CC]\n[/CC]\n", "[CC]\n[/CC]\n"),
    ("[/PC] # old\n", "# old\n"),
    ("VERSION 2\r\n[CC]\r\n1 a\r\n", "VERSION 1\r\n[CC]\r\n1 a\r\n[/CC]\r\n"),
])
def test_structural_fixes(before, after):
    assert fixed(before) == after


def test_nothing_to_fix_returns_the_text_unchanged():
    text = "VERSION 1\n[CC]\n74 Cutoff\n[/CC]\n"
    assert fix(text) == (text, [])


def test_applied_reports_code_and_line():
    assert applied("﻿VERSION 2\n[CC]\n1 a\n") == [
        ("file.bom", 1), ("version", 1), ("section.unclosed_eof", 2)]


def test_a_fix_one_pass_enables_runs_in_the_next():
    # Closing [CC] before [PC] makes the old [/CC] after it a stray close.
    # Pass 1 closes [CC] and deletes the stray [/CC]; pass 2 closes [PC], whose anchor line pass 1 had claimed.
    assert fixed("[CC]\n1 a\n[PC]\n1 b\n[/CC]\n") == "[CC]\n1 a\n[/CC]\n[PC]\n1 b\n[/PC]\n"


def _corpus_text(path):
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        pytest.skip("not UTF-8")


@pytest.mark.parametrize("fw", [(3, 10), LATEST], ids=["3.10", "latest"])
@pytest.mark.parametrize("path", CORPUS, ids=lambda p: str(p.relative_to(TESTDATA)))
def test_fixing_the_corpus_is_idempotent_and_adds_no_errors(path, fw):
    text = _corpus_text(path)
    once, _ = fix(text, fw)
    assert fix(once, fw) == (once, [])
    errors = lambda t: {f.code for f in validate(parse(t), fw) if f.severity is Severity.ERROR}
    assert errors(once) <= errors(text)
