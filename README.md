# hapax-tui

Tools for [Squarp Hapax](https://squarp.net/hapax/) instrument definition files.
Check them before they go on the SD card, repair the obvious mistakes, and edit them through forms instead of a text editor.

## Install

Requires Python 3.13+.

```sh
uv tool install git+https://github.com/claytron/hapax-tui
```

This installs the `hapax` command.

## Validate

```sh
hapax validate                  # every definition under .
hapax validate Synths/TR-8S.txt
hapax validate --fw 3.10        # check against an older firmware
hapax validate --strict         # warnings fail the exit code too
hapax validate --no-warn        # errors only
```

Each file gets a line, followed by its findings:

```text
TR-8S.txt           2 warnings
  W line 109: only the first 15 characters are shown: 'AUTO FILL IN MA'
  W line 111: only the first 15 characters are shown: 'EXTERNAL IN LEV'

14 files, 0 errors, 52 warnings — Hapax OS 3.21
```

Errors (`E`) are things the Hapax will reject or misread.
Warnings (`W`) load, but probably not the way you meant.
Rules follow the firmware you target, from 1.12 through 3.21 (the default).
The exit code is 1 when there are errors, 2 when a path can't be read.

## Fix

```sh
hapax fix --diff                # show what would change
hapax fix                       # rewrite files in place
```

`fix` only repairs what has exactly one sensible repair:

- unclosed or stray section tags
- a `VERSION` other than 1
- non-ASCII characters in names (accents and smart quotes become their plain equivalents)
- a trailing `:value` on `[AUTOMATION]` and `[ASSIGN]` lines, rewritten as `DEFAULT=value`
- a `DEFAULT=` the firmware ignores, moved to the matching `[AUTOMATION]` lane

Anything else is left for you, and reported the same way `validate` would.

## Editor

```sh
hapax                           # browse definitions in .
hapax Synths/                   # browse a directory
hapax TR-8S.txt                 # edit a file
hapax New-Synth.txt             # create one
```

Each section is a tab of rows; the `+` tab adds a section.
Findings show inline as you edit, and comments in the file are kept.

| Key | Action |
| --- | --- |
| `ctrl+s` | Save |
| `a` / `d` | Add / delete row |
| `k` / `j` | Up / down a list, as well as `↑` / `↓` |
| `shift+↑` / `shift+↓` | Move row |
| `ctrl+h` / `ctrl+l` | Previous / next tab |
| `ctrl+k` / `ctrl+j` | Up / down between the tab bar, the tab, and the findings |
| `w` | Toggle warnings |
| `esc` | Back |
| `n` | New file (browser) |
| `?` | Show / hide all keys, when not in a field or form |
| `q` | Quit, when not in a field or form |

`--fw` and `--[no-]warn` work here too.

## Config

`~/.config/hapax/config.toml` (or `$XDG_CONFIG_HOME/hapax/config.toml`):

```toml
theme = "nord"   # saved when you pick a theme in the editor
warn = false     # default for --warn / --no-warn
```

## Development

```sh
uv sync
uv run pytest
```

## License

MIT; see [LICENSE](LICENSE).
