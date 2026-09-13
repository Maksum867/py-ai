"""Tests for --include patterns (pack only matching files)."""

from py_ai.core import pack_project


def _tree(text):
    return text.split("DIRECTORY TREE")[1].split("FILES CONTENT")[0]


def _content(text):
    return text.split("FILES CONTENT")[1]


def test_include_src_only(tmp_path):
    root = tmp_path / "proj"
    (root / "src" / "deep").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    (root / "src" / "main.py").write_text("a=1", encoding="utf-8")
    (root / "src" / "deep" / "util.py").write_text("b=2", encoding="utf-8")
    (root / "docs" / "guide.md").write_text("d", encoding="utf-8")
    (root / "README.md").write_text("r", encoding="utf-8")

    out = tmp_path / "pack.txt"
    stats = pack_project(root, out, copy_to_clipboard=False, include_patterns=["src/**"])
    text = out.read_text(encoding="utf-8")

    assert stats["packed_count"] == 2
    content = _content(text)
    assert "START OF FILE: src/main.py" in content
    assert "START OF FILE: src/deep/util.py" in content
    assert "README.md" not in content
    # Non-included dirs are pruned from the tree.
    tree = _tree(text)
    assert "docs" not in tree
    assert "README" not in tree


def test_include_name_glob_any_depth(tmp_path):
    root = tmp_path / "proj"
    (root / "a" / "b").mkdir(parents=True)
    (root / "x.py").write_text("1", encoding="utf-8")
    (root / "a" / "y.py").write_text("2", encoding="utf-8")
    (root / "a" / "b" / "z.py").write_text("3", encoding="utf-8")
    (root / "a" / "notes.md").write_text("4", encoding="utf-8")

    out = tmp_path / "pack.txt"
    stats = pack_project(root, out, copy_to_clipboard=False, include_patterns=["*.py"])
    assert stats["packed_count"] == 3
    content = _content(out.read_text(encoding="utf-8"))
    assert "notes.md" not in content


def test_include_keeps_ancestor_dirs(tmp_path):
    """Including a deep file must keep every ancestor dir in the tree."""
    root = tmp_path / "proj"
    (root / "deep" / "nested").mkdir(parents=True)
    (root / "deep" / "nested" / "x.py").write_text("1", encoding="utf-8")
    (root / "other.py").write_text("2", encoding="utf-8")

    out = tmp_path / "pack.txt"
    stats = pack_project(root, out, copy_to_clipboard=False,
                         include_patterns=["deep/nested/x.py"])
    assert stats["packed_count"] == 1
    tree = _tree(out.read_text(encoding="utf-8"))
    assert "deep/" in tree
    assert "nested/" in tree


def test_include_dir_pattern_with_slash(tmp_path):
    root = tmp_path / "proj"
    (root / "lib").mkdir(parents=True)
    (root / "lib" / "a.py").write_text("1", encoding="utf-8")
    (root / "m.py").write_text("2", encoding="utf-8")

    out = tmp_path / "pack.txt"
    stats = pack_project(root, out, copy_to_clipboard=False, include_patterns=["lib/"])
    assert stats["packed_count"] == 1
    assert "START OF FILE: lib/a.py" in out.read_text(encoding="utf-8")


def test_include_combined_with_exclude(tmp_path):
    """Exclude wins inside the included set."""
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "keep.py").write_text("1", encoding="utf-8")
    (root / "src" / "drop.log").write_text("2", encoding="utf-8")
    (root / "elsewhere.py").write_text("3", encoding="utf-8")

    out = tmp_path / "pack.txt"
    stats = pack_project(root, out, copy_to_clipboard=False,
                         include_patterns=["src/**"], exclude_patterns=["*.log"])
    assert stats["packed_count"] == 1
    content = _content(out.read_text(encoding="utf-8"))
    assert "keep.py" in content
    assert "drop.log" not in content


def test_include_cannot_resurrect_builtin_ignores(tmp_path):
    """Built-in security rules win: include can't pack into .git / binary."""
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    (root / ".git" / "evil.py").write_text("1", encoding="utf-8")
    (root / "ok.py").write_text("2", encoding="utf-8")
    (root / "pic.png").write_bytes(b"\x89PNG")

    out = tmp_path / "pack.txt"
    stats = pack_project(root, out, copy_to_clipboard=False, include_patterns=["**"])
    assert stats["packed_count"] == 1
    content = _content(out.read_text(encoding="utf-8"))
    assert "evil.py" not in content
    assert "pic.png" not in content


def test_include_empty_patterns_mean_everything(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("1", encoding="utf-8")
    (root / "b.md").write_text("2", encoding="utf-8")
    out = tmp_path / "pack.txt"
    stats = pack_project(root, out, copy_to_clipboard=False, include_patterns=[])
    assert stats["packed_count"] == 2
