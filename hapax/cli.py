"""hapax validate [--strict] [--fw VERSION] [paths...]"""

import argparse
import sys
from pathlib import Path

from .parse import Finding, Severity, parse
from .rules import LATEST, RELEASES, check_file_name, fw_str, parse_fw, validate


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _files(paths: list[Path]) -> list[tuple[str, Path]] | str:
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


def _check(path: Path, fw) -> list[Finding]:
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as e:
        return [Finding(Severity.ERROR, "encoding", f"not valid UTF-8 (byte {e.start})", 0)]
    return validate(parse(text), fw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hapax", description="Squarp Hapax instrument definition tools")
    commands = parser.add_subparsers(dest="command", required=True)
    cmd = commands.add_parser("validate", help="check instrument definitions before copying them to the SD card")
    cmd.add_argument("paths", nargs="*", type=Path, default=[Path(".")], help="files or directories (default: .)")
    cmd.add_argument(
        "--fw", default=fw_str(LATEST),
        help=f"target firmware, {RELEASES[0]} to {RELEASES[-1]} (default: %(default)s)")
    cmd.add_argument("--strict", action="store_true", help="warnings also fail the exit code")
    args = parser.parse_args(argv)

    try:
        fw = parse_fw(args.fw)
    except ValueError as e:
        parser.error(str(e))
    files = _files(args.paths)
    if isinstance(files, str):
        print(f"hapax: {files}", file=sys.stderr)
        return 2

    width = max(len(name) for name, _ in files) + 2
    errors = warnings = 0
    for name, path in files:
        try:
            findings = check_file_name(path.name) + _check(path, fw)
        except OSError as e:
            print(f"hapax: {e}", file=sys.stderr)
            return 2
        errs = sum(f.severity is Severity.ERROR for f in findings)
        warns = len(findings) - errs
        errors, warnings = errors + errs, warnings + warns
        status = ", ".join([_plural(errs, "error")] * bool(errs) + [_plural(warns, "warning")] * bool(warns)) or "OK"
        print(f"{name:<{width}}{status}")
        for f in findings:
            where = f"line {f.line}" if f.line else "file"
            print(f"  {'E' if f.severity is Severity.ERROR else 'W'} {where}: {f.message}")

    print(f"\n{_plural(len(files), 'file')}, {_plural(errors, 'error')}, "
          f"{_plural(warnings, 'warning')} — Hapax OS {fw_str(fw)}")
    return 1 if errors or (args.strict and warnings) else 0
