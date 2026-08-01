"""Tests for py_ai.filters (ignore rules, user patterns, combined filter)."""

import pytest

from py_ai.filters import (
    matches_user_patterns,
    should_ignore,
    make_filter,
    _is_outside_root,
)


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
