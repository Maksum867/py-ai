"""Tests for --strip-docs (comment/docstring removal)."""

from py_ai.core import pack_project
from py_ai.stripping import strip_python_docs

SOURCE = '''"""Module docstring.
More lines.
"""
import os  # os comment

# standalone comment
def f(a, b):
    """Function docstring."""
    url = "http://example.com/#anchor"  # trailing comment
    return a + b


class C:
    """Class docs."""
    pass
'''


def test_docstrings_and_comments_removed():
    out = strip_python_docs(SOURCE)
    assert "docstring" not in out.lower()
    assert "comment" not in out.lower()
    assert "def f(a, b):" in out
    assert "return a + b" in out
    assert "class C:" in out
    # A string literal that contains '#' must survive (only COMMENTS go).
    assert "http://example.com/#anchor" in out


def test_string_with_hash_preserved():
    src = 'x = "http://ex.com/#a"\ny = 2\n'
    out = strip_python_docs(src)
    assert "http://ex.com/#a" in out
    assert "y = 2" in out


def test_empty_def_gets_pass():
    src = 'def only_docs():\n    """docs."""\n'
    out = strip_python_docs(src)
    assert "def only_docs():" in out
    assert "pass" in out


def test_invalid_syntax_untouched():
    src = "def broken(:\n    pass\n"
    assert strip_python_docs(src) == src


def test_empty_source_untouched():
    assert strip_python_docs("") == ""
    assert strip_python_docs("\n\n") == "\n\n"


def test_strip_docs_in_pack(sample_project, tmp_path):
    (sample_project / "src" / "main.py").write_text(
        '"""docs."""\ndef main():\n    """docs."""\n    return 42  # answer\n',
        encoding="utf-8",
    )
    out = tmp_path / "pack.txt"
    stats = pack_project(sample_project, out, copy_to_clipboard=False, strip_docs=True)
    text = out.read_text(encoding="utf-8")
    assert "docs." not in text.split("FILES CONTENT")[1].split("--- START OF FILE: src/main.py ---")[1]
    assert stats["packed_count"] == 7


def test_strip_docs_off_by_default(sample_project, tmp_path):
    (sample_project / "src" / "main.py").write_text(
        '"""docs."""\ndef main():\n    return 42\n', encoding="utf-8")
    out = tmp_path / "pack.txt"
    pack_project(sample_project, out, copy_to_clipboard=False)
    text = out.read_text(encoding="utf-8")
    assert '"""docs."""' in text
