import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "new_firmware", Path(__file__).parent.parent / ".github" / "scripts" / "new_firmware.py"
)
new_firmware = importlib.util.module_from_spec(spec)
spec.loader.exec_module(new_firmware)

PAGE = '<a href="/hapaxOS/1.0/hapax.bin"></a><a href="/hapaxOS/3.22/hapax.bin"></a><a href="/hapaxOS/3.21/hapax.bin"></a>'


def test_newer_release_found():
    assert new_firmware.newest(PAGE, ("3.20", "3.21")) == "3.22"


def test_nothing_new():
    assert new_firmware.newest(PAGE, ("3.21", "3.22")) is None


def test_minor_compares_numerically():
    assert new_firmware.newest('/hapaxOS/3.9/hapax.bin /hapaxOS/3.10/hapax.bin', ("3.9",)) == "3.10"


def test_empty_page():
    assert new_firmware.newest("", ("3.21",)) is None
