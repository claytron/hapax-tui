# Hapax Instrument Definition Validator — Design

Date: 2026-09-21
Status: approved, ready for implementation planning

## Context

Squarp Hapax instrument definitions are UTF-8 `.txt` files stored in the `HAPAX/` folder of the SD card, alongside projects.
They name CCs and PCs, configure drum lanes, set input and output MIDI port and channel, and pre-create automation lanes.

Editing them by hand is error-prone and the hardware gives poor feedback when a file is malformed.
Existing third-party checkers are web-based and mostly out of date.

This is the first stage of a larger tool that will eventually grow a bubbletea TUI for browsing and editing definitions.
That stage is explicitly not part of this design.

## Scope

A single command that validates definition files and reports problems with line numbers.

```
hapax validate [-strict] [files...]
```

With no file arguments it validates `*.txt` in the current directory.
It does not try to locate the SD card, whose mount point varies; pass a path instead.

### Non-goals for v1

- No TUI.
- No editing or writing of files.
- No firmware version selection. One ruleset, targeting Hapax OS 3.10.
- No fetching definitions from the community forum or third-party repositories.

## Authoritative source for the format

The Hapax manual (§6.6) documents what definitions do but defers syntax to the example files: "The syntax is quite simple, and self-documented in the examples below."

The official example template therefore **is** the specification.
Every section carries its grammar, ranges, and allowed values as `#` comments.
Those comments are transcribed into `rules.go`, and the template is kept in `testdata/` as the reference copy.

Three facts come from the manual rather than the template:

- Automation lanes are capped at 64 per track (§4.1).
- Automation and assign destinations run `CC0` through `CC119` (§7.9), corroborating the template's ASSIGN documentation.
- Files are UTF-8 with a `.txt` extension (§6.6).

## Format summary

Three constructs: `KEY VALUE` directives, `[SECTION] … [/SECTION]` blocks, and `#` comments.
A `#` comment may be a whole line or trail a value.
Blank lines are permitted anywhere.
Almost every command is optional, and most values accept `NULL` to leave the track's current state untouched.

### Directives

| Directive | Valid values |
|---|---|
| `VERSION` | `1` |
| `TRACKNAME` | alphanumeric ASCII plus space, `_`, `-`, `+`; or `NULL` |
| `TYPE` | `POLY`, `DRUM`, `MPE`, `NULL` |
| `OUTPORT` | `A`, `B`, `C`, `D`, `USBD`, `USBH`, `CVGx`, `CVx`, `Gx` (x in 1–4), `NULL` |
| `OUTCHAN` | 1–16, `NULL`; ignored unless the output port is MIDI |
| `INPORT` | `NONE`, `ALLACTIVE`, `A`, `B`, `USBH`, `USBD`, `CVG`, `NULL` |
| `INCHAN` | 1–16, `ALL`, `NULL`; ignored when `INPORT` is `NONE`, `ALLACTIVE`, or `CVG` |

### Sections

`[DRUMLANES]` — `ROW:TRIG:CHAN:NOTENUMBER NAME`, at most 8 entries.
`ROW` 1–8, `TRIG` 0–127 or `NULL`, `CHAN` 1–16 or `Gx`/`CVx`/`CVGx` (x in 1–4) or `NULL`, `NOTENUMBER` 0–127 or `NULL`, `NAME` in the TRACKNAME charset or `NULL`.
Discarded by the hardware on non-DRUM tracks.

`[PC]` — `NUMBER NAME`, where `NUMBER` is either a single number or `PC:MSB:LSB`.
`PC` 1–128, `MSB` and `LSB` 0–127 or `NULL`.

`[CC]` — `CC_NUMBER NAME` or `CC_NUMBER:DEFAULT=xx NAME`.
`DEFAULT` 0–127.

`[NRPN]` — `MSB:LSB:DEPTH NAME`, optionally `MSB:LSB:DEPTH:DEFAULT=xx NAME`.
`MSB` and `LSB` 0–127, `DEPTH` 7 or 14.
`DEFAULT` 0–127 for 7-bit, 0–16383 for 14-bit.

`[ASSIGN]` — `POT_NUMBER TYPE:VALUE`, optionally followed by `DEFAULT=xx`.
`POT_NUMBER` 1–8; pots not named are `NULL`.
`TYPE` is `CC` (value 0–119), `PB`, `AT`, `CV` (value 1–4), `NRPN` (value `MSB:LSB:DEPTH`), or `NULL`.
Text after `PB` and `AT` is ignored.
Defaults: `CC` 0–127, `PB` 0–16383, `NRPN` 0–127 or 0–16383 by depth, `CV` either 0–65535 or a voltage from `-5V` to `5V`.
Defaults are ignored for `PB` and `AT`.

`[AUTOMATION]` — `TYPE:VALUE` using the same type and value rules as `[ASSIGN]`, at most 64 entries.

`[COMMENT]` — free text, displayed on the Hapax. Not parsed.

## Architecture

### Parser — line-oriented and lossless

```go
type File struct {
    Lines      []string    // raw, verbatim
    Directives []Directive // Key, Value, Line
    Sections   []Section   // Name, Entries, Start, End
}
```

Every entry retains its raw text and line number.
Nothing is discarded.
This is what gives findings their line numbers, and it is what the editor will later need to write files back without disturbing comments or layout.
It is not extra work now — a line-oriented parser is simpler than one building a lossy tree.

The parser reports only structural problems: an unterminated section, a stray `[/SECTION]`, an unknown section name, a malformed directive line.
Everything else is the rules layer's job.

### Rules

`rules.go` holds the ranges and enumerations as plain Go values, transcribed from the template.
One function per section and per directive, each appending findings.
No configuration, no data files, no version selection — a second firmware becomes a second ruleset if and when one is actually needed.

### Findings

A finding carries severity, line number, and message.
Errors are hard violations of the documented format.

Warnings are legal-but-probably-wrong, a fixed set of five:

1. A CC or PC number declared more than once, naming the earlier line.
2. A drum lane row declared more than once.
3. A non-empty `[DRUMLANES]` on a track whose `TYPE` is not `DRUM`, since the hardware discards it.
4. A `TRACKNAME` containing characters outside the documented charset.
5. A `[CC]` number above 119, which can be named but cannot be automated or assigned.

`-strict` makes warnings affect the exit code.

### Output

```
$ hapax validate ~/Music/hapax\ inst/*.txt

Matriarch.txt      OK
Novation_Peak.txt  1 error, 2 warnings
  E line 88: CC 128 out of range (0-127)
  W line 41: CC 74 declared twice (also line 36)
TR-8S.txt          OK

14 files, 1 error, 2 warnings
```

Exit codes: 0 clean, 1 findings that count, 2 usage or I/O failure.

## Layout

```
go.mod                      module github.com/claytron/hapax
main.go                     flags, dispatch, output formatting
internal/def/parse.go
internal/def/rules.go
internal/def/def_test.go
testdata/                   real definitions, the official template, crafted broken files
```

Standard library `flag`; no CLI framework for one subcommand.
The `validate` subcommand exists from the start so that a bare `hapax` can become the TUI later without restructuring.
`internal/def` is importable by that TUI unchanged.

## Testing

Test-driven, table-driven.

The 14 existing definitions in `~/Music/hapax inst/` are the must-pass corpus.
They are the author's own files, so there is no copyright question in committing them.
Community definitions from the forum are deliberately not vendored.

Each rule gets a crafted broken file asserting the exact line number and message.
That is the check that fails when a range is transcribed wrong, which is the most likely defect in this codebase.

## Decisions worth recording

**PC is 1–128 in the file, 0–127 on the wire.**
Manual §5.7 describes PC values as 0–127; the template requires 1–128.
The file format is one-indexed against MIDI's zero-indexed value.
The validator follows the file format, with a comment in `rules.go` explaining why, so the apparent off-by-one is not "fixed" later.

**`[CC]` numbers are validated as 0–127, warned above 119.**
Neither the manual nor the template states a range for the CC naming section.
Assign and automation destinations stop at 119, but naming is cosmetic, so a higher number is suspicious rather than invalid.
Flip it to an error if the hardware turns out to reject those files.

**No firmware versioning.**
The note that started this project wanted validation against a chosen OS version.
Deferred until a rule is actually observed to differ between firmwares.
The ruleset is small and self-contained, so introducing a second one later is a contained change.

## Later

A bubbletea TUI over the same `internal/def` package: browse definitions with validation status, view detail, then edit fields, CC entries, and drum lane rows in place, writing back through the lossless parser.
Each stage gets its own design.
