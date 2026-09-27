"""hapax validate|fix [--[no-]warn] [--fw VERSION] [paths...]; anything else opens the editor"""

import argparse
import difflib
import sys
from pathlib import Path

from .files import check, expand, read
from .fix import Applied, fix
from .parse import Finding, Severity, parse
from .rules import LATEST, RELEASES, check_file_name, fw_str, parse_fw, validate


def _plural(n: int, word: str, suffix: str = "s") -> str:
    return f"{n} {word}{'' if n == 1 else suffix}"


def _fix(name: str, path: Path, fw, diff: bool) -> tuple[list[Applied], list[Finding], list[str]]:
    """Fix one file: (fixes applied, findings left, diff lines)."""
    text = read(path)
    if isinstance(text, Finding):
        return [], check_file_name(path.name) + [text], []
    fixed, applied = fix(text, fw)
    lines = []
    if diff:
        lines = list(difflib.unified_diff(text.splitlines(True), fixed.splitlines(True), name, name))
    elif fixed != text:
        path.write_bytes(fixed.encode("utf-8"))
    return applied, check_file_name(path.name) + validate(parse(fixed), fw), lines


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in ("validate", "fix", "-h", "--help"):
        from .tui.app import main as tui  # Textual loads only for the editor

        return tui(argv)
    parser = argparse.ArgumentParser(
        prog="hapax", description="Squarp Hapax instrument definition tools; with no command, the editor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(  # the editor parses its own options (tui/app.py), so they are not arguments here
            "editor:\n"
            "  hapax [--fw VERSION] [--[no-]warn] [PATH]\n"
            "  PATH: a directory to browse (default: .), a file to edit, or a new file to create"))
    commands = parser.add_subparsers(dest="command", required=True)
    validate_cmd = commands.add_parser("validate", help="check instrument definitions before copying them to the SD card")
    fix_cmd = commands.add_parser("fix", help="repair, in place, what has exactly one sensible repair")
    for cmd in (validate_cmd, fix_cmd):
        cmd.add_argument("paths", nargs="*", type=Path, default=[Path(".")], help="files or directories (default: .)")
        cmd.add_argument(
            "--fw", default=fw_str(LATEST),
            help=f"target firmware, {RELEASES[0]} to {RELEASES[-1]} (default: %(default)s)")
        cmd.add_argument(
            "--warn", action=argparse.BooleanOptionalAction, default=True,
            help="report warnings (default: on); --no-warn shows errors only")
    validate_cmd.add_argument("--strict", action="store_true", help="warnings also fail the exit code")
    fix_cmd.add_argument("--diff", action="store_true", help="print a diff and write nothing")
    args = parser.parse_args(argv)
    fixing = args.command == "fix"

    try:
        fw = parse_fw(args.fw)
    except ValueError as e:
        parser.error(str(e))
    files = expand(args.paths)
    if isinstance(files, str):
        print(f"hapax: {files}", file=sys.stderr)
        return 2

    width = max(len(name) for name, _ in files) + 2
    errors = warnings = fixes = 0
    for name, path in files:
        try:
            applied, findings, diff = _fix(name, path, fw, args.diff) if fixing else ([], check(path, fw), [])
        except OSError as e:
            print(f"hapax: {e}", file=sys.stderr)
            return 2
        if not args.warn:
            findings = [f for f in findings if f.severity is Severity.ERROR]
        errs = sum(f.severity is Severity.ERROR for f in findings)
        warns = len(findings) - errs
        errors, warnings, fixes = errors + errs, warnings + warns, fixes + len(applied)
        parts = (
            [_plural(len(applied), "fix", "es")] * bool(applied)
            + [_plural(errs, "error")] * bool(errs) + [_plural(warns, "warning")] * bool(warns))
        print(f"{name:<{width}}{', '.join(parts) or 'OK'}")
        for a in applied:
            print(f"  F line {a.line}: {a.description}")
        for f in findings:
            where = f"line {f.line}" if f.line else "file"
            print(f"  {'E' if f.severity is Severity.ERROR else 'W'} {where}: {f.message}")
        for line in diff:
            print(line, end="" if line.endswith("\n") else "\n")

    counts = (
        [_plural(len(files), "file")] + [_plural(fixes, "fix", "es")] * fixing
        + [_plural(errors, "error")] + [_plural(warnings, "warning")] * args.warn)
    print(f"\n{', '.join(counts)} — Hapax OS {fw_str(fw)}")
    if fixing:
        return 1 if errors else 0
    return 1 if errors or (args.strict and warnings) else 0
