"""Tests for --format json (machine-readable output)."""

import json

from py_ai.core import pack_project
from py_ai.formatting import available_formats


def test_json_in_available_formats():
    assert "json" in available_formats()


def test_json_output_structure(sample_project, tmp_path):
    out = tmp_path / "pack.json"
    stats = pack_project(sample_project, out, copy_to_clipboard=False,
                         output_format="json")
    doc = json.loads(out.read_text(encoding="utf-8"))

    assert doc["format_version"] == 1
    assert doc["project"] == "sample"
    assert doc["stats"]["packed_count"] == stats["packed_count"] == 7
    assert doc["stats"]["total_lines"] == stats["total_lines"]
    assert doc["stats"]["token_method"] in {"cl100k_base (tiktoken)", "heuristic (~4 chars/token)"}

    paths = {f["path"]: f for f in doc["files"]}
    assert "src/main.py" in paths
    assert paths["src/main.py"]["content"] == "def main():\n    return 42\n"
    assert paths["src/main.py"]["lines"] == 2
    assert isinstance(paths["src/main.py"]["tokens"], int)

    assert ".gitignore" in doc["directory_tree"]
    assert doc["file_types"][".py"]["files"] == 2


def test_json_token_stats_match_document(sample_project, tmp_path):
    from py_ai.tokens import count_tokens
    out = tmp_path / "pack.json"
    stats = pack_project(sample_project, out, copy_to_clipboard=False,
                         output_format="json")
    doc = json.loads(out.read_bytes().decode("utf-8"))
    assert stats["estimated_tokens"] == count_tokens(out.read_bytes().decode("utf-8"))[0]
    assert doc["stats"]["estimated_tokens"] == stats["estimated_tokens"]


def test_json_records_skipped_files(sample_project, tmp_path):
    (sample_project / "data" / "mystery.xyz").write_bytes(b"\x00\x01\x02")
    out = tmp_path / "pack.json"
    pack_project(sample_project, out, copy_to_clipboard=False, output_format="json")
    doc = json.loads(out.read_text(encoding="utf-8"))
    skipped = {s["path"]: s["reason"] for s in doc["skipped"]}
    assert skipped.get("data/mystery.xyz") == "binary file"


def test_json_no_tree(sample_project, tmp_path):
    out = tmp_path / "pack.json"
    pack_project(sample_project, out, copy_to_clipboard=False,
                 output_format="json", include_tree=False)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert "directory_tree" not in doc


def test_json_invalid_format_still_rejected(sample_project, tmp_path):
    import pytest
    with pytest.raises(ValueError):
        pack_project(sample_project, tmp_path / "o", copy_to_clipboard=False,
                     output_format="xml")
