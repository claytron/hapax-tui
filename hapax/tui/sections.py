"""What each section's table and row form show; both are built from these tables."""

from dataclasses import dataclass

from ..parse import AssignEntry, AutomationEntry, CcEntry, CcPairEntry, DrumEntry, NrpnEntry, PcEntry
from ..rules import INPORTS, MAXRATES, OUTPORTS, TYPES, TYPES_3_20

# Input.restrict patterns: a value can never add a ':', a space or a '#' that would change the line's shape.
NUMBER = r"[0-9]*"
PORT = r"[0-9A-Za-z]*"  # drum CHAN: 10, CV1, G2, CVG3
VOLTS = r"-?[0-9]*\.?[0-9]*[vV]?"  # [AUTOMATION] DEFAULT=: 100, -2.5V
TEXT = r"[^#]*"


@dataclass(frozen=True)
class Column:
    field: str
    label: str
    restrict: str = NUMBER
    choices: tuple[str, ...] | None = None  # a Select instead of an Input
    types: frozenset[str] | None = None  # automation types that use it; None: every type
    required: bool | frozenset[str] = False  # blank makes the line unparseable; a set: only for those types


def required(column: Column, kind: str | None) -> bool:
    """Whether the form must refuse this field blank, for the lane type `kind` (None outside [ASSIGN]/[AUTOMATION])."""
    return column.required if isinstance(column.required, bool) else kind in column.required


def _target(types: tuple[str, ...]) -> tuple[Column, ...]:
    def only(*names):
        return frozenset(names)
    return (
        Column("type", "TYPE", choices=types),
        Column("cc", "CC", types=only("CC"), required=True),
        Column("msb", "MSB", types=only("NRPN", "CC_PAIR"), required=only("CC_PAIR")),  # NRPN::2000:7 omits it
        Column("lsb", "LSB", types=only("NRPN", "CC_PAIR"), required=True),
        Column("depth", "DEPTH", types=only("NRPN"), required=True),
        Column("cv", "CV", types=only("CV"), required=True),
        Column("default", "DEFAULT", VOLTS, types=only("CC", "NRPN", "CC_PAIR", "CV")),
    )


NAME = Column("name", "NAME", TEXT, required=True)
DEFAULT = Column("default", "DEFAULT")
SECTIONS = {
    "CC": (CcEntry, (Column("cc", "CC", required=True), DEFAULT, NAME)),
    "PC": (PcEntry, (Column("pc", "PC", required=True), Column("msb", "MSB"), Column("lsb", "LSB"), NAME)),
    "CC_PAIR": (CcPairEntry, (
        Column("msb", "MSB CC", required=True), Column("lsb", "LSB CC", required=True), DEFAULT, NAME)),
    "NRPN": (NrpnEntry, (
        Column("msb", "MSB"), Column("lsb", "LSB", required=True), Column("depth", "DEPTH", required=True), DEFAULT,
        NAME)),
    "DRUMLANES": (DrumEntry, (
        Column("row", "ROW", required=True), Column("trig", "TRIG"), Column("chan", "CHAN", PORT),
        Column("note", "NOTE"), NAME)),
    "ASSIGN": (AssignEntry, (
        Column("pot", "POT", required=True), *_target(("CC", "NRPN", "CC_PAIR", "CV", "PB", "AT", "NULL")))),
    "AUTOMATION": (AutomationEntry, _target(("CC", "NRPN", "CC_PAIR", "CV", "PB", "AT"))),
}
ORDER = (*SECTIONS, "COMMENT")  # the order the "+" tab offers missing sections in
COMMENT = Column("text", "#", r".*")  # a comment line inside a table section

HEADER = {  # directive: label on the General tab; VERSION is left out, the fixer keeps it 1
    "TRACKNAME": "Track name",
    "TYPE": "Track type",
    "OUTPORT": "MIDI out port",
    "OUTCHAN": "MIDI out channel",
    "INPORT": "MIDI in port",
    "INCHAN": "MIDI in channel",
    "MAXRATE": "Max CC rate",
}


def header_choices(key: str, fw: tuple[int, int]) -> tuple[str, ...] | None:
    """The values a header directive's Select offers on this firmware; None for TRACKNAME, a text field."""
    virtual = tuple(f"{p}{n}" for p in ("USBD", "USBH") for n in range(1, 17)) if fw >= (3, 0) else ()
    channels = tuple(str(n) for n in range(1, 17))
    match key:
        case "TYPE":
            return tuple(sorted(TYPES | (TYPES_3_20 if fw >= (3, 20) else set())))
        case "OUTPORT":
            return (*sorted(OUTPORTS), *virtual)
        case "INPORT":
            return (*sorted(INPORTS), *virtual)
        case "OUTCHAN":
            return (*channels, "NULL")
        case "INCHAN":
            return (*channels, "ALL", "NULL")
        case "MAXRATE":
            return (*(str(n) for n in sorted(MAXRATES, reverse=True)), "NULL")
    return None
