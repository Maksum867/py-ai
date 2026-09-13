"""Tests for --budget (token limit check) and --dry-run (preview mode)."""

import pytest

from py_ai.cli import parse_token_budget
from py_ai.core import pack_project


def test_parse_token_budget():
    assert parse_token_budget("200000") == 200_000
    assert parse_token_budget("128k") == 128_000
    assert parse_token_budget(" 2 M ") == 2_000_000
    assert parse_token_budget("1.5k") == 1_500
    with pytest.raises(ValueError):
        parse_token_budget("banana")
    with pytest.raises(ValueError):
        parse_token_budget("0k")
    with pytest.raises(ValueError):
        parse_token_budget("-5")


def test_budget_within_limit(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    out = tmp_path / "o.txt"
    stats = pack_project(root, out, copy_to_clipboard=False, budget=1_000_000)
    assert stats["budget"] == 1_000_000
    assert stats["budget_exceeded"] is False


def test_budget_exceeded_reports_heaviest(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    (root / "big.py").write_text("x = 1\n" * 5000, encoding="utf-8")
    (root / "small.py").write_text("y = 2\n", encoding="utf-8")
    out = tmp_path / "o.txt"
    stats = pack_project(root, out, copy_to_clipboard=False, budget=100)
    assert stats["budget_exceeded"] is True
    heaviest = stats["heaviest_files"]
    assert heaviest[0]["path"] == "big.py"
    assert heaviest[0]["tokens"] > heaviest[-1]["tokens"]


def test_budget_requires_token_counting(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        pack_project(root, tmp_path / "o.txt", copy_to_clipboard=False,
                     budget=1000, enable_token_count=False)


def test_budget_positive_only(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        pack_project(root, tmp_path / "o.txt", copy_to_clipboard=False, budget=0)


def test_dry_run_writes_nothing(sample_project, tmp_path):
    out = tmp_path / "never.txt"
    stats = pack_project(sample_project, out, copy_to_clipboard=False, dry_run=True)
    assert stats["dry_run"] is True
    assert not out.exists()
    assert stats["clipboard_copied"] is False
    # All statistics still computed.
    assert stats["packed_count"] == 7
    assert stats["total_lines"] > 0
    assert stats["file_size"] > 0
    assert len(stats["files"]) == 7
    assert stats["files"][0]["tokens"] > 0


def test_per_file_stats_always_returned(sample_project, tmp_path):
    out = tmp_path / "o.txt"
    stats = pack_project(sample_project, out, copy_to_clipboard=False)
    paths = {f["path"] for f in stats["files"]}
    assert "src/main.py" in paths
    for record in stats["files"]:
        assert record["lines"] >= 0
        assert record["tokens"] is not None


def test_file_types_summary_computed(sample_project, tmp_path):
    out = tmp_path / "o.txt"
    stats = pack_project(sample_project, out, copy_to_clipboard=False)
    ft = stats["file_types"]
    assert ft[".py"]["files"] == 2
    assert ft[".md"]["files"] == 2  # README.md + docs/guide.md
    assert ft[".toml"]["files"] == 1
    assert ft[".py"]["lines"] > 0


def test_type_summary_in_header(sample_project, tmp_path):
    out = tmp_path / "o.txt"
    pack_project(sample_project, out, copy_to_clipboard=False)
    header = out.read_text(encoding="utf-8").split("DIRECTORY TREE")[0]
    assert "File types:" in header
    assert ".py" in header


def test_no_type_summary(sample_project, tmp_path):
    out = tmp_path / "o.txt"
    pack_project(sample_project, out, copy_to_clipboard=False,
                 include_type_summary=False)
    header = out.read_text(encoding="utf-8").split("DIRECTORY TREE")[0]
    assert "File types:" not in header
