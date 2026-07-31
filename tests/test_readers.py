"""Tests for py_ai.readers (encodings, BOMs, binary detection)."""

from py_ai.readers import looks_binary, read_text_content


def _write(tmp_path, name, raw: bytes):
    f = tmp_path / name
    f.write_bytes(raw)
    return f


def test_plain_utf8(tmp_path):
    f = _write(tmp_path, "a.py", "print('ї')\n".encode("utf-8"))
    content, err = read_text_content(f)
    assert err is None
    assert content == "print('ї')\n"


def test_utf8_with_bom(tmp_path):
    f = _write(tmp_path, "a.txt", "hello".encode("utf-8-sig"))
    content, err = read_text_content(f)
    assert err is None
    assert content == "hello"


def test_utf16_with_bom(tmp_path):
    f = _write(tmp_path, "u16.txt", "Замітки UTF-16".encode("utf-16"))
    content, err = read_text_content(f)
    assert err is None
    assert content == "Замітки UTF-16"


def test_utf32_with_bom(tmp_path):
    f = _write(tmp_path, "u32.txt", "wide".encode("utf-32"))
    content, err = read_text_content(f)
    assert err is None
    assert content == "wide"


def test_cp1251_cyrillic(tmp_path):
    f = _write(tmp_path, "win.txt", "Привіт світ".encode("cp1251"))
    content, err = read_text_content(f)
    assert err is None
    assert content == "Привіт світ"


def test_latin1_last_resort(tmp_path):
    # 0x98 is undefined in cp1251, so the chain must fall through to latin-1.
    f = _write(tmp_path, "late.txt", b"\x98foo")
    content, err = read_text_content(f)
    assert err is None
    assert content == "\x98foo"


def test_binary_nul_detection(tmp_path):
    f = _write(tmp_path, "raw.bin", b"abc\x00def")
    content, reason = read_text_content(f)
    assert content is None
    assert reason == "binary file"


def test_empty_file(tmp_path):
    f = _write(tmp_path, "empty.py", b"")
    content, err = read_text_content(f)
    assert err is None
    assert content == ""


def test_bom_only_file(tmp_path):
    f = _write(tmp_path, "bom.txt", b"\xff\xfe")
    content, err = read_text_content(f)
    assert err is None
    assert content == ""


def test_missing_file_reports_reason(tmp_path):
    content, reason = read_text_content(tmp_path / "nope.txt")
    assert content is None
    assert reason is not None and "read error" in reason


def test_looks_binary():
    assert looks_binary(b"\x00")
    assert not looks_binary(b"plain text")
    # NUL beyond the inspected window is not detected (documented heuristic).
    assert not looks_binary(b"x" * 9000 + b"\x00")
