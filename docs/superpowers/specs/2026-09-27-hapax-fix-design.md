# Hapax Instrument Definition Fixer — Design

- Date: 2026-09-27
- Status: draft, under review
- Builds on: [validator design](2026-09-21-hapax-validator-design.md)

## Context

The validator reports every problem in a definition file.
Some of those problems have exactly one sensible repair, and making the author type it is busywork.
This stage adds `hapax fix` for those, and the line serializer the forms TUI ([design](2026-09-27-hapax-tui-design.md)) needs to write edits back.
It comes first because the TUI's open gate runs the fixer before it will load a file.

## Scope

```text
hapax fix [--diff] [--[no-]warn] [--fw VERSION] [paths...]
```

Paths, `--fw` and `--[no-]warn` behave exactly as in `hapax validate`.
Files are rewritten in place; `--diff` prints a unified diff per file and writes nothing.

Output per file: the name, one `F line N: …` line per fix applied, then the remaining findings in `validate`'s `E`/`W` format.
The summary adds the number of fixes applied.
Exit code 1 if errors remain after fixing, 2 on usage or I/O errors, else 0.

### Non-goals

- No fix that discards or rewrites what the author wrote beyond the list below: no trimming long names, no renumbering, no resolving duplicates, no clamping out-of-range values.
- No formatting normalisation of lines no fix touches.
- No interactive mode; the TUI is the interactive front end.

## The rule

A fix never changes what the author meant.
It only adds missing structure, removes bytes the Hapax ignores, or moves a value to where the Hapax honours it.
Every line a fix does not touch is written back byte for byte.
Anything outside the rule stays a finding for the author to fix by hand.

## Fixes

| Code | Fix |
| --- | --- |
| `file.bom` | Drop the byte-order mark. |
| `section.unclosed` | Insert `[/X]` on the line before the next header. |
| `section.unclosed_eof` | Append `[/X]` after the section's last non-blank line. |
| `section.stray_close` | Delete the line. |
| `version` | Set the value to `1`, keeping any trailing comment. |
| `name.char` | Transliterate: Unicode NFKD with combining marks dropped (`é`→`e`, `ü`→`u`), plus a small table (`ß`→`ss`, `æ`→`ae`, `ø`→`o`, curly quotes→straight, en/em dash→`-`). Characters with no mapping stay, and the finding remains. |
| `default.ignored` | On 3.00–3.19: remove `DEFAULT=` from the `[CC]`, `[NRPN]` or `[CC_PAIR]` line and put it on the matching `[AUTOMATION]` line (see below). |
| `automation.extra`, `assign.extra` | `CC:74:100` becomes `CC:74 DEFAULT=100`, as the warning already suggests. |

Moving a section default:

- A matching `[AUTOMATION]` line (same type and address) without a `DEFAULT=` gets it.
- No matching line: one is appended to `[AUTOMATION]`, creating the section at the end of the file if needed, provided the section stays within 64 lines.
- Hand fix instead when: the matching line already has a different `DEFAULT=`; the CC is 120–127 (unusable in `[AUTOMATION]`); the section is full.
- `CC_PAIR` `DEFAULT=` before 1.14 is not moved: that warning has a different cause and no automation-side equivalent is assumed.

Fixes are applied, the document is re-parsed and re-validated, and fixing repeats until nothing changes, so one fix enabling another (a closed section exposing a stray close) settles in one run.

## Architecture

```text
lines ──parse──► Document ──validate──► findings ──fix.py──► edited lines ──► write
                                                    │
                                          write.render(entry)
```

### `hapax/write.py`

`render(entry) -> str` turns any entry back into one line in the template's canonical form:

- Directives: `KEY VALUE`, key upper-cased.
- `[CC]` `CC NAME` / `CC:DEFAULT=v NAME`; `[PC]` `PC NAME` / `PC:MSB:LSB NAME`; `[CC_PAIR]` `MSB:LSB[:DEFAULT=v] NAME`; `[NRPN]` `MSB:LSB:DEPTH[:DEFAULT=v] NAME`, with `MSB` left empty only when the model's `msb` is `None`.
- `[DRUMLANES]`, `[ASSIGN]`, `[AUTOMATION]` in the forms the validator spec documents.
- Comment lines: `# text`, keeping the original indentation.

The undocumented shorthands (`CC:v NAME`, `MSB:LSB:DEPTH:v`) are rendered in their `DEFAULT=` form.
A trailing `# comment` on the original line is kept.
The rendered line takes the file's line ending: `\r` is appended when the original line (or, for a new line, the file's first line) ends with one.

The model's `Document.lines` is lossless apart from a leading BOM, so writing a document is `"\n".join(lines)`.
There is no separate `dump`.

### `hapax/fix.py`

`fix(lines, fw) -> (lines, list[Applied])`, where `Applied` is `(code, line, description)` with `line` as it was before fixing.
Each fix is a small function keyed on a finding code; it receives the finding and document and returns line edits (replace, insert, delete).
Edits from one pass are applied bottom-up so earlier line numbers stay valid.
Rendered replacements build the edited entry with `dataclasses.replace` and call `render`.

### `hapax/cli.py`

Gains the `fix` subcommand, sharing path expansion and the finding printer with `validate`.
`_files` and `_check` move to a module both the CLI and the TUI import (`hapax/files.py`).

## Testing

- **Render round trip:** for every entry in every corpus file (the author's 14, the 155 community files, the template and probes), parsing `render(entry)` yields the same fields.
- **Untouched output:** writing a parsed document with no edits reproduces the input bytes (minus a BOM).
- **Each fix:** before/after string pairs in `tests/test_fix.py`, including every hand-fix fallback for moved defaults.
- **Idempotence:** `fix` on its own output changes nothing.
- **Corpus safety:** fixing any corpus file never adds a finding code the file did not already have, and every line not reported as fixed is unchanged.
- **CLI:** in-place write, `--diff` leaves the file alone, output format, exit codes.
