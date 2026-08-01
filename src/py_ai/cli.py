"""
cli.py module
=============
Command-line interface (CLI) for the py-ai utility using the built-in argparse.
Provides user interaction, argument parsing, and triggers the packing logic.
"""

import argparse
import os
import re
import sys
from pathlib import Path

from py_ai import __version__
from py_ai.core import _format_bytes, pack_project
from py_ai.formatting import available_formats

_SIZE_SUFFIXES = {
    "B": 1,
    "KB": 1024,
    "MB": 1024 ** 2,
    "GB": 1024 ** 3,
}


def parse_size(value: str) -> int:
    """
    Parses a human-friendly size like '512KB', '10MB' or '1048576'
    into a number of bytes. Raises ValueError on invalid input.
    """
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(B|KB|MB|GB)?\s*", value.strip(), re.IGNORECASE)
    if not match:
        raise ValueError(f"invalid size value: '{value}' (examples: 512KB, 10MB, 1048576)")
    number = float(match.group(1))
    suffix = (match.group(2) or "B").upper()
    result = int(number * _SIZE_SUFFIXES[suffix])
    if result <= 0:
        raise ValueError(f"size must be greater than zero: '{value}'")
    return result


def _program_name() -> str:
    """Returns the program name to display, based on how the tool was invoked.

    Both console scripts ('pyai' and 'py-ai') point to the same entry point,
    so the name must be derived from argv[0] instead of being hardcoded.
    """
    argv0 = os.path.basename(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    if argv0.startswith("py-ai"):
        return "py-ai"
    if argv0.startswith("pyai"):
        return "pyai"
    return "pyai"

def _enable_unicode_output() -> None:
    """Prevent crashes when stdout/stderr are attached to pipes that use
    legacy code pages (Windows consoles use cp125x for redirected output).
    Unencodable glyphs (emoji) degrade to '?' instead of raising
    UnicodeEncodeError."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # Python >= 3.7
        except (AttributeError, ValueError, OSError):
            pass  # non-standard streams (e.g. test capture, odd embedders)

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_program_name(),
        description="py-ai: pack your project's codebase into a single text (or Markdown) file "
                    "and copy it to the clipboard for LLM context."
    )

    parser.add_argument(
        "root_dir",
        nargs="?",
        default=".",
        help="Path to the project directory to pack (default: current directory '.')"
    )

    parser.add_argument(
        "-o", "--output",
        default="ai_context.txt",
        help="Name or path of the output file (default: 'ai_context.txt')"
    )

    parser.add_argument(
        "--no-clipboard",
        action="store_true",
        help="Disable automatic copying of the generated context to the system clipboard "
             "(useful for headless servers or CI/CD pipelines)."
    )

    parser.add_argument(
        "--format",
        choices=available_formats(),
        default="text",
        dest="output_format",
        help="Output format: 'text' (classic file markers) or 'markdown' "
             "(fenced code blocks with language detection). Default: text."
    )

    parser.add_argument(
        "--max-file-size",
        metavar="SIZE",
        default=None,
        help="Skip files larger than SIZE (e.g. 512KB, 10MB). Skipped files are "
             "listed with a warning and marked in the directory tree."
    )

    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="Glob pattern(s) to exclude additionally (e.g. '*.log', 'docs/*'). "
             "Can be passed multiple times."
    )

    parser.add_argument(
        "--no-gitignore",
        action="store_true",
        help="Do not honor .pyaiignore/.gitignore files even when the optional "
             "'pathspec' dependency (py-for-ai[gitignore]) is installed."
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}"
    )

    return parser


def main():
    """
    Main entry point for the command-line interface. Parses CLI arguments,
    starts the project packaging process, and prints results to the console.
    """
    _enable_unicode_output()
    parser = _build_parser()
    args = parser.parse_args()

    root_path = Path(args.root_dir)
    output_path = Path(args.output)

    max_file_size = None
    if args.max_file_size is not None:
        try:
            max_file_size = parse_size(args.max_file_size)
        except ValueError as e:
            print(f"❌ Error: {e}", file=sys.stderr)
            sys.exit(2)

    try:
        resolved_root = root_path.resolve()
    except OSError:
        resolved_root = root_path.absolute()
    print(f"🔍 Scanning project directory: {resolved_root}")

    try:
        # Trigger the core packing logic
        stats = pack_project(
            root_dir=root_path,
            output_file=output_path,
            copy_to_clipboard=not args.no_clipboard,
            max_file_size=max_file_size,
            output_format=args.output_format,
            exclude_patterns=args.exclude,
            respect_gitignore=not args.no_gitignore,
        )

        print("\n✨ Project successfully packed!")
        print(f"📁 Root Directory:   {stats['root_dir']}")
        print(f"📄 Output File:      {stats['output_file']}")
        print(f"🧾 Output Format:    {stats['output_format']}")
        print(f"💾 Output Size:      {_format_bytes(stats.get('file_size', 0))}")
        print(f"📦 Packed Files:     {stats['packed_count']}")
        print(f"📏 Total Lines:      {stats['total_lines']}")
        print(f"🪙 Estimated Tokens: ~{stats['estimated_tokens']} ({stats['token_method']})")

        if stats['failed_count'] > 0:
            print(f"⚠️  Skipped Files:    {stats['failed_count']} (see warning messages above; they are marked '[skipped: ...]' in the directory tree)")

        if stats['clipboard_copied']:
            print("📋 Project context copied to clipboard successfully!")
        else:
            if args.no_clipboard:
                print("ℹ️  Clipboard copying was disabled by the --no-clipboard flag.")
            else:
                print(
                    f"⚠️  Could not copy to clipboard.\n"
                    f"   Details: {stats['clipboard_error'] or 'Unknown error'}.\n"
                    f"   The output was still saved successfully to the output file."
                )

    except FileNotFoundError as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print(f"❌ Write Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"❌ Unexpected Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
