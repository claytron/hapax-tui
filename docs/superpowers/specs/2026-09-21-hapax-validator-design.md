# Hapax Instrument Definition Validator — Design

- Date: 2026-09-21
- Revised: 2026-09-25 — Python and Textual replace Go and bubbletea; rules rebuilt on hardware probes, firmware binaries and the firmware changelog; firmware selection added; Lark parsing and a core shaped for real-time use by the TUI
- Status: draft, under review

## Context

Squarp Hapax instrument definitions are UTF-8 `.txt` files stored in the `HAPAX/` folder of the SD card, alongside projects.
They name CCs and PCs, configure drum lanes, set input and output MIDI port and channel, and pre-create automation lanes and pot assignments.

The Hapax already validates these files, but badly for authoring: it rejects the whole file at the **first** bad line with `SYNTAX ERROR line N`, and you only find out after copying the file to the card and loading it.
Worse, some mistakes load without complaint and silently do nothing.
This tool reports every problem at once, before the file leaves the computer, for the firmware the file is meant for.

This is the first stage of a larger tool that will grow a [Textual](https://github.com/Textualize/textual) TUI for browsing and editing definitions.
That stage is not part of this design.

## Scope

```text
hapax validate [--strict] [--fw VERSION] [paths...]
```

Each path is a file or a directory; a directory expands to the `*.txt` files directly inside it.
With no paths it validates the current directory.
Dotfiles are always skipped: macOS writes a binary `._Name.txt` next to every file it copies to the SD card.

`--fw` selects the target firmware: any published release from `1.12` to `3.21`; the default is the latest, `3.21`.
Older or unknown versions are refused with exit code 2.
The summary line always names the firmware checked against, so the default is never invisible.

### Non-goals for v1

- No TUI.
- No editing or writing of files.
- No firmware older than 1.12, whose parser was "less strict" in undocumented ways.
- No fetching definitions from the community forum or third-party repositories.

## Sources of truth

In order of authority:

1. **Hardware probes** — `testdata/probes/`, run on a Hapax with OS 3.10.
   Each probe file tests one variant; the recorded outcome is either "loads" or `SYNTAX ERROR line N`.
   Results are in `testdata/probes/RESULTS.md` and `testdata/probes/r2/RESULTS.md`.
2. **The firmware changelog**, `https://squarp.net/hapax/firmware/`, for behaviour that changed between versions.
3. **The firmware binaries** from the same page.
   `strings hapax.bin` exposes the parser's keyword table; diffing it across all 26 releases dates each keyword.
   The author's SD-card copy of 3.10 is byte-identical to the published one.
4. **Squarp's online template**, `https://squarp.net/hapax/instr_def/template.txt`, which tracks the latest firmware.
   Where it states a range and nothing above contradicts it, the range is treated as enforced — every range that was probed was enforced.
5. **The manual** (3.10, §6.6), which defers syntax to the template.

The template embedded in older definition files, including the author's own, predates several features below.
It is not a source.

## Firmware history

Definition-relevant changes, from the keyword diff and the changelog:

| Version | Change |
|---|---|
| 1.10 | Instrument definitions introduced |
| 1.12 | `MAXRATE`; `[CC_PAIR]`; NRPN LSB above 127 when MSB is 0 or omitted; "syntax compliance is now more strict" |
| 1.13 | `CC_PAIR:` as an ASSIGN and AUTOMATION type |
| 1.14 | Tabs no longer break loading; `[CC_PAIR]` defaults loaded |
| 3.00 | `USBDx`/`USBHx` virtual ports (1–16); `.txt.bak` files ignored; `DEFAULT=` in `[CC]`, `[NRPN]`, `[CC_PAIR]` stops being applied **and range-checked** (2.21 applies it, probe E01, and rejects `DEFAULT=128`, probe A07). The changelog's "additional special characters" did not touch definition names: 2.21 accepts exactly the 3.10 set |
| 3.10 | Drum rows 9–16 |
| 3.20 | `TYPE POLYAT` and `AFTR`; `DEFAULT=` in `[CC]`, `[NRPN]`, `[CC_PAIR]` honoured (silently ignored in 3.00 and 3.10); MPE type with a DIN `INPORT` checked |
| 3.21 | No definition changes |

Firmware-dependent rules across the supported range, 1.12–3.21:

| Rule | Condition |
|---|---|
| Tab anywhere in the file is an error | before 1.14 |
| `CC_PAIR:` in ASSIGN or AUTOMATION is an error | before 1.13 |
| `[CC_PAIR]` `DEFAULT=` is ignored (warning) | before 1.14 |
| `USBDx`/`USBHx` are errors | before 3.00 |
| Section defaults are ignored and unchecked (warning; no range error) | 3.00–3.10 |
| Drum rows 9–16 are errors | before 3.10 |
| `TYPE POLYAT`/`AFTR` are errors | before 3.20 |

Everything else in this spec was probed on 3.10 and 2.21 with identical results, and is assumed unchanged from 1.12 to 3.21, since the changelog records no other definition changes in that range.

## How the Hapax parses

Observed on 3.10 and 2.21 hardware.

- The first error rejects the whole file.
  Nothing is partially loaded.
- Line numbers are 1-based physical lines, comments and blank lines included.
- `#` starts a comment anywhere on a line; text after it is ignored.
- Whitespace is spaces or tabs (tabs from 1.14).
  CRLF line endings load.
- Keywords are case-insensitive: `trackname`, `TYPE poly`, `[cc]`, `Default=` all load.
- Every directive and every section is optional, including `VERSION`.
  A file of only `VERSION 1` and `TRACKNAME x` loads.
- Numbers may have leading zeros: `026` loads.
- An unknown section header is accepted, but its first entry is a syntax error.
- An unclosed section is reported at the next section header.

## Names

TRACKNAME and every entry name use one character set.
The documented set (alphanumerics, space, `_ - +`) is too strict.
The set below is identical on 2.21 and 3.10.

| Accepted | Rejected |
|---|---|
| `A–Z a–z 0–9`, space, `_ - + ! " $ ' ( ) * , . / : < = > ? @` | ``% & ; [ \ ] ^ ` { \| } ~``, any non-ASCII |

Probed on CC names and TRACKNAME; applied to PC, NRPN, CC_PAIR and drum lane names on the assumption that one routine handles all names.
A name is required wherever the syntax shows one: a `[CC]` entry with no name is rejected.

## Rules

Severity follows one principle: **an error is something the target firmware rejects; a warning is something it accepts that is probably not what the author meant.**
Nothing the target firmware accepts is reported as an error.

Rules that depend on the firmware are marked **(fw)**.

### Directives

| Directive | Valid | Error | Warning |
|---|---|---|---|
| `VERSION` | any | — | not `1` |
| `TRACKNAME` | name charset, `NULL` | bad character | — |
| `TYPE` | `POLY DRUM MPE NULL`; `POLYAT AFTR` from 3.20 **(fw)** | anything else | — |
| `OUTPORT` | `A B C D USBD USBH NULL`, `USBDx USBHx` (1–16) from 3.00 **(fw)**, `CVGx CVx Gx` (1–4) | anything else | — |
| `OUTCHAN` | 1–16, `NULL` | anything else | — |
| `INPORT` | `NONE ALLACTIVE A B USBD USBH CVG NULL`, `USBDx USBHx` (1–16) from 3.00 **(fw)** | anything else | `A` or `B` when `TYPE` is `MPE` — MPE cannot use a DIN port |
| `INCHAN` | 1–16, `ALL`, `NULL` | anything else | — |
| `MAXRATE` | `NULL 192 96 64 48 32 24 16 12 8 6 4 3 2 1` | anything else | — |
| unknown key | — | always | — |
| any key twice | — | — | always, naming the earlier line |

### Sections

**`[DRUMLANES]`** — `ROW:TRIG:CHAN:NOTE NAME`.
`ROW` 1–16 from 3.10, 1–8 before **(fw)**; `TRIG` 0–127 or `NULL`; `CHAN` 1–16, `Gx`/`CVx`/`CVGx` (1–4) or `NULL`; `NOTE` 0–127 or `NULL`; `NAME` or `NULL`.
Warnings: a row declared twice; any entry when `TYPE` is explicitly `POLY`, `MPE`, `POLYAT` or `AFTR` (the hardware discards the section; `TYPE NULL` keeps the track's current type, which may be DRUM, so it does not warn).

**`[PC]`** — `PC NAME` or `PC:MSB:LSB NAME`.
`PC` 1–128; `MSB` and `LSB` 0–127 or `NULL`.
Warnings: the same `PC:MSB:LSB` twice (a bare `PC` is `PC:NULL:NULL`); more than 128 entries — the template states a limit of 128 but 3.10 loads 129.

**`[CC]`** — `CC NAME` or `CC:DEFAULT=v NAME`.
`CC` 0–127; `DEFAULT` 0–127, `DEFAULT=NULL` is rejected; out of range is an error except on 3.00–3.10, which neither check nor apply section defaults **(fw)**.
`CC:v NAME` is an undocumented shorthand for `CC:DEFAULT=v NAME` — it sets the lane default on 2.21 (probe E03) — and is treated identically.
Warnings: the same CC twice; `CC` above 119 (nameable but not usable in ASSIGN or AUTOMATION, where 120 is rejected); any default, `DEFAULT=v` or shorthand, on 3.00–3.10 **(fw)** — ignored on load; the message says to set it on the `[AUTOMATION]` line instead.

**`[CC_PAIR]`** — `MSB_CC:LSB_CC NAME` or `MSB_CC:LSB_CC:DEFAULT=v NAME`; 14-bit CC.
Each CC 0–127, `DEFAULT` 0–16383.
Ranges are from the template and unprobed.
Warnings: the same pair twice; any `DEFAULT=` before 1.14 or on 3.00–3.10 **(fw)**.

**`[NRPN]`** — `MSB:LSB:DEPTH NAME` or `MSB:LSB:DEPTH:DEFAULT=v NAME`.
`MSB` 0–127 or empty; `LSB` 0–127, or 0–16383 when `MSB` is `0` or empty (`1:200:7` is rejected); `DEPTH` 7 or 14; `DEFAULT` 0–127 for 7-bit, 0–16383 for 14-bit.
`MSB:LSB:DEPTH:v` is an undocumented shorthand for `MSB:LSB:DEPTH:DEFAULT=v` (probe E04 on 2.21) and is treated identically.
Warnings: the same `MSB:LSB` twice; any default on 3.00–3.10 **(fw)**.

**`[ASSIGN]`** — `POT TYPE:VALUE [DEFAULT=v]`.
`POT` 1–8.
`TYPE`/`VALUE`: `CC:0–119`, `PB`, `AT`, `CV:1–4`, `NRPN:MSB:LSB:DEPTH`, `CC_PAIR:MSB:LSB`, `NULL`.
`CC_PAIR:` is undocumented in the template; it is in the keyword table from 1.13 **(fw)** and loads.
`DEFAULT`: CC 0–127, PB 0–16383, NRPN by depth, CV 0–65535 or a voltage from `-5V` to `5V`; ignored for PB and AT.
Warnings: the same pot twice; an extra `:v` after a CC value (`CC:74:100`) — it loads but is silently dropped, the pot default stays 0 (probe E05), so the message says to write `DEFAULT=100`; text between the value and `DEFAULT=` — loads, with unverified effect.

**`[AUTOMATION]`** — `TYPE:VALUE [DEFAULT=v]`, types and values as `[ASSIGN]` without `NULL`.
At most 64 entries; the 65th is rejected.
`DEFAULT=` here is undocumented in the template but honoured on every firmware probed (2.21, and per the changelog 3.00–3.21) — it is the only default 3.00 and 3.10 apply — so it is valid and not reported.

**`[COMMENT]`** — free text shown on the Hapax.
Structure only; contents not validated.

**Unknown section** — an error on its first entry, as the hardware reports it; a warning if it is empty.

**Structure** — an unclosed section is an error; so is a closing tag with no matching open.

## Architecture

The validator is a library first.
The CLI is one thin front end; the TUI will be another, calling the same functions on every edit to validate input as it is typed.
That use shapes the core: pure functions, cheap re-validation, and findings precise enough to underline a single field.

```text
                 ┌──────────── hapax (library, no I/O) ─────────────┐
 text ──► parse ─┤ Document ──► validate(doc, fw) ──► list[Finding] │
                 └───────────────────────────────────────────────────┘
                        ▲                                   │
     CLI: read files ───┘                                   └──► print, exit code
     TUI: on every edit ─┘                                  └──► underline, gutter, form errors
```

### Public API

```python
def parse(text: str) -> Document: ...
def validate(doc: Document, fw: tuple[int, int] = LATEST) -> list[Finding]: ...
```

`parse` never raises: anything that fails to parse becomes a finding carried on the `Document`.
`validate` is pure — no printing, no exit codes, no file access — and returns parse findings and rule findings together, sorted by line.
The CLI and the TUI own all I/O and presentation.

### Parsing — two passes, Lark per line

`hapax/parse.py` and `hapax/grammar.lark`.

The **structure pass** walks the lines once, classifying each as blank, comment, directive, section header, section close or entry, and tracking the enclosing section.
It reports structural problems: an unclosed section, a stray closing tag, an unknown section.

The **entry pass** parses each directive and entry on its own with [Lark](https://github.com/lark-parser/lark) in LALR mode, using the start rule for its kind — `cc_entry`, `nrpn_entry`, `drum_entry`, `assign_entry`, and so on, all in one grammar file.
Parsing line by line is what lets a grammar report every error in a file rather than stopping at the first, as the Hapax does.
The grammar file is also the most readable statement of the format: it replaces the per-entry regexes of an earlier draft and much of this spec's prose about shapes.

Each line is parsed as it appears on disk minus its comment, leading whitespace kept, so Lark's column numbers are the columns on screen.
Keyword case-insensitivity, leading zeros, `NULL`, the empty NRPN MSB and the shorthand defaults are all expressed in the grammar.

Line parses are memoised with `functools.lru_cache` keyed on `(kind, text)`.
The TUI re-parses the whole document on each edit and only the edited line misses the cache, so there is no incremental parser to maintain.

A Lark `Transformer` turns each parse tree into a dataclass.

### Model

```python
@dataclass(frozen=True)
class Span:
    start: int  # column in the raw line
    end: int

@dataclass(frozen=True)
class Entry:  # base; one subclass per kind: CcEntry, NrpnEntry, DrumEntry, ...
    line: int
    raw: str                    # the line exactly as on disk
    spans: dict[str, Span]      # field name -> columns, e.g. spans["lsb"]

@dataclass(frozen=True)
class NrpnEntry(Entry):
    msb: int | None
    lsb: int
    depth: int
    default: int | None
    name: str

@dataclass
class Section:
    name: str                   # upper-cased
    start: int
    end: int | None             # None if never closed
    entries: list[Entry]

@dataclass
class Document:
    lines: list[str]            # raw, verbatim
    directives: list[Directive]
    sections: list[Section]
    parse_findings: list[Finding]
```

Nothing is discarded, which gives findings their line numbers and lets the future editor write files back without disturbing comments or layout.

### Rules

`hapax/rules.py`, in two kinds:

- **Entry rules** see one parsed entry and the firmware: ranges, enumerations, the firmware-dependent rules, name characters.
  They are independent of each other and of the rest of the file.
- **Document rules** see the whole `Document`: duplicates, the 64-lane cap, drum lanes on a non-DRUM track, `TYPE MPE` with a DIN input, more than 128 PCs.

`validate` runs both.
The split is what makes a finer cache possible later — entry-rule results keyed like line parses — but it is not added until a measurement asks for it.

Ranges and enumerations are module-level constants, each with a comment citing its source: a probe ID, a firmware version, or the template.
Firmware is a `tuple[int, int]`; each firmware-dependent rule is a plain comparison such as `fw >= (3, 20)` beside a comment naming the changelog entry.
There is no per-version ruleset and no version registry.

### Findings

```python
@dataclass(frozen=True)
class Finding:
    severity: Severity           # StrEnum: ERROR | WARNING
    code: str                    # stable id: "cc.range", "defaults.ignored", ...
    message: str
    line: int                    # 1-based; 0 = whole file
    span: Span | None            # columns to underline
    field: str | None            # model field, e.g. "lsb", for form-based editing
```

`span` lets the TUI underline exactly `2000` in `:2000:7 BAR`; `field` lets a form-based editor put the error beside the LSB input.
`code` is stable across message rewording: tests assert on it, and a future option to silence a warning would key on it.

Parse errors carry Lark's expected tokens, rendered with friendly terminal names — `expected DEFAULT= or a number` rather than `Unexpected token`.
LALR also keeps Lark's interactive parser available, which can list the tokens acceptable at a cursor position: the basis for completion in the TUI, not built now.

### What stays out of the library

When to show a finding is a front-end decision: the TUI may hold back errors on the line under the cursor until it is left.
The library has no "in-progress input" mode; it reports accurately and the caller chooses.

Writing entries back to text belongs to the editor's design.
The lossless model already fixes its rule: a line is regenerated only when it is edited; every other line keeps its raw text.

### CLI

`hapax/cli.py`, standard library `argparse`: reads files, calls `parse` and `validate`, prints, sets the exit code.
The `validate` subcommand exists from the start so a bare `hapax` can become the TUI later.

```text
$ hapax validate --fw 3.10 ~/Music/hapax\ inst/

DD-500.txt         OK
Matriarch.txt      34 warnings
  W line 49: DEFAULT ignored on 3.10 (honoured from 3.20); set it on the [AUTOMATION] line instead
  ...
TR-8S.txt          OK

14 files, 0 errors, 304 warnings — Hapax OS 3.10
```

Plain text, no colour — Rich arrives with Textual at the TUI stage.

- A file that is not valid UTF-8 produces an error finding at line 0; other files are still checked.
- A path that does not exist, no `.txt` files found at all, or an unsupported `--fw`, exits 2 with a message.
- Exit codes: 0 clean, 1 findings that count, 2 usage or I/O failure.
- `--strict` makes warnings count toward the exit code.

## Layout

```text
pyproject.toml              uv; [project.scripts] hapax = "hapax.cli:main"
.python-version             3.13
uv.lock
hapax/
  __init__.py      re-exports parse, validate, Finding, LATEST
  grammar.lark     entry and directive grammars, one start rule each
  parse.py         model dataclasses, structure pass, cached per-line Lark parsing
  rules.py         entry rules, document rules, validate()
  cli.py
tests/
  test_parse.py
  test_probes.py
  test_rules.py
  test_corpus.py
testdata/
  probes/                   hardware probes and their recorded results (OS 3.10)
  mine/                     the author's 14 definitions
  community/                endlesscoil/hapax-instruments, CC0, pinned commit fd4d9df
  template-online.txt       squarp.net template, reference only
```

Flat package, matching the sibling projects in `claytron/`.
One runtime dependency, `lark`, pure Python; `pytest` is the only development dependency.
Textual is added at the TUI stage.
Firmware binaries are not committed; the keyword diff is recorded in this spec and can be rerun from the published downloads.

## Testing

Test-driven, `pytest.mark.parametrize` throughout.

**The first task is a Lark spike.**
Write the grammar and run it over the author's 14 files, the 155 community files and every probe file, checking two things: names with spaces and punctuation split cleanly from the fields before them, and the grammar accepts and rejects exactly what the hardware did.
If it does not hold up, fall back to a hand-written line parser behind the same `parse()`.

**Probes are the primary suite, run with `fw=(3, 10)`.**
For every probe file, the validator's first error line must equal the hardware's recorded outcome: the reported line, or no error for "loads".
This pins the validator to the hardware rather than to anyone's reading of the template.
The expected outcomes live in `test_probes.py` as a dict, transcribed from the `RESULTS.md` files.
Round 3 also ran on 2.21; those outcomes are asserted with `fw=(2, 21)`.
Probes the hardware accepted but that should warn assert the warning as well.

**Firmware tests:** each firmware-dependent rule is asserted on both sides of its threshold — tab on 1.13 and 1.14, `CC_PAIR:` on 1.12 and 1.13, `USBD1` on 2.21 and 3.00, a `[CC]` default on 2.21, 3.10 and 3.20, drum row 9 on 3.00 and 3.10, `TYPE POLYAT` on 3.10 and 3.20 — plus the default being 3.21.

**Rule tests** cover what probes don't: range boundaries for unprobed sections (`CC_PAIR`, CV voltages, drum channels).
They assert `code`, `line` and `span`, not message text.

**Parse tests** cover the grammar directly: every entry shape, including shorthand defaults, empty MSB, `NULL`, leading zeros, case, tabs, and names containing spaces and punctuation; spans for each field; expected-token lists on failure.

**Performance guard:** parsing and validating `Novation_Peak.txt` (364 lines) must stay under 50 ms, cold cache — a generous bound that still catches a regression that would make the TUI lag while typing.

**Corpus tests:** the author's 14 files must produce no errors on 3.10; the 155 community files must parse without raising, and a handful of known mistakes in them are asserted by line — `OUTAN` in `uptown/flash.txt`, `105:LPF VEL` in `toraiz/as-1.txt`, `DEFAULT=NULL` in `pandamidi/future_impact.txt`.

The community repository is CC0, so vendoring it is permitted.
Forum posts are not vendored.

## Decisions worth recording

**A library shaped for the TUI, before the TUI exists.**
Real-time validation in the editor is a known next stage, and retrofitting spans, stable codes and a pure API later would touch every rule.
They cost little now; incremental parsing, completion and result caching are not built until needed.

**Lark over regexes, pydantic, and hand-written parsing.**
The entry shapes — optional fields, shorthands, `NULL`, empty MSB, names with spaces — made a stack of regexes hard to read.
A grammar file states the format once, tracks columns for free, and its expected-token errors improve messages in both front ends.
Pydantic was considered for validation and rejected: it has no warnings, reports field paths rather than file lines, and most rules here depend on firmware or on other fields, which would all become custom validators anyway.
If Lark fails the first spike (see Testing), a hand-written line parser can sit behind the same `parse()` without changing anything else.


**The hardware decides severity.**
The template's prose was wrong in both directions: it documents a character set narrower than what loads, a PC limit that isn't enforced, and — for the author's 3.10 — a `TYPE POLYAT` that is rejected.
Probing replaced guessing.

**Firmware selection, defaulting to the latest.**
The original design deferred versioning as speculative.
The changelog made it concrete: seven rules differ between 1.12 and 3.21, and one of them silently discards every section default the author has written on 3.10.
The default is the latest release, so files written for sharing are checked against what most people run; `--fw 3.10` checks against the author's own hardware.
3.20 projects do not open on 3.10, so owners may reasonably stay on 3.10 for some time.
The floor is 1.12: probing 2.21 showed the same name character set as 3.10, and the changelog dates every other difference back to 1.12.
Before 1.12 the parser was "less strict" in ways nobody documented.

**Python and Textual rather than Go and bubbletea.**
Consistency with the surrounding projects.
The architecture did not depend on the language.

**PC is 1–128 in the file, 0–127 on the wire.**
The manual (§5.7) describes PC values as 0–127; the file format is one-indexed, and PC 0 is rejected.
A comment in `rules.py` records this so it is not "fixed" later.

**Undocumented syntax is judged by what it does, not whether it loads.**
The `[CC]` and `[NRPN]` shorthand defaults load and set the default (E03, E04), so they are valid.
The ASSIGN `CC:74:100` form loads and drops the default (E05), so it warns.
A silently dropped default is exactly the bug this tool exists to catch — as 3.10's own section defaults demonstrate.

## Open questions

- Name length limit: unprobed; long names may be truncated or rejected.
  The 1.15 changelog mentions long file names preventing loading, so file-name length may matter too.
- `[COMMENT]` character set: unprobed; the validator does not check it.
- Behaviour on 3.20 and 3.21, and on 1.12–2.20, is inferred from the changelog, not probed.

## Later

A Textual TUI over the same `parse` and `validate`: browse definitions with validation status, view detail, then edit in place with findings shown as you type, writing back through the lossless model.
Rich for colour and Lark's interactive parser for completion arrive with it.
Each stage gets its own design.
