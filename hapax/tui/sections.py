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


def _target(types: tuple[str, ...]) -> tuple[Column, ...]:
    def only(*names):
        return frozenset(names)
    return (
        Column("type", "TYPE", choices=types),
        Column("cc", "CC", types=only("CC")),
        Column("msb", "MSB", types=only("NRPN", "CC_PAIR")),
        Column("lsb", "LSB", types=only("NRPN", "CC_PAIR")),
        Column("depth", "DEPTH", types=only("NRPN")),
        Column("cv", "CV", types=only("CV")),
        Column("default", "DEFAULT", VOLTS, types=only("CC", "NRPN", "CC_PAIR", "CV")),
    )


NAME = Column("name", "NAME", TEXT)
DEFAULT = Column("default", "DEFAULT")
SECTIONS = {
    "CC": (CcEntry, (Column("cc", "CC"), DEFAULT, NAME)),
    "PC": (PcEntry, (Column("pc", "PC"), Column("msb", "MSB"), Column("lsb", "LSB"), NAME)),
    "CC_PAIR": (CcPairEntry, (Column("msb", "MSB CC"), Column("lsb", "LSB CC"), DEFAULT, NAME)),
    "NRPN": (NrpnEntry, (Column("msb", "MSB"), Column("lsb", "LSB"), Column("depth", "DEPTH"), DEFAULT, NAME)),
    "DRUMLANES": (DrumEntry, (
        Column("row", "ROW"), Column("trig", "TRIG"), Column("chan", "CHAN", PORT), Column("note", "NOTE"), NAME)),
    "ASSIGN": (AssignEntry, (Column("pot", "POT"), *_target(("CC", "NRPN", "CC_PAIR", "CV", "PB", "AT", "NULL")))),
    "AUTOMATION": (AutomationEntry, _target(("CC", "NRPN", "CC_PAIR", "CV", "PB", "AT"))),
}
ORDER = (*SECTIONS, "COMMENT")  # the order the "+" tab offers missing sections in
COMMENT = Column("text", "#", r".*")  # a comment line inside a table section

HEADER = ("TRACKNAME", "TYPE", "OUTPORT", "OUTCHAN", "INPORT", "INCHAN", "MAXRATE")  # VERSION: the fixer keeps it 1


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
