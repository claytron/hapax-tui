"""hapax [--fw VERSION] [--[no-]warn] [PATH]: edit instrument definitions through forms."""

import argparse
from pathlib import Path

from textual.app import App

from ..files import read
from ..rules import LATEST, RELEASES, fw_str, parse_fw
from .browser import Browser
from .dialogs import Dialog, NewFile
from .edits import open_text
from .editor import Editor


class HapaxApp(App):
    TITLE = "hapax"

    def __init__(self, path: Path, fw=LATEST, warn: bool = True):
        super().__init__()
        self.path, self.fw, self.warn = path, fw, warn

    def on_mount(self) -> None:
        # The browser is always underneath, so leaving the editor or a dialog lands somewhere useful.
        directory = self.path if self.path.is_dir() else self.path.parent
        self.push_screen(Browser(directory))
        if self.path.is_file():
            self.open_file(self.path)
        elif not self.path.exists():
            self.new_file(directory, self.path.name)

    def open_file(self, path: Path) -> None:
        """The open gate: offer the fixer's changes, refuse what no form can show, then edit."""
        try:
            saved = read(path)
        except OSError as e:
            self.notify(str(e), severity="error")
            return
        text, applied, blocking = open_text(saved, self.fw)
        if blocking:
            lines = [f"{'line ' + str(f.line) if f.line else 'file'}: {f.message}" for f in blocking]
            self.push_screen(Dialog(f"{path.name} cannot be edited here; fix these in a text editor", lines, None))
            return

        def edit(ok: bool | None) -> None:
            if ok:
                self.push_screen(Editor(path, saved, text, self.fw, self.warn))

        if applied:
            lines = [f"line {a.line}: {a.description}" for a in applied]
            self.push_screen(Dialog(f"{path.name} needs these fixes", lines, "Apply and open"), edit)
        else:
            edit(True)

    def new_file(self, directory: Path, name: str = "") -> None:
        def created(path: Path | None) -> None:
            if path:
                self.open_file(path)

        self.push_screen(NewFile(directory, self.fw, name), created)

    async def action_quit(self) -> None:
        if isinstance(self.screen, Editor) and self.screen.dirty:
            self.push_screen(Dialog("Discard unsaved changes and quit?", [], "Quit"), lambda ok: ok and self.exit())
        else:
            self.exit()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="hapax", description="Edit Squarp Hapax instrument definitions. Also: hapax validate, hapax fix.")
    parser.add_argument(
        "path", nargs="?", type=Path, default=Path("."),
        help="a directory to browse, a file to edit, or a new file to create (default: .)")
    parser.add_argument(
        "--fw", default=fw_str(LATEST), help=f"target firmware, {RELEASES[0]} to {RELEASES[-1]} (default: %(default)s)")
    parser.add_argument(
        "--warn", action=argparse.BooleanOptionalAction, default=True, help="show warnings at start (default: on)")
    args = parser.parse_args(argv)
    try:
        fw = parse_fw(args.fw)
    except ValueError as e:
        parser.error(str(e))
    if not args.path.exists() and not args.path.parent.is_dir():
        parser.error(f"{args.path.parent}: no such directory")
    HapaxApp(args.path, fw, args.warn).run()
    return 0
