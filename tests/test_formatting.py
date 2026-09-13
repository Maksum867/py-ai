"""Tests for py_ai.formatting (language detection, fences, assembly)."""

from py_ai.formatting import assemble_output, detect_language, format_file_block


def test_language_by_extension():
    assert detect_language("src/main.py") == "python"
    assert detect_language("README.md") == "markdown"
    assert detect_language("data/plot.svg") == "xml"  # SVG packed as text/XML
    assert detect_language("unknown.xyz") == ""


def test_language_by_whole_file_name():
    assert detect_language("Dockerfile") == "dockerfile"
    assert detect_language("deploy/dockerfile") == "dockerfile"
    assert detect_language("Makefile") == "makefile"
    assert detect_language("CMakeLists.txt") == "cmake"
    assert detect_language(".gitignore") == "gitignore"
    assert detect_language(".editorconfig") == "ini"


def test_extension_takes_priority_over_name():
    # A file literally named 'dockerfile' with a real extension keeps its own language.
    assert detect_language("docker/Dockerfile.bak") == ""  # .bak unknown -> name has suffix, no mapping
    assert detect_language("ci/makefile.py") == "python"


def test_text_block_markers():
    block = format_file_block("a.py", "x=1", "text")
    assert block == "--- START OF FILE: a.py ---\nx=1\n--- END OF FILE: a.py ---"


def test_markdown_block_uses_detected_language():
    block = format_file_block("Dockerfile", "FROM python:3.13", "markdown")
    assert block.startswith("### `Dockerfile`\n```dockerfile\n")


def test_assemble_output_no_tree():
    stats = {
        "project_name": "p", "timestamp": "2026-01-01 00:00:00",
        "packed_count": 1, "failed_count": 0, "total_lines": 5,
        "estimated_tokens": 10, "token_method": "heuristic (~4 chars/token)",
    }
    text = assemble_output(stats, "", [format_file_block("a.py", "x=1", "text")],
                           "text", include_tree=False)
    assert "DIRECTORY TREE" not in text
    assert "FILES CONTENT" in text
