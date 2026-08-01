"""Tests for the py_ai CLI (argument handling, exit codes, messaging)."""

import sys

import pytest

import pyperclip

from py_ai import __version__
from py_ai.cli import main, parse_size


def _run_cli(argv, monkeypatch):
    monkeypatch.setattr(sys, "argv", argv)
    return main()


def test_successful_run(sample_project, tmp_path, monkeypatch, capsys):
    out = tmp_path / "ctx.txt"
    _run_cli(["pyai", str(sample_project), "-o", str(out), "--no-clipboard"], monkeypatch)
    captured = capsys.readouterr()

    assert "Project successfully packed!" in captured.out
    assert "Estimated Tokens:" in captured.out
    assert "Total Lines:" in captured.out
    assert out.is_file()

def test_console_emoji_safe_on_legacy_codepage(sample_project, tmp_path, monkeypatch):
    """CLI output must never crash on legacy console code pages (cp125x pipes)."""
    import io

    buffer = io.BytesIO()
    # Імітація перенаправленої Windows-консолі зі старою кодовою сторінкою
    wrapper = io.TextIOWrapper(buffer, encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", wrapper)

    out = tmp_path / "ctx.txt"
    monkeypatch.setattr(sys, "argv",
                        ["pyai", str(sample_project), "-o", str(out), "--no-clipboard"])
    main()  # без фіксу тут UnicodeEncodeError
    wrapper.flush()
    assert buffer.getvalue()  # щось надрукувалось

def test_version_flag(monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        _run_cli(["pyai", "--version"], monkeypatch)
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_missing_directory_exits_1(tmp_path, monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        _run_cli(["pyai", str(tmp_path / "ghost"), "--no-clipboard"], monkeypatch)
    assert exc.value.code == 1
    assert "Error" in capsys.readouterr().err


def test_file_as_root_exits_1(tmp_path, monkeypatch):
    f = tmp_path / "f.txt"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        _run_cli(["pyai", str(f), "--no-clipboard"], monkeypatch)
    assert exc.value.code == 1


def test_invalid_size_exits_2(sample_project, monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        _run_cli(["pyai", str(sample_project), "--no-clipboard",
                  "--max-file-size", "ten-megabytes"], monkeypatch)
    assert exc.value.code == 2


def test_unwritable_output_exits_1(sample_project, tmp_path, monkeypatch, capsys):
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        _run_cli(["pyai", str(sample_project), "-o", str(blocker / "o.txt"),
                  "--no-clipboard"], monkeypatch)
    assert exc.value.code == 1
    assert "Write Error" in capsys.readouterr().err


def test_invalid_format_exits_2(sample_project, monkeypatch):
    with pytest.raises(SystemExit) as exc:
        _run_cli(["pyai", str(sample_project), "--no-clipboard", "--format", "xml"], monkeypatch)
    assert exc.value.code == 2  # argparse choices error


def test_clipboard_failure_warns_exactly_once(sample_project, tmp_path, monkeypatch, capsys):
    def _boom(_text):
        raise pyperclip.PyperclipException("no clipboard here")

    monkeypatch.setattr(pyperclip, "copy", _boom)
    out = tmp_path / "ctx.txt"
    _run_cli(["pyai", str(sample_project), "-o", str(out)], monkeypatch)  # clipboard ON
    captured = capsys.readouterr()

    total = captured.out + captured.err
    assert total.count("Could not copy to clipboard") == 1
    assert out.is_file()  # output still saved


def test_parse_size():
    assert parse_size("512") == 512
    assert parse_size("512B") == 512
    assert parse_size("1KB") == 1024
    assert parse_size("1.5KB") == 1536
    assert parse_size("10MB") == 10 * 1024 ** 2
    assert parse_size("2GB") == 2 * 1024 ** 3
    assert parse_size("  64 kb ") == 64 * 1024
    with pytest.raises(ValueError):
        parse_size("10.5XB")
    with pytest.raises(ValueError):
        parse_size("banana")
    # zero / sub-byte sizes are rejected (would silently skip every file)
    with pytest.raises(ValueError):
        parse_size("0")
    with pytest.raises(ValueError):
        parse_size("0B")
    with pytest.raises(ValueError):
        parse_size("0.5B")
