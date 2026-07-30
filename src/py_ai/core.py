"""
core.py module
==============
Contains the core business logic for the py-ai utility:
- File and directory ignore checks (should_ignore).
- Project directory tree generation in ASCII format.
- Gathering allowed file contents and writing them to the final context file.
- Copying the generated output to the system clipboard.
"""

import os
import sys
from pathlib import Path
from datetime import datetime
import pyperclip

# Standard lists of exclusions for ignore checks
IGNORED_NAMES = {
    # Version control and system folders
    '.git', '.github', '.gitlab', '.svn', '.hg', 'node_modules',
    # Python runtime and caches
    '__pycache__', '.venv', 'venv', 'env', '.env', '.pytest_cache',
    '.mypy_cache', '.ruff_cache', '.tox', '.nox', '.egg-info', 'build', 'dist',
    # IDE and editor settings
    '.idea', '.vscode', '.settings',
    # OS system files
    '.DS_Store', 'Thumbs.db', 'desktop.ini'
}

IGNORED_EXTENSIONS = {
    # Compiled Python and binary artifacts
    '.pyc', '.pyo', '.pyd', '.class', '.o', '.obj', '.dll', '.so', '.dylib',
    # Archives/Compressed files
    '.zip', '.tar', '.gz', '.bz2', '.xz', '.rar', '.7z', '.tgz',
    # Images and multimedia
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp', '.tiff', '.svg',
    '.mp3', '.wav', '.ogg', '.flac', '.mp4', '.mkv', '.avi', '.mov', '.webm',
    # Fonts
    '.woff', '.woff2', '.ttf', '.eot', '.otf',
    # Databases and binary documents
    '.db', '.sqlite', '.sqlite3', '.pdf', '.epub',
    # Office documents
    '.docx', '.xlsx', '.pptx', '.doc', '.xls', '.ppt'
}


def should_ignore(path: Path, root_dir: Path) -> bool:
    """
    Checks if a file or directory should be ignored based on standard exclusions.

    :param path: Path to the file or folder to verify.
    :param root_dir: Root directory of the project.
    :return: True if the path should be ignored, False otherwise.
    """
    try:
        # Resolve to absolute paths to avoid issues with relative path operations
        abs_root = root_dir.resolve()
        abs_path = path.resolve()
        # Calculate path relative to the root directory
        rel_path = abs_path.relative_to(abs_root)
    except ValueError:
        # Fallback if the path is not under the root directory
        rel_path = path

    # Check each part of the relative path.
    # If any parent folder is in the ignored list, ignore the entire subtree.
    for part in rel_path.parts:
        if part in IGNORED_NAMES or part.lower() in IGNORED_NAMES:
            return True
        
        # Ignore any hidden folders/files (starting with a dot),
        # except allowed configuration files such as .gitignore or .env.example
        if part.startswith('.') and part not in ('.gitignore', '.env.example', '.env.template', '.pylintrc'):
            return True

    # Additional file-level checks for extensions and file names
    if path.is_file():
        if path.suffix.lower() in IGNORED_EXTENSIONS:
            return True
        if path.name.lower() in IGNORED_NAMES:
            return True

    return False


def build_tree_lines(path: Path, root_dir: Path, prefix: str = "", is_last: bool = True, is_root: bool = False) -> list[str]:
    """
    Recursively generates the ASCII project tree, skipping ignored files and folders.

    :param path: Current path (file or folder).
    :param root_dir: Root directory of the project (for should_ignore checks).
    :param prefix: Prefix for the current line (indentation and connection symbols).
    :param is_last: Whether the current item is the last one in its parent directory.
    :param is_root: Whether the current item is the root folder of the project.
    :return: List of strings forming the ASCII tree.
    """
    lines = []
    
    # Root directory displays with its name and a trailing slash
    if is_root:
        lines.append(f"{path.name}/")
    else:
        connector = "└── " if is_last else "├── "
        display_name = path.name + ("/" if path.is_dir() else "")
        lines.append(f"{prefix}{connector}{display_name}")

    if path.is_dir():
        try:
            # List directory items, sort them: directories first, then files (case-insensitive)
            # Filter out any ignored items immediately
            items = sorted(
                [item for item in path.iterdir() if not should_ignore(item, root_dir)],
                key=lambda x: (not x.is_dir(), x.name.lower())
            )
        except OSError as e:
            # Handle permission errors or system issues gracefully in the tree
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}[Permission denied/Error accessing directory: {e}]")
            return lines

        for i, item in enumerate(items):
            item_is_last = (i == len(items) - 1)
            # Calculate next indentation prefix for child elements
            if is_root:
                next_prefix = ""
            else:
                next_prefix = prefix + ("    " if is_last else "│   ")
            
            lines.extend(build_tree_lines(item, root_dir, next_prefix, item_is_last, is_root=False))

    return lines


def pack_project(root_dir: str | Path, output_file: str | Path, copy_to_clipboard: bool = True) -> dict:
    """
    Recursively scans the project, builds an ASCII tree, gathers all text file contents,
    saves the aggregated output to a single file, and copies it to the system clipboard.

    :param root_dir: Path to the root folder of the project.
    :param output_file: Path to the target output text file.
    :param copy_to_clipboard: Whether to copy the generated context to the clipboard.
    :return: Dictionary containing execution statistics.
    """
    root_path = Path(root_dir).resolve()
    output_path = Path(output_file).resolve()

    if not root_path.exists() or not root_path.is_dir():
        raise FileNotFoundError(f"The specified directory '{root_path}' does not exist or is not a directory.")

    # 1. Generate the ASCII directory tree
    tree_lines = build_tree_lines(root_path, root_path, is_root=True)
    tree_text = "\n".join(tree_lines)

    # 2. Collect all allowed files for code packing
    files_to_pack = []

    def recursive_walk(current_dir: Path):
        try:
            # Sort items for a deterministic walking order
            items = sorted(current_dir.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except PermissionError as e:
            print(f"Warning: Permission denied reading directory {current_dir}: {e}", file=sys.stderr)
            return

        for item in items:
            if should_ignore(item, root_path):
                continue
            if item.is_dir():
                recursive_walk(item)
            elif item.is_file():
                # Avoid packing the output file itself if it is located inside the root project directory
                if item.resolve() == output_path:
                    continue
                files_to_pack.append(item)

    recursive_walk(root_path)

    # 3. Read file contents and format blocks
    content_blocks = []
    packed_count = 0
    failed_count = 0

    for file_path in files_to_pack:
        try:
            rel_path = file_path.relative_to(root_path).as_posix()
        except ValueError:
            rel_path = file_path.as_posix() if hasattr(file_path, "as_posix") else str(file_path)

        try:
            # Read files using UTF-8 encoding
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Format the code block with clean delimiters
            block = f"--- START OF FILE: {rel_path} ---\n{content}\n--- END OF FILE: {rel_path} ---"
            content_blocks.append(block)
            packed_count += 1
        except UnicodeDecodeError:
            # Handle binary files that cannot be decoded as standard text
            print(f"Warning: Skipped '{rel_path}' due to encoding error (likely a binary file).", file=sys.stderr)
            failed_count += 1
        except PermissionError:
            print(f"Warning: Skipped '{rel_path}' due to permission error.", file=sys.stderr)
            failed_count += 1
        except Exception as e:
            print(f"Warning: Skipped '{rel_path}' due to an error: {e}", file=sys.stderr)
            failed_count += 1

    # 4. Formulate the single aggregated output
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    header = (
        "================================================================================\n"
        f"PROJECT CONTEXT PACK: {root_path.name}\n"
        f"Generated on: {timestamp}\n"
        f"Total files packed: {packed_count}\n"
        "================================================================================\n"
    )

    tree_section = (
        "================================================================================\n"
        "DIRECTORY TREE\n"
        "================================================================================\n"
        f"{tree_text}\n"
    )

    files_section_header = (
        "================================================================================\n"
        "FILES CONTENT\n"
        "================================================================================\n"
    )

    files_content = "\n\n".join(content_blocks)
    full_output = f"{header}\n{tree_section}\n{files_section_header}\n{files_content}\n"

    # 5. Write to the output file
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_output)
    except Exception as e:
        raise IOError(f"Failed to write results to '{output_path}': {e}")

    # 6. Copy to the system clipboard if enabled
    clipboard_copied = False
    clipboard_error = None

    if copy_to_clipboard:
        try:
            pyperclip.copy(full_output)
            clipboard_copied = True
        except Exception as e:
            clipboard_error = str(e)
            print(f"Warning: Could not copy to clipboard: {e}", file=sys.stderr)

    return {
        "root_dir": str(root_path),
        "output_file": str(output_path),
        "packed_count": packed_count,
        "failed_count": failed_count,
        "clipboard_copied": clipboard_copied,
        "clipboard_error": clipboard_error,
        "file_size": len(full_output)
    }
