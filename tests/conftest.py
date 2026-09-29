import pytest


@pytest.fixture(autouse=True)
def config_home(tmp_path, monkeypatch):
    """Keep every test away from the real ~/.config/hapax."""
    home = tmp_path / "config-home"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
    return home
