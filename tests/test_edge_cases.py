"""Edge-case tests: deep nesting, unreadable dirs, ignore-file support."""

import os
import sys

import pytest

from py_ai.core import pack_project


def _iterative_rmtree(path):
    """Removes a directory tree WITHOUT recursion: on Python <= 3.11 both
    shutil.rmtree and pytest's garbage collection recurse per level and
    crash (RecursionError) on very deep trees created by this test."""
    dirs = []
    stack = [path]
    while stack:
        current = stack.pop()
        dirs.append(current)
        for child in current.iterdir():
            if child.is_dir() and not child.is_symlink():
                stack.append(child)
            else:
                child.unlink()
    for directory in reversed(dirs):
        directory.rmdir()


def test_deeply_nested_project(tmp_path):
    """Deep nesting must not hit the recursion limit (iterative traversal).

    The depth is platform-capped: macOS enforces a 1024-byte PATH_MAX, so an
    1100-level tree physically cannot exist there (the runner's tmp base path
    alone consumes ~100 bytes). Linux/Windows runners handle 1100 levels.
    """
    budget = 950 if sys.platform == "darwin" else 4000
    base_len = len(str(tmp_path / "deep")) + 8  # "/deep" + slack
    depth = max(40, min(1100, (budget - base_len) // 2))

    current = tmp_path / "deep"
    current.mkdir()
    for _ in range(depth):
        current = current / "d"
        current.mkdir()
    (current / "leaf.py").write_text("x=1", encoding="utf-8")

    out = tmp_path / "pack.txt"
    stats = pack_project(tmp_path / "deep", out, copy_to_clipboard=False)
    assert stats["packed_count"] == 1
    text = out.read_text(encoding="utf-8")
    assert "leaf.py" in text

    # Self-cleanup (iterative): pytest's own recursive tmp-dir garbage
    # collection would crash on Python <= 3.11 otherwise.
    _iterative_rmtree(tmp_path / "deep")
    assert not (tmp_path / "deep").exists()


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


def test_nested_gitignore_is_honored(tmp_path):
    """A .gitignore inside a subdirectory applies to that subtree — at ANY
    depth below it (git semantics for unanchored patterns)."""
    pytest.importorskip("pathspec")

    root = tmp_path / "nested"
    (root / "sub" / "deep" / "deeper").mkdir(parents=True)
    (root / "sub" / ".gitignore").write_text("*.tmp\n", encoding="utf-8")
    (root / "sub" / "secret.tmp").write_text("x", encoding="utf-8")
    (root / "sub" / "deep" / "deep_secret.tmp").write_text("x", encoding="utf-8")
    (root / "sub" / "deep" / "deeper" / "deeper_secret.tmp").write_text("x", encoding="utf-8")
    (root / "sub" / "ok.txt").write_text("y", encoding="utf-8")

    out = tmp_path / "pack.txt"
    pack_project(root, out, copy_to_clipboard=False)
    content_section = out.read_text(encoding="utf-8").split("FILES CONTENT")[1]

    assert "--- START OF FILE: sub/ok.txt ---" in content_section
    assert "--- START OF FILE: sub/secret.tmp ---" not in content_section
    assert "--- START OF FILE: sub/deep/deep_secret.tmp ---" not in content_section
    assert "--- START OF FILE: sub/deep/deeper/deeper_secret.tmp ---" not in content_section


def test_pyaiignore_negation_overrides_gitignore(tmp_path):
    """Rules in .pyaiignore (later, tool-specific) must be able to re-include
    files ignored by .gitignore via '!' negation."""
    pytest.importorskip("pathspec")

    root = tmp_path / "prio"
    root.mkdir()
    (root / ".gitignore").write_text("*.log\n", encoding="utf-8")
    (root / ".pyaiignore").write_text("!keep.log\n", encoding="utf-8")
    (root / "keep.log").write_text("important", encoding="utf-8")
    (root / "drop.log").write_text("junk", encoding="utf-8")

    out = tmp_path / "pack.txt"
    pack_project(root, out, copy_to_clipboard=False)
    content_section = out.read_text(encoding="utf-8").split("FILES CONTENT")[1]

    assert "--- START OF FILE: keep.log ---" in content_section     # re-included
    assert "--- START OF FILE: drop.log ---" not in content_section  # still ignored


def test_gitignore_negation_does_not_leak_into_pyaiignore_rules(tmp_path):
    """The reverse direction: .pyaiignore '*' must beat .gitignore '!keep'.
    (A later rule in the merged matcher wins.)"""
    pytest.importorskip("pathspec")

    root = tmp_path / "prio2"
    root.mkdir()
    (root / ".gitignore").write_text("!keep.log\n", encoding="utf-8")
    (root / ".pyaiignore").write_text("*.log\n", encoding="utf-8")
    (root / "keep.log").write_text("important", encoding="utf-8")

    out = tmp_path / "pack.txt"
    pack_project(root, out, copy_to_clipboard=False)
    content_section = out.read_text(encoding="utf-8").split("FILES CONTENT")[1]

    assert "--- START OF FILE: keep.log ---" not in content_section


def test_excluded_dir_pruned_from_tree(tmp_path):
    """A directory whose entire content was excluded must not appear in the
    tree as an empty folder (tree stays consistent with packed content)."""
    root = tmp_path / "prune"
    (root / "docs" / "deep").mkdir(parents=True)
    (root / "docs" / "a.md").write_text("x", encoding="utf-8")
    (root / "docs" / "deep" / "b.md").write_text("x", encoding="utf-8")
    (root / "app.py").write_text("y=1", encoding="utf-8")

    out = tmp_path / "pack.txt"
    pack_project(root, out, copy_to_clipboard=False, exclude_patterns=["docs/*"])
    tree_section = out.read_text(encoding="utf-8").split("DIRECTORY TREE")[1].split("FILES CONTENT")[0]

    assert "docs" not in tree_section
    assert "app.py" in tree_section


def test_gitignored_dir_pruned_from_tree(tmp_path):
    """Same pruning for .gitignore-based exclusion (when pathspec available)."""
    pytest.importorskip("pathspec")

    root = tmp_path / "prune2"
    (root / "generated").mkdir(parents=True)
    (root / "generated" / "out.bin").write_bytes(b"\x00\x01")
    (root / "app.py").write_text("y=1", encoding="utf-8")
    (root / ".gitignore").write_text("generated/\n", encoding="utf-8")

    out = tmp_path / "pack.txt"
    pack_project(root, out, copy_to_clipboard=False)
    tree_section = out.read_text(encoding="utf-8").split("DIRECTORY TREE")[1].split("FILES CONTENT")[0]

    assert "generated" not in tree_section
