"""hapax [--fw VERSION] [--[no-]warn] [PATH]: edit instrument definitions through forms."""

import argparse
from pathlib import Path

from textual.app import App
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Input, Select, TextArea

from .. import config
from ..files import read
from ..rules import LATEST, RELEASES, fw_str, parse_fw
from .browser import Browser
from .dialogs import Dialog, NewFile
from .edits import open_text
from .editor import Editor, RowForm


class HapaxApp(App):
    TITLE = "hapax"
    BINDINGS = [Binding("q", "quit_idle", "Quit"), Binding("question_mark", "keys", "All keys")]

    def __init__(self, path: Path, fw=LATEST, warn: bool = True, theme: str | None = None):
        super().__init__()
        self.path, self.fw, self.warn, self.saved_theme = path, fw, warn, theme

    def on_mount(self) -> None:
        if self.saved_theme in self.available_themes:
            self.theme = self.saved_theme
        # The browser is always underneath, so leaving the editor or a dialog lands somewhere useful.
        directory = self.path if self.path.is_dir() else self.path.parent
        self.push_screen(Browser(directory))
        if self.path.is_file():
            self.open_file(self.path)
        elif not self.path.exists():
            self.new_file(directory, self.path.name)

    def watch_theme(self, theme: str) -> None:
        if self.is_mounted and theme != self.saved_theme:  # a pick from the command palette
            self.saved_theme = theme
            config.save_theme(theme)

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

    def check_action(self, action: str, parameters) -> bool | None:
        if action in ("quit_idle", "keys") and self.editing():
            return False  # the key goes to the field instead; ctrl+q still quits
        return True

    def editing(self) -> bool:
        """Whether a dialog, a field, or a row form is open: where q is not a request to quit."""
        focused = self.focused
        return isinstance(self.screen, ModalScreen) or bool(self.screen.query(RowForm)) or focused is not None and any(
            isinstance(w, (Input, Select, TextArea)) for w in focused.ancestors_with_self)

    def action_keys(self) -> None:
        if self.screen.query("HelpPanel"):
            self.action_hide_help_panel()
        else:
            self.action_show_help_panel()

    async def action_quit_idle(self) -> None:
        await self.action_quit()

    async def action_quit(self) -> None:
        if any(isinstance(s, Editor) and s.dirty for s in self.screen_stack):  # also under a dialog
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
    settings = config.load()
    parser.add_argument(
        "--warn", action=argparse.BooleanOptionalAction, default=settings.get("warn", True),
        help=f"show warnings at start (default: {'on' if settings.get('warn', True) else 'off'}, from {config.path()})")
    args = parser.parse_args(argv)
    try:
        fw = parse_fw(args.fw)
    except ValueError as e:
        parser.error(str(e))
    if not args.path.exists() and not args.path.parent.is_dir():
        parser.error(f"{args.path.parent}: no such directory")
    HapaxApp(args.path, fw, args.warn, settings.get("theme")).run()
    return 0
