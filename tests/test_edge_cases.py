"""Edge-case tests: deep nesting, unreadable dirs, ignore-file support."""

import os

import pytest

from py_ai.core import pack_project


def test_deeply_nested_project(tmp_path):
    """~1100 levels of nesting must not hit the recursion limit."""
    current = tmp_path / "deep"
    current.mkdir()
    for _ in range(1100):
        current = current / "d"
        current.mkdir()
    (current / "leaf.py").write_text("x=1", encoding="utf-8")

    out = tmp_path / "pack.txt"
    stats = pack_project(tmp_path / "deep", out, copy_to_clipboard=False)
    assert stats["packed_count"] == 1
    text = out.read_text(encoding="utf-8")
    assert "leaf.py" in text


@pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0,
    reason="permission bits are not enforceable for root / on this platform",
)
def test_unreadable_directory_reported_once(tmp_path):
    root = tmp_path / "perm"
    (root / "secret_dir").mkdir(parents=True)
    (root / "secret_dir" / "x.txt").write_text("x", encoding="utf-8")
    (root / "public.py").write_text("y=1", encoding="utf-8")
    os.chmod(root / "secret_dir", 0)
    try:
        out = tmp_path / "pack.txt"
        stats = pack_project(root, out, copy_to_clipboard=False)
        text = out.read_text(encoding="utf-8")
    finally:
        os.chmod(root / "secret_dir", 0o755)

    assert stats["packed_count"] == 1
    assert "[Cannot access directory: Permission denied]" in text
    tree_section = text.split("DIRECTORY TREE")[1].split("FILES CONTENT")[0]
    assert tree_section.count("secret_dir") == 1  # no duplicated entries


def test_gitignore_and_pyaiignore_respected_when_pathspec_available(tmp_path):
    pytest.importorskip("pathspec")

    root = tmp_path / "ign"
    (root / "ignored_dir").mkdir(parents=True)
    (root / ".gitignore").write_text("ignored_dir/\n*.secret\n", encoding="utf-8")
    (root / "ignored_dir" / "a.py").write_text("a=1", encoding="utf-8")
    (root / "b.secret").write_text("b=1", encoding="utf-8")
    (root / "c.py").write_text("c=1", encoding="utf-8")

    out = tmp_path / "pack.txt"
    stats = pack_project(root, out, copy_to_clipboard=False)
    text = out.read_text(encoding="utf-8")
    content_section = text.split("FILES CONTENT")[1]

    assert "--- START OF FILE: c.py" in content_section
    assert ".gitignore" in content_section  # allowlisted hidden file is still packed
    assert "ignored_dir/a.py" not in content_section
    assert "b.secret" not in content_section
    assert stats["packed_count"] == 2  # c.py + .gitignore

    # Explicit opt-out disables the matcher.
    out2 = tmp_path / "pack2.txt"
    stats2 = pack_project(root, out2, copy_to_clipboard=False, respect_gitignore=False)
    assert stats2["packed_count"] == 4


def test_pyaiignore_file(tmp_path):
    pytest.importorskip("pathspec")

    root = tmp_path / "ign2"
    root.mkdir()
    (root / ".pyaiignore").write_text("skipme.py\n", encoding="utf-8")
    (root / "skipme.py").write_text("s=1", encoding="utf-8")
    (root / "keepme.py").write_text("k=1", encoding="utf-8")

    out = tmp_path / "pack.txt"
    pack_project(root, out, copy_to_clipboard=False)
    content_section = out.read_text(encoding="utf-8").split("FILES CONTENT")[1]

    assert "keepme.py" in content_section
    assert "skipme.py" not in content_section
