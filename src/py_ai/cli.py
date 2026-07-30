"""
cli.py module
=============
Command-line interface (CLI) for the py-ai utility using the built-in argparse.
Provides user interaction, argument parsing, and triggers the packing logic.
"""

import argparse
import sys
from pathlib import Path
from py_ai.core import pack_project


def main():
    """
    Main entry point for the command-line interface. Parses CLI arguments,
    starts the project packaging process, and prints results to the console.
    """
    parser = argparse.ArgumentParser(
        description="py-ai: A command-line utility to pack your project's codebase into a single text file and copy it to the clipboard for LLM context."
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
        help="Disable automatic copying of the generated context to the system clipboard (useful for headless servers or CI/CD pipelines)."
    )

    args = parser.parse_args()

    root_path = Path(args.root_dir)
    output_path = Path(args.output)

    print(f"🔍 Scanning project directory: {root_path.resolve()}")

    try:
        # Trigger the core packing logic
        stats = pack_project(
            root_dir=root_path,
            output_file=output_path,
            copy_to_clipboard=not args.no_clipboard
        )

        print("\n✨ Project successfully packed!")
        print(f"📁 Root Directory:   {stats['root_dir']}")
        print(f"📄 Output File:      {stats['output_file']}")
        print(f"📦 Packed Files:     {stats['packed_count']}")

        if stats['failed_count'] > 0:
            print(f"⚠️  Skipped Files:    {stats['failed_count']} (see warning messages above)")

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
    except Exception as e:
        print(f"❌ Unexpected Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
