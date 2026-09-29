import os

import pytest

from hapax.cli import main


def run(args):
    try:
        return main(args)
    except SystemExit as e:  # argparse usage errors
        return e.code


def write(directory, name, text):
    path = directory / name
    path.write_text(text)
    return path


def test_clean_directory_skips_dotfiles_and_backups(tmp_path, capsys):
    write(tmp_path, "A.txt", "VERSION 1\n")
    write(tmp_path, "B.TXT", "VERSION 1\n")
    write(tmp_path, "._A.txt", "\x00\x01")  # macOS resource fork
    write(tmp_path, "C.txt.bak", "junk")  # 3.00 ignores .txt.bak
    assert run(["validate", str(tmp_path)]) == 0
    assert capsys.readouterr().out == (
        "A.txt  OK\n"
        "B.TXT  OK\n"
        "\n"
        "2 files, 0 errors, 0 warnings — Hapax OS 3.21\n"
    )


def test_findings_are_listed_under_their_file(tmp_path, capsys):
    path = write(tmp_path, "bad.txt", "VERSION 2\nOUTCHAN 17\n")
    assert run(["validate", "--fw", "3.10", str(path)]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"{path}  1 error, 1 warning"
    assert out[1].startswith("  W line 1: ")
    assert out[2].startswith("  E line 2: ")
    assert out[-1] == "1 file, 1 error, 1 warning — Hapax OS 3.10"


def test_warnings_count_only_with_strict(tmp_path):
    path = write(tmp_path, "w.txt", "VERSION 2\n")
    assert run(["validate", str(path)]) == 0
    assert run(["validate", "--strict", str(path)]) == 1


def test_file_that_is_not_utf8_is_an_error_and_others_still_run(tmp_path, capsys):
    (tmp_path / "a.txt").write_bytes(b"TRACKNAME \xff\n")
    write(tmp_path, "b.txt", "VERSION 1\n")
    assert run(["validate", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "a.txt  1 error\n  E file: " in out
    assert "b.txt  OK" in out


def test_no_paths_means_the_current_directory(tmp_path, monkeypatch, capsys):
    write(tmp_path, "A.txt", "VERSION 1\n")
    monkeypatch.chdir(tmp_path)
    assert run(["validate"]) == 0
    assert capsys.readouterr().out.startswith("A.txt  OK\n")


@pytest.mark.parametrize("args", [
    ["validate", "does-not-exist"],
    ["validate", "--fw", "3.11", "."],
    ["validate", "--fw", "1.11", "."],
    ["--fw", "3.11"],  # the editor's options fail before it starts
    ["no-such-dir/new.txt"],
])
def test_usage_and_io_failures_exit_2(args, tmp_path, monkeypatch):
    write(tmp_path, "A.txt", "VERSION 1\n")
    monkeypatch.chdir(tmp_path)
    assert run(args) == 2


def test_no_txt_files_exits_2(tmp_path):
    assert run(["validate", str(tmp_path)]) == 2


def test_long_file_name_warns(tmp_path, capsys):
    write(tmp_path, "A" * 28 + ".txt", "VERSION 1\n")
    assert run(["validate", str(tmp_path)]) == 0
    assert "1 warning\n  W file: " in capsys.readouterr().out


def test_no_warn_hides_warnings(tmp_path, capsys):
    path = write(tmp_path, "w.txt", "VERSION 2\nOUTCHAN 17\n")
    assert run(["validate", "--no-warn", str(path)]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"{path}  1 error"
    assert out[1].startswith("  E line 2: ")
    assert out[-1] == "1 file, 1 error — Hapax OS 3.21"


def test_no_warn_ignores_strict(tmp_path):
    path = write(tmp_path, "w.txt", "VERSION 2\n")
    assert run(["validate", "--no-warn", "--strict", str(path)]) == 0


def test_warn_is_the_default_and_can_be_given(tmp_path, capsys):
    path = write(tmp_path, "w.txt", "VERSION 2\n")
    run(["validate", "--warn", str(path)])
    assert capsys.readouterr().out.endswith("0 errors, 1 warning — Hapax OS 3.21\n")

def test_fix_rewrites_in_place_and_reports(tmp_path, capsys):
    path = write(tmp_path, "a.txt", "VERSION 2\n[CC]\n74 Cutoff\n")
    assert run(["fix", str(path)]) == 0
    assert path.read_text() == "VERSION 1\n[CC]\n74 Cutoff\n[/CC]\n"
    assert capsys.readouterr().out == (
        f"{path}  2 fixes\n"
        "  F line 1: VERSION 2 → 1\n"
        "  F line 2: closed [CC]\n"
        "\n"
        "1 file, 2 fixes, 0 errors, 0 warnings — Hapax OS 3.21\n"
    )


def test_fix_keeps_crlf(tmp_path):
    path = tmp_path / "a.txt"
    path.write_bytes(b"VERSION 2\r\n[CC]\r\n74 x\r\n")
    run(["fix", str(path)])
    assert path.read_bytes() == b"VERSION 1\r\n[CC]\r\n74 x\r\n[/CC]\r\n"


def test_fix_diff_writes_nothing(tmp_path, capsys):
    path = write(tmp_path, "a.txt", "VERSION 2\n")
    assert run(["fix", "--diff", str(path)]) == 0
    assert path.read_text() == "VERSION 2\n"
    out = capsys.readouterr().out
    assert "-VERSION 2\n+VERSION 1\n" in out


def test_fix_leaves_clean_files_alone(tmp_path):
    path = write(tmp_path, "a.txt", "VERSION 1\n")
    os.utime(path, ns=(0, 0))
    assert run(["fix", str(path)]) == 0
    assert path.stat().st_mtime_ns == 0


def test_fix_exits_1_when_errors_remain(tmp_path, capsys):
    path = write(tmp_path, "a.txt", "[CC]\n200 x\n[/CC]\n")
    assert run(["fix", str(path)]) == 1
    assert "  E line 2: " in capsys.readouterr().out


def test_fix_does_not_touch_a_file_that_is_not_utf8(tmp_path, capsys):
    path = tmp_path / "a.txt"
    path.write_bytes(b"VERSION 2\n\xff\n")
    assert run(["fix", str(path)]) == 1
    assert path.read_bytes() == b"VERSION 2\n\xff\n"
    assert "  E file: not valid UTF-8" in capsys.readouterr().out


def test_fix_takes_the_firmware(tmp_path):
    path = write(tmp_path, "a.txt", "[CC]\n74:64 C\n[/CC]\n[AUTOMATION]\nCC:74\n[/AUTOMATION]\n")
    run(["fix", "--fw", "3.10", str(path)])
    assert path.read_text() == "[CC]\n74 C\n[/CC]\n[AUTOMATION]\nCC:74 DEFAULT=64\n[/AUTOMATION]\n"


def test_help_shows_how_to_open_the_editor(capsys):
    assert run(["--help"]) == 0
    assert "hapax [--fw VERSION] [--[no-]warn] [PATH]" in capsys.readouterr().out


def test_warn_off_in_the_config_hides_warnings(tmp_path, config_home, capsys):
    (config_home / "hapax").mkdir(parents=True)
    (config_home / "hapax" / "config.toml").write_text("warn = false\n")
    (tmp_path / "Old.txt").write_text("VERSION 2\n")
    main(["validate", str(tmp_path)])
    assert "warning" not in capsys.readouterr().out
    main(["validate", "--warn", str(tmp_path)])
    assert "1 warning" in capsys.readouterr().out
