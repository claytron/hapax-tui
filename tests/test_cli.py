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
    [],
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
