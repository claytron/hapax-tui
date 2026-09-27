"""Finding and reading definition files, shared by every front end."""

from pathlib import Path

from .parse import Finding, Severity, parse
from .rules import check_file_name, validate


def expand(paths: list[Path]) -> list[tuple[str, Path]] | str:
    """(display name, path) pairs, or an error message."""
    files = []
    for p in paths:
        if p.is_dir():
            files += [
                (f.name, f) for f in sorted(p.glob("*.txt", case_sensitive=False))
                if f.is_file() and not f.name.startswith(".")  # macOS writes ._Name.txt beside every copy
            ]
        elif p.is_file():
            if not p.name.startswith("."):
                files.append((str(p), p))
        else:
            return f"{p}: no such file or directory"
    return files or "no .txt files found"


def read(path: Path) -> str | Finding:
    """The file's text, or the finding that stops it being read. OSError propagates."""
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as e:
        return Finding(Severity.ERROR, "encoding", f"not valid UTF-8 (byte {e.start})", 0)


def check(path: Path, fw) -> list[Finding]:
    text = read(path)
    content = [text] if isinstance(text, Finding) else validate(parse(text), fw)
    return check_file_name(path.name) + content
