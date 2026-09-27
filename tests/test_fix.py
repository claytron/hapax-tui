# tests/test_fix.py
from pathlib import Path

import pytest

from hapax import LATEST, Severity, parse, validate
from hapax.fix import fix, transliterate

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


def test_transliterate():
    assert transliterate("Ærø—ﬁ “x” Résumé") == 'AEro-fi "x" Resume'
    assert transliterate("Arrow→") == "Arrow→"


@pytest.mark.parametrize("before, after", [
    ("[CC]\n74 Resonänce\n[/CC]\n", "[CC]\n74 Resonance\n[/CC]\n"),
    ("TRACKNAME Straße\n", "TRACKNAME Strasse\n"),
    ("[CC]\n1 “Drive”\n[/CC]\n", '[CC]\n1 "Drive"\n[/CC]\n'),
    ("[COMMENT]\nCafé notes\n[/COMMENT]\n", "[COMMENT]\nCafe notes\n[/COMMENT]\n"),
    ("[AUTOMATION]\nCC:74:100\n[/AUTOMATION]\n", "[AUTOMATION]\nCC:74 DEFAULT=100\n[/AUTOMATION]\n"),
    ("[AUTOMATION]\nCC:74:100 DEFAULT=5\n[/AUTOMATION]\n", "[AUTOMATION]\nCC:74 DEFAULT=5\n[/AUTOMATION]\n"),
    ("[ASSIGN]\n1 CC:74:100\n[/ASSIGN]\n", "[ASSIGN]\n1 CC:74 DEFAULT=100\n[/ASSIGN]\n"),
])
def test_value_fixes(before, after):
    assert fixed(before) == after


def test_unmappable_characters_stay_and_are_still_reported():
    text = fixed("[CC]\n1 Résumé→\n[/CC]\n")
    assert text == "[CC]\n1 Resume→\n[/CC]\n"
    assert "name.char" in codes(text)


def test_nothing_mappable_means_no_fix():
    text = "[CC]\n1 Arrow→\n[/CC]\n"
    assert fix(text) == (text, [])
V310 = (3, 10)


@pytest.mark.parametrize("before, after", [
    ("[CC]\n74:DEFAULT=64 Cutoff\n[/CC]\n[AUTOMATION]\nCC:74\n[/AUTOMATION]\n",
     "[CC]\n74 Cutoff\n[/CC]\n[AUTOMATION]\nCC:74 DEFAULT=64\n[/AUTOMATION]\n"),
    ("[CC]\n74:64 Cutoff\n[/CC]\n[AUTOMATION]\nCC:74 DEFAULT=64\n[/AUTOMATION]\n",
     "[CC]\n74 Cutoff\n[/CC]\n[AUTOMATION]\nCC:74 DEFAULT=64\n[/AUTOMATION]\n"),
    ("[CC]\n74:64 Cutoff\n[/CC]\n[AUTOMATION]\n  PB\n[/AUTOMATION]\n",
     "[CC]\n74 Cutoff\n[/CC]\n[AUTOMATION]\n  PB\n  CC:74 DEFAULT=64\n[/AUTOMATION]\n"),
    ("[CC]\n74:64 Cutoff\n75:1 Reso\n[/CC]\n",
     "[CC]\n74 Cutoff\n75 Reso\n[/CC]\n[AUTOMATION]\nCC:74 DEFAULT=64\nCC:75 DEFAULT=1\n[/AUTOMATION]\n"),
    ("[NRPN]\n0:1026:7:5 FOO\n[/NRPN]\n[AUTOMATION]\nNRPN:8:2:7\n[/AUTOMATION]\n",
     "[NRPN]\n0:1026:7 FOO\n[/NRPN]\n[AUTOMATION]\nNRPN:8:2:7 DEFAULT=5\n[/AUTOMATION]\n"),
    ("[CC_PAIR]\n1:33:DEFAULT=8000 Mod\n[/CC_PAIR]\n",
     "[CC_PAIR]\n1:33 Mod\n[/CC_PAIR]\n[AUTOMATION]\nCC_PAIR:1:33 DEFAULT=8000\n[/AUTOMATION]\n"),
    # Review focus 4: a name fix and a move on the same line both land.
    ("[CC]\n74:64 Résonance\n[/CC]\n",
     "[CC]\n74 Resonance\n[/CC]\n[AUTOMATION]\nCC:74 DEFAULT=64\n[/AUTOMATION]\n"),
    ("VERSION 1\r\n[CC]\r\n74:64 C\r\n[/CC]\r\n",
     "VERSION 1\r\n[CC]\r\n74 C\r\n[/CC]\r\n[AUTOMATION]\r\nCC:74 DEFAULT=64\r\n[/AUTOMATION]\r\n"),
])
def test_section_defaults_move_to_automation_on_3_10(before, after):
    assert fixed(before, V310) == after


FULL = "[CC]\n100:64 C\n[/CC]\n[AUTOMATION]\n" + "".join(f"CC:{i}\n" for i in range(64)) + "[/AUTOMATION]\n"


@pytest.mark.parametrize("text, fw", [
    ("[CC]\n74:64 C\n[/CC]\n[AUTOMATION]\nCC:74 DEFAULT=1\n[/AUTOMATION]\n", V310),  # conflicting default
    ("[CC]\n120:64 C\n[/CC]\n", V310),  # CC 120-127 cannot be automated
    (FULL, V310),  # no room for a 65th lane
    ("[CC]\n74:64 C\n[/CC]\n", LATEST),  # honoured on 3.20+: nothing to fix
    ("[CC_PAIR]\n1:33:DEFAULT=8000 M\n[/CC_PAIR]\n", (1, 13)),  # a different cause
])
def test_section_defaults_left_for_a_hand_fix(text, fw):
    assert fix(text, fw) == (text, [])
