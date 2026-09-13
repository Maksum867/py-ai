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


def test_file_symlink_alias_packed_once(tmp_path):
    """A file symlink pointing INSIDE the project must not duplicate the
    content: the real file is packed, the alias is skipped with a note."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "real.py").write_text("IMPL=42", encoding="utf-8")
    (root / "alias.py").symlink_to(root / "real.py")

    out = tmp_path / "pack.txt"
    stats = pack_project(root, out, copy_to_clipboard=False)
    text = out.read_text(encoding="utf-8")

    assert text.count("IMPL=42") == 1
    assert stats["packed_count"] == 1
    assert stats["failed_count"] == 1
    # The alias stays visible in the tree with an explanatory note.
    assert "alias.py" in text.split("DIRECTORY TREE")[1].split("FILES CONTENT")[0]
    assert "symlink alias" in text


def test_real_files_with_same_content_are_both_packed(tmp_path):
    """Deduplication must only affect symlinks, not distinct files that
    happen to have equal content."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("SAME=1", encoding="utf-8")
    (root / "b.py").write_text("SAME=1", encoding="utf-8")

    out = tmp_path / "pack.txt"
    stats = pack_project(root, out, copy_to_clipboard=False)
    text = out.read_text(encoding="utf-8")

    assert stats["packed_count"] == 2
    assert text.count("SAME=1") == 2


def test_dangling_symlink_shown_with_note(tmp_path):
    """A symlink whose target does not exist must stay visible in the tree
    with an explanatory note instead of disappearing silently."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "ok.py").write_text("x=1", encoding="utf-8")
    (root / "dangling.py").symlink_to(root / "nonexistent.txt")

    out = tmp_path / "pack.txt"
    pack_project(root, out, copy_to_clipboard=False)
    text = out.read_text(encoding="utf-8")

    assert "dangling.py" in text
    assert "dangling symlink" in text
    assert "START OF FILE: dangling.py" not in text
