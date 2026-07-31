"""Tests for symlink safety: escapes, cycles and duplicate links."""

import os

import pytest

from py_ai.core import pack_project

pytestmark = pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")


def test_symlink_outside_root_not_packed(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "real.py").write_text("x=1", encoding="utf-8")

    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET", encoding="utf-8")
    (root / "linked.txt").symlink_to(secret)

    out = tmp_path / "pack.txt"
    stats = pack_project(root, out, copy_to_clipboard=False)
    text = out.read_text(encoding="utf-8")

    assert "TOP SECRET" not in text
    assert stats["packed_count"] == 1
    assert "linked.txt" in text  # visible in the tree ...
    assert "symlink outside project root" in text  # ... with a warning note


def test_symlink_cycle_is_traversed_once(tmp_path):
    root = tmp_path / "proj"
    (root / "sub").mkdir(parents=True)
    (root / "code.py").write_text("x=1", encoding="utf-8")
    (root / "sub" / "loop").symlink_to(root / "sub", target_is_directory=True)

    out = tmp_path / "pack.txt"
    stats = pack_project(root, out, copy_to_clipboard=False)
    text = out.read_text(encoding="utf-8")

    assert stats["packed_count"] == 1
    assert "cyclic or duplicate link" in text
    # The tree must not explode with endlessly nested 'loop/' entries.
    assert text.count("loop/") <= 1


def test_duplicate_dir_link_packed_once(tmp_path):
    root = tmp_path / "proj"
    (root / "real").mkdir(parents=True)
    (root / "real" / "code.py").write_text("x=1", encoding="utf-8")
    (root / "alias").symlink_to(root / "real", target_is_directory=True)

    out = tmp_path / "pack.txt"
    pack_project(root, out, copy_to_clipboard=False)
    text = out.read_text(encoding="utf-8")

    content_section = text.split("FILES CONTENT")[1]
    assert content_section.count("--- START OF FILE: real/code.py") == 1
    assert "alias/code.py" not in content_section
