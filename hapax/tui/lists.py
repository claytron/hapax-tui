"""Lists that also move with vim-style j/k."""

from textual import widgets
from textual.binding import Binding

VIM = [Binding("k", "cursor_up", "Up", show=False), Binding("j", "cursor_down", "Down", show=False)]


class DataTable(widgets.DataTable):
    BINDINGS = VIM


class OptionList(widgets.OptionList):
    BINDINGS = VIM
