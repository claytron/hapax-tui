# tests/test_write.py
from dataclasses import fields
from pathlib import Path

import pytest

from hapax import parse
from hapax.parse import AutomationEntry
from hapax.write import eol, render

TESTDATA = Path(__file__).parent / "testdata"
CORPUS = sorted(TESTDATA.rglob("*.txt"))


def entries(doc):
    return [*doc.directives, *(e for s in doc.sections for e in s.entries)]


def rendered(section, line):
    text = line if section is None else f"[{section}]\n{line}\n[/{section}]"
    (entry,) = entries(parse(text))
    return render(entry)


@pytest.mark.parametrize("section, line, expected", [
    (None, "VERSION 1", "VERSION 1"),
    (None, "version 1", "VERSION 1"),
    (None, "TRACKNAME My Synth", "TRACKNAME My Synth"),
    (None, "OUTCHAN", "OUTCHAN"),
    (None, "VERSION 1 # note", "VERSION 1 # note"),
    ("CC", "74 Cutoff", "74 Cutoff"),
    ("CC", "74:64 Cutoff", "74:DEFAULT=64 Cutoff"),
    ("CC", "74:default=64 Cutoff", "74:DEFAULT=64 Cutoff"),
    ("CC", "  74 Cutoff # filter\r", "  74 Cutoff # filter\r"),
    ("PC", "1 Piano", "1 Piano"),
    ("PC", "1:0:NULL Piano", "1:0:NULL Piano"),
    ("PC", "1:null:null Piano", "1 Piano"),
    ("CC_PAIR", "1:33 Mod", "1:33 Mod"),
    ("CC_PAIR", "1:33:DEFAULT=8000 Mod", "1:33:DEFAULT=8000 Mod"),
    ("NRPN", ":2000:7 BAR", ":2000:7 BAR"),
    ("NRPN", "0:1026:7 FOO", "0:1026:7 FOO"),
    ("NRPN", "1:2:14:100 X", "1:2:14:DEFAULT=100 X"),
    ("DRUMLANES", "1:NULL:10:36 Kick", "1:NULL:10:36 Kick"),
    ("DRUMLANES", "2:1:cv1:NULL Snare", "2:1:CV1:NULL Snare"),
    ("ASSIGN", "1 cc:74 default=64", "1 CC:74 DEFAULT=64"),
    ("ASSIGN", "2 NRPN::2000:7", "2 NRPN::2000:7"),
    ("ASSIGN", "3 PB:ignored", "3 PB"),
    ("ASSIGN", "4 CV:1 DEFAULT=-2.5v", "4 CV:1 DEFAULT=-2.5V"),
    ("ASSIGN", "5 NULL", "5 NULL"),
    ("ASSIGN", "6 CC:74 some text DEFAULT=1", "6 CC:74 some text DEFAULT=1"),
    ("AUTOMATION", "CC:74:100", "CC:74:100"),
    ("AUTOMATION", "CC_PAIR:1:33", "CC_PAIR:1:33"),
    ("AUTOMATION", "AT", "AT"),
    ("COMMENT", "  Any text: here", "  Any text: here"),
])
def test_render(section, line, expected):
    assert rendered(section, line) == expected


def test_a_new_entry_renders_bare():
    entry = AutomationEntry(line=0, raw="", spans={}, type="CC", cc=74, default="64")
    assert render(entry) == "CC:74 DEFAULT=64"


def test_eol_follows_the_first_line():
    assert eol(["VERSION 1\r", ""]) == "\r"
    assert eol(["VERSION 1", ""]) == ""


def model(e):
    return type(e), {f.name: getattr(e, f.name) for f in fields(e) if f.name not in ("line", "raw", "spans")}


@pytest.mark.parametrize("path", CORPUS, ids=lambda p: str(p.relative_to(TESTDATA)))
def test_every_corpus_entry_renders_to_the_same_fields(path):
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        pytest.skip("not UTF-8")
    doc = parse(text)
    assert "\n".join(doc.lines) == text.removeprefix("﻿")
    lines = list(doc.lines)
    for e in entries(doc):
        lines[e.line - 1] = render(e)
    again = parse("\n".join(lines))
    assert [model(e) for e in entries(again)] == [model(e) for e in entries(doc)]
