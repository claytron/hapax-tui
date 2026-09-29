"""Settings in $XDG_CONFIG_HOME/hapax/config.toml (default ~/.config): theme = "name", warn = true|false."""

import json
import os
import re
import sys
import tomllib
from pathlib import Path


def path() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "hapax" / "config.toml"


def load() -> dict:
    try:
        return tomllib.loads(path().read_text())
    except FileNotFoundError:
        return {}
    except (OSError, tomllib.TOMLDecodeError) as e:
        print(f"hapax: ignoring {path()}: {e}", file=sys.stderr)
        return {}


def save_theme(theme: str) -> None:
    """Rewrite only the theme line, keeping the rest of the file as written; a file that does not parse is left alone."""
    p = path()
    try:
        text = p.read_text() if p.exists() else ""
        tomllib.loads(text)
    except (OSError, tomllib.TOMLDecodeError):
        return
    line = f"theme = {json.dumps(theme)}"  # a JSON string is a valid TOML basic string
    text, found = re.subn(r"^theme\s*=.*$", lambda _: line, text, count=1, flags=re.M)
    if not found:
        text = f"{line}\n{text}"  # at the top, so it never lands inside a [table]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
