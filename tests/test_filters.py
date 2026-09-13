"""Tests for py_ai.filters (ignore rules, user patterns, combined filter)."""

import pytest

from py_ai.filters import (
    _is_outside_root,
    _rebase_ignore_line,
    load_ignore_matcher,
    make_filter,
    matches_ignore_files,
    matches_user_patterns,
    should_ignore,
)


def test_svg_is_text_and_packed(tmp_path):
    """SVG is a text/XML format and must not be filtered by extension."""
    root = tmp_path / "p"
    root.mkdir()
    svg = root / "logo.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>', encoding="utf-8")
    assert not should_ignore(svg, root)


def test_rebase_unanchored_pattern_matches_any_depth():
    """Git semantics: an unanchored pattern from a nested .gitignore must
    match at ANY depth below the ignore file's directory, so the rebase
    produces 'sub/**/pattern' (a plain 'sub/pattern' would anchor it)."""
    assert _rebase_ignore_line("*.tmp", "sub") == "sub/**/*.tmp"
    assert _rebase_ignore_line("build/", "sub") == "sub/**/build/"
    assert _rebase_ignore_line("!keep.tmp", "sub") == "!sub/**/keep.tmp"


def test_rebase_anchored_pattern_stays_anchored():
    """Anchored patterns (inner slash) are relative to the ignore file dir."""
    assert _rebase_ignore_line("/top.tmp", "sub") == "sub/top.tmp"
    assert _rebase_ignore_line("a/b.tmp", "sub") == "sub/a/b.tmp"
    assert _rebase_ignore_line("a/**/c.tmp", "sub") == "sub/a/**/c.tmp"
    # Comments and blanks pass through untouched.
    assert _rebase_ignore_line("# comment", "sub") == "# comment"
    assert _rebase_ignore_line("", "sub") == ""


def test_nested_gitignore_matches_any_depth(tmp_path):
    """Integration: 'sub/.gitignore' with '*.tmp' must ignore tmp-files at
    any depth below sub/ (git behaviour), not only direct children."""
    pytest.importorskip("pathspec")

    root = tmp_path / "p"
    (root / "sub" / "deep" / "deeper").mkdir(parents=True)
    (root / "sub" / ".gitignore").write_text("*.tmp\n", encoding="utf-8")
    (root / "sub" / "x.tmp").write_text("x", encoding="utf-8")
    (root / "sub" / "deep" / "y.tmp").write_text("y", encoding="utf-8")
    (root / "sub" / "deep" / "deeper" / "z.tmp").write_text("z", encoding="utf-8")
    (root / "sub" / "ok.py").write_text("ok", encoding="utf-8")

    matcher = load_ignore_matcher(root)
    assert matcher is not None
    assert matches_ignore_files(root / "sub" / "x.tmp", root, matcher)
    assert matches_ignore_files(root / "sub" / "deep" / "y.tmp", root, matcher)
    assert matches_ignore_files(root / "sub" / "deep" / "deeper" / "z.tmp", root, matcher)
    assert not matches_ignore_files(root / "sub" / "ok.py", root, matcher)


def test_nested_gitignore_anchored_pattern_not_matched_deeper(tmp_path):
    """An anchored nested pattern ('/top.tmp') applies only to the direct
    child of the ignore file's dir, exactly like git."""
    pytest.importorskip("pathspec")

    root = tmp_path / "p"
    (root / "sub" / "deep").mkdir(parents=True)
    (root / "sub" / ".gitignore").write_text("/top.tmp\n", encoding="utf-8")
    (root / "sub" / "top.tmp").write_text("x", encoding="utf-8")
    (root / "sub" / "deep" / "top.tmp").write_text("x", encoding="utf-8")

    matcher = load_ignore_matcher(root)
    assert matches_ignore_files(root / "sub" / "top.tmp", root, matcher)
    assert not matches_ignore_files(root / "sub" / "deep" / "top.tmp", root, matcher)


def test_nested_gitignore_negation_works_at_depth(tmp_path):
    """'!keep.tmp' from a nested ignore file re-includes files at any depth."""
    pytest.importorskip("pathspec")

    root = tmp_path / "p"
    (root / "sub" / "deep").mkdir(parents=True)
    (root / "sub" / ".gitignore").write_text("*.tmp\n!keep.tmp\n", encoding="utf-8")
    (root / "sub" / "a.tmp").write_text("x", encoding="utf-8")
    (root / "sub" / "deep" / "keep.tmp").write_text("x", encoding="utf-8")
    (root / "sub" / "deep" / "b.tmp").write_text("x", encoding="utf-8")

    matcher = load_ignore_matcher(root)
    assert matches_ignore_files(root / "sub" / "a.tmp", root, matcher)
    assert not matches_ignore_files(root / "sub" / "deep" / "keep.tmp", root, matcher)
    assert matches_ignore_files(root / "sub" / "deep" / "b.tmp", root, matcher)


def test_ignores_vcs_and_venv(tmp_path):
    root = tmp_path / "p"
    (root / ".git").mkdir(parents=True)
    (root / "node_modules" / "dep").mkdir(parents=True)
    (root / "pkg.egg-info").mkdir()
    assert should_ignore(root / ".git", root)
    assert should_ignore(root / ".git" / "config", root)
    assert should_ignore(root / "node_modules" / "dep", root)


def test_ignores_egg_info_suffixed_dirs(tmp_path):
    root = tmp_path / "p"
    target = root / "my_pkg.egg-info"
    target.mkdir(parents=True)
    (target / "PKG-INFO").write_text("Metadata", encoding="utf-8")
    assert should_ignore(target, root)
    assert should_ignore(target / "PKG-INFO", root)


def test_ignores_binary_and_office_extensions(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    for name in ("a.exe", "b.bin", "c.dat", "d.zip", "e.png", "f.xlsx"):
        f = root / name
        f.write_bytes(b"\x00\x01")
        assert should_ignore(f, root), name


def test_case_insensitive_builtin_names(tmp_path):
    root = tmp_path / "p"
    target = root / "ENV"
    target.mkdir(parents=True)
    assert should_ignore(target / "x.txt", root)


def test_hidden_policy(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    env = root / ".env"
    env.write_text("S=1", encoding="utf-8")
    assert should_ignore(env, root)  # secrets never packed

    for allowed in (".gitignore", ".editorconfig", ".dockerignore", ".env.example"):
        f = root / allowed
        f.write_text("x", encoding="utf-8")
        assert not should_ignore(f, root), allowed


def test_outside_root_is_ignored(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("x", encoding="utf-8")
    assert _is_outside_root(outside, root)


def test_user_exclude_patterns(tmp_path):
    root = tmp_path / "p"
    (root / "docs").mkdir(parents=True)
    f1 = root / "docs" / "a.md"
    f1.write_text("x", encoding="utf-8")
    f2 = root / "app.log"
    f2.write_text("x", encoding="utf-8")

    assert matches_user_patterns(f1, root, ["docs/*"])
    assert matches_user_patterns(f2, root, ["*.log"])
    assert not matches_user_patterns(f1, root, ["*.log"])
    assert not matches_user_patterns(f2, root, [])


def test_make_filter_combines_layers(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    builtin = root / "image.png"
    builtin.write_bytes(b"\x89PNG")
    custom = root / "custom.skip"
    custom.write_text("x", encoding="utf-8")
    normal = root / "app.py"
    normal.write_text("x=1", encoding="utf-8")

    predicate = make_filter(root, patterns=["*.skip"])
    assert predicate(builtin)
    assert predicate(custom)
    assert not predicate(normal)


def test_bare_files_named_like_ignored_dirs_are_packed(tmp_path):
    """Regular files literally named 'dist'/'env'/'build' (no extension) must
    be packed: IGNORED_NAMES contains *directory* names and must not filter
    files."""
    root = tmp_path / "p"
    root.mkdir()
    for name in ("dist", "env", "build", "venv"):
        f = root / name
        f.write_text("content", encoding="utf-8")
        assert not should_ignore(f, root), name
    # ... but OS junk file names stay ignored (files must exist to be judged)
    for junk in ("Thumbs.db", "desktop.ini"):
        j = root / junk
        j.write_text("content", encoding="utf-8")
        assert should_ignore(j, root), junk


def test_directory_pattern_with_trailing_slash(tmp_path):
    root = tmp_path / "p"
    (root / "generated" / "deep").mkdir(parents=True)
    (root / "keep").mkdir()

    d = root / "generated"
    deep = root / "generated" / "deep" / "x.py"
    keep = root / "keep" / "y.py"

    assert matches_user_patterns(d, root, ["generated/"])
    assert matches_user_patterns(deep, root, ["generated/"])
    assert not matches_user_patterns(keep, root, ["generated/"])


def test_directory_pattern_does_not_match_same_named_file(tmp_path):
    """Git semantics: 'build/' excludes the DIRECTORY build, not a regular
    file literally named 'build'."""
    root = tmp_path / "p"
    root.mkdir()
    f = root / "build"
    f.write_text("#!/bin/sh\n", encoding="utf-8")

    assert not matches_user_patterns(f, root, ["build/"])
