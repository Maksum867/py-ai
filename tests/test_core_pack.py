"""Tests for py_ai.core.pack_project (output content, ordering, formats, limits)."""

import pytest

from py_ai.core import pack_project


def _packed_files(output_text: str) -> list[str]:
    """Extracts ordered file paths from the classic marker format."""
    files = []
    for line in output_text.splitlines():
        if line.startswith("--- START OF FILE: "):
            files.append(line[len("--- START OF FILE: "):-len(" ---")])
    return files


def test_basic_pack_markers_and_stats(sample_project):
    out = sample_project / "pack.txt"
    stats = pack_project(sample_project, out, copy_to_clipboard=False)

    text = out.read_text(encoding="utf-8")
    assert "PROJECT CONTEXT PACK: sample" in text
    assert "--- START OF FILE: src/main.py ---" in text
    assert "def main():" in text
    assert stats["packed_count"] == 7  # 2 py + guide.md + README + pyproject + .env.example + .gitignore
    assert stats["failed_count"] == 0
    assert stats["clipboard_copied"] is False

    # ignored things must not appear in the content section
    content_section = text.split("FILES CONTENT")[1]
    assert "SECRET=hunter2" not in text          # .env is never packed
    assert "--- START OF FILE: .git/config" not in content_section
    assert "lib.so" not in content_section
    assert "logo.png" not in content_section


def test_header_contains_token_and_line_stats(sample_project):
    out = sample_project / "pack.txt"
    stats = pack_project(sample_project, out, copy_to_clipboard=False)
    text = out.read_text(encoding="utf-8")

    assert "Total lines:" in text
    assert "Estimated tokens: ~" in text
    assert stats["estimated_tokens"] > 0
    assert stats["total_lines"] > 0
    assert stats["token_method"] in {
        "cl100k_base (tiktoken)", "heuristic (~4 chars/token)"
    }


def test_content_order_is_deterministic_dfs(tmp_path):
    """Subdirectories (with subtrees) come before files; all sorted ASC."""
    root = tmp_path / "ordered"
    (root / "pkg" / "sub").mkdir(parents=True)
    (root / "pkg" / "sub" / "d.py").write_text("d=1", encoding="utf-8")
    (root / "pkg" / "b.py").write_text("b=1", encoding="utf-8")
    (root / "pkg" / "c.py").write_text("c=1", encoding="utf-8")
    (root / "a.py").write_text("a=1", encoding="utf-8")
    (root / "z.py").write_text("z=1", encoding="utf-8")

    out = tmp_path / "out.txt"
    pack_project(root, out, copy_to_clipboard=False)
    files = _packed_files(out.read_text(encoding="utf-8"))

    assert files == ["pkg/sub/d.py", "pkg/b.py", "pkg/c.py", "a.py", "z.py"]


def test_output_file_excludes_itself_on_repeat_runs(sample_project):
    out = sample_project / "ai_context.txt"
    pack_project(sample_project, out, copy_to_clipboard=False)
    pack_project(sample_project, out, copy_to_clipboard=False)  # second run

    text = out.read_text(encoding="utf-8")
    tree_section = text.split("DIRECTORY TREE")[1].split("FILES CONTENT")[0]
    assert "ai_context.txt" not in tree_section
    assert "--- START OF FILE: ai_context.txt" not in text


def test_binary_file_marked_in_tree(sample_project):
    (sample_project / "data" / "dump.dat").write_bytes(b"\x00\x01\x02")  # ext-filtered
    weird = sample_project / "data" / "mystery.xyz"
    weird.write_bytes(b"\x00\x01\x02")  # unknown ext, NUL bytes -> skipped

    out = sample_project / "pack.txt"
    stats = pack_project(sample_project, out, copy_to_clipboard=False)
    text = out.read_text(encoding="utf-8")

    assert stats["failed_count"] == 1
    assert "mystery.xyz  [skipped: binary file]" in text
    assert "--- START OF FILE: data/mystery.xyz" not in text


def test_empty_project(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    out = tmp_path / "pack.txt"
    stats = pack_project(root, out, copy_to_clipboard=False)

    text = out.read_text(encoding="utf-8")
    assert stats["packed_count"] == 0
    assert "Total files packed: 0" in text
    assert out.is_file()


def test_max_file_size(tmp_path):
    root = tmp_path / "limits"
    root.mkdir()
    (root / "small.py").write_text("x=1", encoding="utf-8")
    (root / "big.py").write_text("x=1\n" * 5000, encoding="utf-8")  # ~20 KB

    out = tmp_path / "pack.txt"
    stats = pack_project(root, out, copy_to_clipboard=False, max_file_size=1024)
    text = out.read_text(encoding="utf-8")

    assert stats["packed_count"] == 1
    assert stats["failed_count"] == 1
    assert "big.py  [skipped: exceeds size limit (1.0 KB)]" in text
    assert "--- START OF FILE: big.py" not in text


def test_crlf_content_not_doubled_on_any_platform(tmp_path):
    """CRLF line endings from the source must never become CRCRLF in the output."""
    root = tmp_path / "crlf"
    root.mkdir()
    (root / "win.py").write_bytes(b"a = 1\r\nb = 2\r\n")
    out = tmp_path / "pack.txt"
    pack_project(root, out, copy_to_clipboard=False)

    raw = out.read_bytes()
    assert b"\r\r\n" not in raw
    text = out.read_text(encoding="utf-8")
    assert "--- START OF FILE: win.py ---\na = 1\nb = 2\n" in text


def test_exclude_patterns(sample_project):
    out = sample_project / "pack.txt"
    stats = pack_project(sample_project, out, copy_to_clipboard=False,
                         exclude_patterns=["docs/*", "*.toml"])
    text = out.read_text(encoding="utf-8")

    assert "--- START OF FILE: docs/guide.md" not in text
    assert "--- START OF FILE: pyproject.toml" not in text
    assert "--- START OF FILE: src/main.py" in text
    assert stats["packed_count"] == 5


def test_invalid_format_raises(sample_project):
    with pytest.raises(ValueError):
        pack_project(sample_project, sample_project / "x.txt",
                     copy_to_clipboard=False, output_format="xml")


def test_markdown_format(sample_project):
    out = sample_project / "pack.md"
    stats = pack_project(sample_project, out, copy_to_clipboard=False,
                         output_format="markdown")
    text = out.read_text(encoding="utf-8")

    assert text.startswith("# Project Context Pack")
    assert "## Directory Tree" in text
    assert "## Files Content" in text
    assert "### `src/main.py`" in text
    assert "```python\n" in text  # language detected by extension
    assert stats["output_format"] == "markdown"


def test_markdown_adaptive_fence_escapes_nested_backticks(tmp_path):
    root = tmp_path / "md"
    root.mkdir()
    (root / "notes.md").write_text("# Title\n```python\nnested()\n```\n", encoding="utf-8")

    out = tmp_path / "pack.md"
    pack_project(root, out, copy_to_clipboard=False, output_format="markdown")
    text = out.read_text(encoding="utf-8")

    # The wrapper fence must be longer than the 3-backtick run in the content.
    assert "````markdown\n# Title\n```python\nnested()\n```\n````" in text


def test_missing_root_and_file_as_root(tmp_path):
    with pytest.raises(FileNotFoundError):
        pack_project(tmp_path / "ghost", tmp_path / "o.txt", copy_to_clipboard=False)

    f = tmp_path / "file.txt"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        pack_project(f, tmp_path / "o.txt", copy_to_clipboard=False)


def test_write_failure_raises_ioerror(sample_project, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    # Parent path component is a regular file -> mkdir/open must fail.
    with pytest.raises(IOError):
        pack_project(sample_project, blocker / "o.txt", copy_to_clipboard=False)


def test_file_size_reports_real_disk_bytes(sample_project, tmp_path):
    """'file_size' must be the on-disk byte count, not the character count
    (len() understates non-ASCII content, e.g. Cyrillic in UTF-8)."""
    root = tmp_path / "cyr"
    root.mkdir()
    (root / "ukr.txt").write_text("Привіт, світе!\n" * 100, encoding="utf-8")

    out = tmp_path / "pack.txt"
    stats = pack_project(root, out, copy_to_clipboard=False)
    assert stats["file_size"] == out.stat().st_size
    assert stats["file_size"] > len(out.read_text(encoding="utf-8"))  # bytes > chars


def test_leftover_default_output_name_is_never_packed(tmp_path):
    """A leftover 'ai_context.txt' from a previous run must not be packed
    even when the new run writes to a differently-named output file."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "app.py").write_text("x=1", encoding="utf-8")
    (root / "ai_context.txt").write_text("OLD PACK CONTENT", encoding="utf-8")

    out = tmp_path / "fresh.txt"
    pack_project(root, out, copy_to_clipboard=False)
    text = out.read_text(encoding="utf-8")

    assert "START OF FILE: app.py" in text
    assert "ai_context.txt" not in text.split("FILES CONTENT")[1]


def test_nested_file_with_default_output_name_is_packed(tmp_path):
    """Only the ROOT-level default output name ('ai_context.txt') is treated
    as a leftover pack; a legit nested file with the same name must be packed."""
    root = tmp_path / "proj"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "ai_context.txt").write_text("LEGIT DOC", encoding="utf-8")
    (root / "app.py").write_text("x=1", encoding="utf-8")

    out = tmp_path / "fresh.txt"
    pack_project(root, out, copy_to_clipboard=False)
    content_section = out.read_text(encoding="utf-8").split("FILES CONTENT")[1]

    assert "--- START OF FILE: docs/ai_context.txt ---" in content_section
    assert "--- START OF FILE: app.py ---" in content_section


def test_collect_files_survives_zero_inodes(tmp_path, monkeypatch):
    """On filesystems where st_ino is 0/unreliable, directories must not be
    silently treated as duplicates (which used to drop whole subtrees)."""
    import os

    import py_ai.core as core

    root = tmp_path / "proj"
    (root / "dir1").mkdir(parents=True)
    (root / "dir2").mkdir(parents=True)
    (root / "dir1" / "a.py").write_text("a", encoding="utf-8")
    (root / "dir2" / "b.py").write_text("b", encoding="utf-8")
    (root / "c.py").write_text("c", encoding="utf-8")

    real_stat = os.stat

    def zero_ino_stat(path, *args, **kwargs):
        st = real_stat(path, *args, **kwargs)
        return os.stat_result((
            st.st_mode, 0, st.st_dev, st.st_nlink, st.st_uid, st.st_gid,
            st.st_size, st.st_atime, st.st_mtime, st.st_ctime,
        ))

    monkeypatch.setattr(os, "stat", zero_ino_stat)
    files = core._collect_files(root, root / "out.txt", core.make_filter(root))

    # as_posix() normalizes separators so the assertion works on Windows too.
    rels = sorted(f.relative_to(root).as_posix() for f in files)
    assert rels == ["c.py", "dir1/a.py", "dir2/b.py"]
