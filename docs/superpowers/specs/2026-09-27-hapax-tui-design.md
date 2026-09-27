# Hapax Instrument Definition TUI — Design

- Date: 2026-09-27
- Status: draft, under review
- Builds on: [validator design](2026-09-21-hapax-validator-design.md), [fixer design](2026-09-27-hapax-fix-design.md)

## Context

The validator and fixer work on files the author edits elsewhere.
This stage is the point of the project: a [Textual](https://github.com/Textualize/textual) TUI that edits definitions through forms, so the author picks ports from a list and types a CC number into a field instead of remembering syntax.
The author already has a text editor; this is deliberately not another one.

Goals:

- Edit an existing file.
- See errors and warnings inline and as a list.
- Hide warnings.
- Create a new file.

### Non-goals

- No raw text editing of entries, no editor or LSP integration.
- No bulk entry (pasting parameter lists from a manual); that is left to separate AI-assisted tooling.
- No completion from Lark's interactive parser; forms make it unnecessary.
- No changing the target firmware inside a session.
- No SD card detection or copying.

## Entry points

```text
hapax [--fw VERSION] [--[no-]warn] [PATH]
```

- `PATH` a directory (default `.`): the file browser.
- `PATH` an existing `.txt` file: straight into the editor, through the open gate.
- `PATH` that does not exist: the new-file dialog, with the name filled in.

`hapax validate` and `hapax fix` are unchanged.
`--fw` is fixed for the session and shown in the footer; `--[no-]warn` sets the warning toggle's starting state.

## Data flow

The editor's source of truth is the file's lines, not the forms.

```text
form action ──render──► line edit ──► lines ──parse──► Document ──validate──► findings
     ▲                                                     │                     │
     └──────────────── tables, forms, tab badges ◄─────────┴─────────────────────┘
```

Every action (edit a row, add, delete, move, add a section) renders the row with `write.render` and replaces, inserts or deletes lines.
The whole document is then re-parsed and re-validated; the per-line parse cache means only changed lines are parsed again, and the validator's 50 ms guard keeps this interactive.
Line numbers, spans, comments, blank lines and untouched lines stay correct with no extra bookkeeping, and saving is `"\n".join(lines)`.

Findings map onto the screen through the model:

- `line` → the entry, and so the tab and row.
- `field` → the form field to mark.
- A section header's line → a badge on that tab.
- Line 0 (whole file, file name) → the findings panel only.

## Screens

### Browser

A table of `name | status` for the `*.txt` files in the directory, with status as in `validate` (`OK`, `2E 1W`).
Refreshed on return from the editor.
Keys: `enter` edit, `n` new, `q` quit.

### Open gate

Opening a file:

1. Runs `fix` in memory.
   If it would change anything, a dialog lists the fixes: "Apply and open" or "Cancel".
   Applied fixes mark the document unsaved; nothing is written until save.
2. If structural errors remain — `encoding`, `syntax`, `section.unknown`, `directive.unknown` — refuses to open and lists them by line, to be fixed in a text editor.
   These have no typed entry a form could show.

Every other error (ranges, `name.char`, duplicates, `automation.count`) belongs to an entry and opens normally.

### Editor

```text
Header  CC(64) ●2  PC(12)  NRPN(8) ○1  AUTOMATION(20)  +
┌───────────────────────────────────────────┐
│  CC   DEFAULT  NAME                        │
│  74   64       Cutoff                      │
│● 75   —        Resonänce    ← 'ä' ASCII    │
│  76   —        Env Amount                  │
└───────────────────────────────────────────┘
 Findings (1E 1W)                 [w] warnings on
 ● E CC 75   name.char  'ä': names are ASCII only
 ○ W NRPN 3  name.long  shows 15 of 19 chars
```

**Tabs.**
Header first, then one tab per section in file order, then `+` to add a section the file lacks (added at the end of the file with its close tag).
Tab labels carry counts: `●N` errors, `○N` warnings.

**Header tab.**
A form with one field per directive: selects for `TYPE`, `OUTPORT`, `OUTCHAN`, `INPORT`, `INCHAN`, `MAXRATE` (built from the `rules` constants, filtered by firmware, with `NULL`), text for `TRACKNAME`.
`VERSION` is not shown; the fixer keeps it at `1`.

**Section tabs.**
A `DataTable` of the section's entries.
The gutter marks rows with an error (`●`) or warning (`○`), and the row shows its first message on the right.
Comment lines inside a section are dim `# …` rows, edited as text.
Keys: `enter` edit row, `a` add row after the cursor, `d` delete (confirm), `ctrl+↑`/`ctrl+↓` move.

**Row form.**
Docked below the table, one field per column.
On every keystroke the candidate line is rendered and validated in place, and messages appear under the fields they name.
`enter` applies, `esc` cancels.

**COMMENT sections.**
A `TextArea` over the section's lines; `name.char` findings show in the panel.

**Findings panel.**
Docked at the bottom, listing every finding with severity, location (section and row, or `file`), code and message.
Selecting one jumps to its tab, row and field.

**Warnings.**
`w` toggles warnings in the panel, badges and gutter together.

**Save and quit.**
`ctrl+s` writes the file.
With errors remaining it asks "N errors — the Hapax may reject this file. Save anyway?".
Leaving with unsaved changes asks first.

### New file

A dialog with the file name (the 27-character `file.name_long` warning appears as you type) and the header fields from the header tab.
Creating writes `VERSION 1` and the header directives, then opens the editor with no sections.
An existing name is refused.

## Architecture

| Module | Purpose |
| --- | --- |
| `hapax/tui/app.py` | App, CLI options, screen routing |
| `hapax/tui/browser.py` | File list and status |
| `hapax/tui/editor.py` | Tabs, tables, row form, findings panel |
| `hapax/tui/dialogs.py` | Open gate, confirm, new file |
| `hapax/tui/sections.py` | Per-section column specs: field, label, kind (int range, choice, text) |
| `hapax/tui/edits.py` | Pure functions on `lines`: set, add, delete, move row; add section |

`sections.py` is a plain table; tables and forms are both built from it.
`edits.py` has no Textual imports, so every operation is tested without a UI.
`cli.py` routes a bare `hapax` (no `validate`/`fix`) to `tui.app.main`.
`textual` becomes a dependency.

## Testing

- **`edits.py`:** each operation on `lines`, checking the result parses to the intended entries and leaves other lines untouched.
- **`sections.py`:** every column's field exists on its entry class; choice lists match the `rules` constants.
- **Pilot tests** (`App.run_test`):
  - Open a corpus file, edit a name, save: only that line changed.
  - Open gate: fix prompt on a file with a BOM; refusal on a syntax error.
  - `w` hides and shows warnings.
  - Selecting a finding focuses its row.
  - New file: the written file passes `hapax validate` with no errors.
