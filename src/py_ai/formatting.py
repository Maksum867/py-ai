"""
formatting.py module
====================
Assembly of the final context output for the py-ai utility.
Two output formats are supported:

- 'text'     : classic plain-text format with START/END OF FILE markers
               (default, backwards compatible).
- 'markdown' : Markdown document with fenced code blocks and per-file
               language detection - convenient for pasting into LLM chats
               and for rendering.
"""

from __future__ import annotations

from pathlib import Path

SEPARATOR = "=" * 80

# File extension -> Markdown code fence language identifier.
LANGUAGE_BY_EXTENSION = {
    '.py': 'python', '.pyi': 'python',
    '.js': 'javascript', '.jsx': 'jsx', '.mjs': 'javascript',
    '.ts': 'typescript', '.tsx': 'tsx',
    '.json': 'json', '.jsonc': 'jsonc',
    '.toml': 'toml', '.yaml': 'yaml', '.yml': 'yaml', '.ini': 'ini',
    '.cfg': 'ini', '.xml': 'xml', '.html': 'html', '.htm': 'html',
    '.css': 'css', '.scss': 'scss', '.less': 'less',
    '.md': 'markdown', '.markdown': 'markdown',
    '.sh': 'bash', '.bash': 'bash', '.zsh': 'bash',
    '.sql': 'sql', '.rs': 'rust', '.go': 'go',
    '.c': 'c', '.h': 'c', '.cpp': 'cpp', '.cc': 'cpp', '.hpp': 'cpp',
    '.cs': 'csharp', '.java': 'java', '.kt': 'kotlin', '.kts': 'kotlin',
    '.rb': 'ruby', '.php': 'php', '.swift': 'swift',
    '.r': 'r', '.lua': 'lua', '.pl': 'perl',
    '.dockerfile': 'dockerfile', '.makefile': 'makefile',
    '.txt': 'text', '.log': 'text', '.csv': 'csv',
}

_OUTPUT_FORMATS = ("text", "markdown")


def available_formats() -> tuple[str, ...]:
    """Returns the supported output format names."""
    return _OUTPUT_FORMATS


def detect_language(rel_path: str) -> str:
    """
    Detects a Markdown code-fence language for a file by its extension.

    :param rel_path: POSIX-style relative path of the file.
    :return: Language identifier, or '' when unknown.
    """
    suffix = Path(rel_path).suffix.lower()
    return LANGUAGE_BY_EXTENSION.get(suffix, "")


def _adaptive_fence(content: str) -> str:
    """
    Returns a backtick fence that is guaranteed to be longer than any run
    of backticks inside the content, so nested fences never break the block.
    """
    longest = 0
    run = 0
    for char in content:
        if char == "`":
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    return "`" * max(3, longest + 1)


def format_stats_lines(stats: dict) -> list[str]:
    """
    Renders the 'key: value' statistic lines shared by both formats.

    :param stats: Statistics dictionary (see pack_project).
    :return: List of formatted lines.
    """
    lines = [
        f"Project: {stats['project_name']}",
        f"Generated on: {stats['timestamp']}",
        f"Total files packed: {stats['packed_count']}",
    ]
    if stats["failed_count"] > 0:
        lines.append(f"Skipped files: {stats['failed_count']} (marked in the tree / see warnings)")
    lines.append(f"Total lines: {stats['total_lines']}")
    lines.append(f"Estimated tokens: ~{stats['estimated_tokens']} ({stats['token_method']})")
    return lines


def format_file_block(rel_path: str, content: str, output_format: str = "text") -> str:
    """
    Formats a single file's content block in the requested output format.

    :param rel_path: POSIX-style relative path used as the block label.
    :param content: Text content of the file.
    :param output_format: 'text' or 'markdown'.
    :return: The formatted block (without a trailing separator newline).
    """
    if output_format == "markdown":
        fence = _adaptive_fence(content)
        language = detect_language(rel_path)
        # Exactly one newline between the content and the closing fence.
        body = content if content.endswith("\n") else content + "\n"
        return f"### `{rel_path}`\n{fence}{language}\n{body}{fence}"

    return f"--- START OF FILE: {rel_path} ---\n{content}\n--- END OF FILE: {rel_path} ---"


def assemble_output(stats: dict, tree_text: str, content_blocks: list[str],
                    output_format: str = "text") -> str:
    """
    Assembles the complete output document.

    :param stats: Statistics dictionary (project_name, timestamp, counts...).
    :param tree_text: Rendered ASCII directory tree.
    :param content_blocks: Pre-formatted per-file blocks.
    :param output_format: 'text' or 'markdown'.
    :return: The full output text.
    """
    stats_lines = format_stats_lines(stats)

    if output_format == "markdown":
        tree_fence = _adaptive_fence(tree_text)
        header = "# Project Context Pack\n" + "\n".join(f"- {line}" for line in stats_lines)
        tree_section = f"## Directory Tree\n\n{tree_fence}text\n{tree_text}\n{tree_fence}"
        files_section = "## Files Content"
        return f"{header}\n\n{tree_section}\n\n{files_section}\n\n" + "\n\n".join(content_blocks) + "\n"

    header = f"{SEPARATOR}\n" + "\n".join(_header_text_lines(stats_lines)) + f"\n{SEPARATOR}\n"
    tree_section = f"{SEPARATOR}\nDIRECTORY TREE\n{SEPARATOR}\n{tree_text}\n"
    files_section_header = f"{SEPARATOR}\nFILES CONTENT\n{SEPARATOR}\n"
    return f"{header}\n{tree_section}\n{files_section_header}\n" + "\n\n".join(content_blocks) + "\n"


def _header_text_lines(stats_lines: list[str]) -> list[str]:
    """Converts stat lines into the classic plain-text header lines."""
    result = []
    for line in stats_lines:
        if line.startswith("Project:"):
            result.append(line.replace("Project:", "PROJECT CONTEXT PACK:", 1))
        else:
            result.append(line)
    return result
