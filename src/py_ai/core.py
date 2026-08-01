"""
core.py module
==============
Core orchestration logic for the py-ai utility:
- Project directory tree generation in ASCII format (build_tree_lines).
- Gathering allowed file contents and writing them to the final context file.
- Copying the generated output to the system clipboard.

Design notes
------------
- Traversal (walker and tree builder) is ITERATIVE (explicit stack), so
  extremely deep projects do not hit Python's recursion limit. Files are
  collected in the same deterministic order as the classic recursive DFS:
  for every directory - subdirectories (with their subtrees) first, then
  files, all sorted case-insensitively.
- Symlinks resolving outside of the project root are never followed or
  packed (see filters.py); cycles/duplicates are traversed once.
- Backwards compatibility: the public names 'should_ignore',
  'IGNORED_NAMES', 'IGNORED_EXTENSIONS', 'ALLOWED_HIDDEN_FILES',
  'read_text_content', 'build_tree_lines' and 'pack_project' remain
  available from 'py_ai.core'.
"""

# PEP 563: postpone evaluation of annotations. Keeps `str | Path` (PEP 604)
# and builtin-generic annotations importable on Python 3.8 and 3.9.
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import pyperclip

from py_ai.filters import (
    ALLOWED_HIDDEN_FILES,
    IGNORED_EXTENSIONS,
    IGNORED_NAMES,
    _is_outside_root,
    load_ignore_matcher,
    make_filter,
    should_ignore,
)
from py_ai.formatting import assemble_output, available_formats, format_file_block
from py_ai.readers import read_text_content
from py_ai.tokens import count_lines, count_tokens

# Internal sentinel used in the tree stack for directory symlinks; the final
# human-readable note is chosen when the entry is popped and rendered.
_DIR_SYMLINK_MARKER = "__pyai_dir_symlink__"

# Default output file names that must never be packed, even when they exist
# in the project from a previous run with a different output path.
_DEFAULT_OUTPUT_NAMES = {"ai_context.txt"}

__all__ = [
    "ALLOWED_HIDDEN_FILES",
    "IGNORED_EXTENSIONS",
    "IGNORED_NAMES",
    "build_tree_lines",
    "pack_project",
    "read_text_content",
    "should_ignore",
]


def _is_same_path(first: Path, second: Path) -> bool:
    """
    Safely compares two paths by their resolved location. Never raises,
    even for broken symlinks or non-existent paths.
    """
    try:
        return first.resolve() == second.resolve()
    except OSError:
        return os.path.abspath(first) == os.path.abspath(second)


def _link_suffix(path: Path) -> str:
    """Returns a ' -> target' suffix for symlinks, or an empty string."""
    if path.is_symlink():
        try:
            return f" -> {os.readlink(path)}"
        except OSError:
            return " -> <unreadable link>"
    return ""


def _dir_identity(path: Path):
    """
    Returns a stable identity key for a directory (used to detect duplicate
    traversal / cycles), or None when it cannot be determined.

    Prefers the ``(st_dev, st_ino)`` pair, but falls back to the resolved
    absolute path on filesystems where inodes are unreliable (e.g. ``st_ino``
    is 0 or repeated on some network/FUSE mounts). Relying on inodes alone
    caused *silent* loss of whole subtrees there: every directory after the
    first was treated as a duplicate and skipped.
    """
    try:
        st = path.stat()
    except OSError:
        return None
    if st.st_dev and st.st_ino:
        return ("inode", st.st_dev, st.st_ino)
    try:
        return ("path", os.path.normcase(os.path.realpath(os.fspath(path))))
    except OSError:
        return None


def build_tree_lines(path: Path, root_dir: Path, prefix: str = "", is_last: bool = True,
                     is_root: bool = False, exclude_path: Path | None = None,
                     skipped_files: dict[Path, str] | None = None,
                     ignore_predicate=None) -> list[str]:
    """
    Generates the ASCII project tree, skipping ignored files and folders.

    The traversal is ITERATIVE (explicit stack), so arbitrarily deep projects
    do not raise RecursionError. Symlink cycles/duplicates are visited once
    and marked instead of exploding the tree.

    :param path: Path of the root folder to render.
    :param root_dir: Root directory of the project (for filtering checks).
    :param prefix: Prefix for the current line (indentation/connection symbols).
    :param is_last: Whether the current item is the last one in its parent directory.
    :param is_root: Whether the current item is the root folder of the project.
    :param exclude_path: Optional path (e.g. the output file) that must not
                         appear in the tree.
    :param skipped_files: Optional mapping of {file path: reason}. Such files
                          are shown in the tree with a "[skipped: ...]" note so
                          the tree stays consistent with the FILES CONTENT section.
    :param ignore_predicate: Optional callable(Path) -> bool (built-ins only
                             when omitted; use make_filter() to extend).
    :return: List of strings forming the ASCII tree.
    """
    if ignore_predicate is None:
        ignore_predicate = make_filter(root_dir)

    lines: list[str] = []
    # Keys come from _dir_identity(): either ("inode", st_dev, st_ino) or
    # ("path", resolved) — a plain tuple is the accurate common type.
    visited_dirs: set[tuple] = set()

    exclude_resolved = None
    if exclude_path is not None:
        try:
            exclude_resolved = exclude_path.resolve()
        except OSError:
            exclude_resolved = Path(os.path.abspath(exclude_path))

    # Stack entries: (path, prefix, is_last, is_root, marker)
    # marker, when set, is appended to the item's line and the item's
    # children are never traversed (used for unsafe/outside-root symlinks).
    stack: list[tuple[Path, str, bool, bool, str | None]] = [
        (path, prefix, is_last, is_root, None)
    ]

    while stack:
        current, cur_prefix, cur_is_last, cur_is_root, marker = stack.pop()

        # Resolve the deferred marker for directory symlinks: known-visited
        # targets are cycles/duplicates, the rest are simply not followed.
        if marker == _DIR_SYMLINK_MARKER:
            link_key = _dir_identity(current)
            if link_key is not None and link_key in visited_dirs:
                marker = "cyclic or duplicate link — already traversed, not followed"
            else:
                marker = "directory symlink — not followed"

        if cur_is_root:
            lines.append(f"{current.name}/")
        else:
            connector = "└── " if cur_is_last else "├── "
            is_directory = current.is_dir() if marker is None else False
            display_name = current.name + ("/" if is_directory else "")
            display_name += _link_suffix(current)
            note = ""
            if marker is not None:
                note = f"  [{marker}]"
            elif not is_directory and skipped_files and current in skipped_files:
                note = f"  [skipped: {skipped_files[current]}]"
            lines.append(f"{cur_prefix}{connector}{display_name}{note}")

        if marker is not None:
            # Explicitly blocked item: shown for visibility, never traversed.
            continue

        if current.is_dir():
            # Cycle/duplicate detection: track directories by a reliable
            # identity (inode when available, resolved path otherwise).
            dir_key = _dir_identity(current)

            child_prefix = "" if cur_is_root else cur_prefix + ("    " if cur_is_last else "│   ")

            if dir_key is not None:
                if dir_key in visited_dirs:
                    lines.append(f"{child_prefix}└── [cyclic or duplicate link — already traversed, not followed]")
                    continue
                visited_dirs.add(dir_key)

            try:
                # List directory items, sort them: directories first, then
                # files (case-insensitive). Ignored items are filtered out.
                entries: list[tuple[Path, str | None]] = []
                for item in current.iterdir():
                    if _is_outside_root(item, root_dir):
                        # Kept visible in the tree, but never followed or packed.
                        entries.append((item, "symlink outside project root — not followed, not packed"))
                        continue
                    if ignore_predicate(item):
                        continue
                    if exclude_resolved is not None and _is_same_path(item, exclude_resolved):
                        # The output file itself must never appear in its own pack.
                        continue
                    if item.parent == root_dir and item.name in _DEFAULT_OUTPUT_NAMES:
                        # A leftover pack from a previous run that used the
                        # default output name at the project root. Nested files
                        # with the same name are legitimate and stay packed.
                        continue
                    if item.is_dir() and item.is_symlink():
                        # Directory symlinks are visible in the tree but are
                        # never traversed (see _collect_files). The final note
                        # is decided when the entry is popped, based on whether
                        # its target directory has already been traversed.
                        entries.append((item, _DIR_SYMLINK_MARKER))
                        continue
                    entries.append((item, None))
                entries.sort(key=lambda entry: (not entry[0].is_dir() if entry[1] is None else True,
                                                entry[0].name.lower()))
            except OSError as e:
                # Report permission errors or system issues as a child note of
                # the directory instead of duplicating the directory entry.
                reason = e.strerror or str(e)
                lines.append(f"{child_prefix}└── [Cannot access directory: {reason}]")
                continue

            # Push children in reverse order so they are processed (LIFO)
            # in the original sorted order.
            for i in range(len(entries) - 1, -1, -1):
                item, item_marker = entries[i]
                item_is_last = (i == len(entries) - 1)
                stack.append((item, child_prefix, item_is_last, False, item_marker))

    return lines


def _collect_files(root_path: Path, output_path: Path, ignore_predicate) -> list[Path]:
    """
    Collects all files to pack using an ITERATIVE depth-first traversal.

    The work stack holds both files and directories, which reproduces exactly
    the classic recursive DFS order: for each directory its subdirectories
    (with complete subtrees) come first, then its files, everything sorted
    case-insensitively.

    :param root_path: Root directory (resolved).
    :param output_path: Output file to exclude from packing.
    :param ignore_predicate: Callable(Path) -> bool.
    :return: Ordered list of file paths to pack.
    """
    files_to_pack: list[Path] = []
    # Keys come from _dir_identity(): either ("inode", st_dev, st_ino) or
    # ("path", resolved) — a plain tuple is the accurate common type.
    visited_dirs: set[tuple] = set()
    work_stack: list[Path] = [root_path]

    while work_stack:
        node = work_stack.pop()

        if node.is_dir():
            dir_key = _dir_identity(node)
            if dir_key is None:
                continue
            if dir_key in visited_dirs:
                # Symlink cycle or duplicate directory link.
                continue
            visited_dirs.add(dir_key)

            try:
                # Sort items for a deterministic walking order:
                # directories first, then files, both case-insensitive.
                items = sorted(node.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            except PermissionError as e:
                print(f"Warning: Permission denied reading directory {node}: {e}", file=sys.stderr)
                continue
            except OSError as e:
                # ELOOP, I/O errors and friends: warn and keep going.
                print(f"Warning: Could not read directory {node}: {e}", file=sys.stderr)
                continue

            # Push in reverse order so the sorted DFS order is preserved
            # when popping (both subdirectories and files go through the
            # same work stack).
            for item in reversed(items):
                if ignore_predicate(item):
                    continue
                if item.is_dir() and item.is_symlink():
                    # Directory symlinks are NEVER followed for packing:
                    # files are only collected through their real paths, so
                    # no aliased paths and no cycles can occur. The symlink
                    # stays visible in the directory tree (see build_tree_lines).
                    continue
                work_stack.append(item)

        elif node.is_file():
            # Avoid packing the output file itself. A leftover pack from a
            # previous run that used the default output name at the project
            # root is excluded too; nested files with that name are legitimate.
            if _is_same_path(node, output_path):
                continue
            if node.parent == root_path and node.name in _DEFAULT_OUTPUT_NAMES:
                continue
            files_to_pack.append(node)

    return files_to_pack


def pack_project(root_dir: str | Path, output_file: str | Path, copy_to_clipboard: bool = True,
                 *, max_file_size: int | None = None, output_format: str = "text",
                 exclude_patterns=None, respect_gitignore: bool = True,
                 include_tree: bool = True, enable_token_count: bool = True) -> dict:
    """
    Recursively scans the project, builds an ASCII tree, gathers all text file
    contents, saves the aggregated output to a single file and (optionally)
    copies it to the system clipboard.

    :param root_dir: Path to the root folder of the project.
    :param output_file: Path to the target output text file.
    :param copy_to_clipboard: Whether to copy the generated context to the clipboard.
    :param max_file_size: Optional maximum file size in bytes; larger files
                          are skipped with a warning and marked in the tree.
    :param output_format: 'text' (classic markers) or 'markdown' (fenced blocks).
    :param exclude_patterns: Optional iterable of glob patterns (--exclude),
                             matched against the relative POSIX path and the file name.
    :param respect_gitignore: Honor .pyaiignore/.gitignore files when the
                              optional 'pathspec' dependency is installed.
    :param include_tree: When False, the directory tree is omitted from the output.
    :param enable_token_count: When False, token estimation is skipped (faster
                               on large projects); token_method becomes 'disabled'.
    :return: Dictionary with execution statistics (file counts, size, lines,
             estimated tokens, clipboard status, ...).
    """
    if output_format not in available_formats():
        raise ValueError(
            f"Unsupported output format '{output_format}'. "
            f"Available formats: {', '.join(available_formats())}."
        )

    root_path = Path(root_dir).resolve()
    output_path = Path(output_file).resolve()

    if not root_path.exists() or not root_path.is_dir():
        raise FileNotFoundError(f"The specified directory '{root_path}' does not exist or is not a directory.")

    matcher = load_ignore_matcher(root_path) if respect_gitignore else None
    ignore_predicate = make_filter(root_path, patterns=exclude_patterns or (), matcher=matcher)

    # 1. Collect all files allowed for packing (iterative, cycle-safe,
    #    deterministic DFS order).
    files_to_pack = _collect_files(root_path, output_path, ignore_predicate)

    # 2. Read file contents and format blocks
    content_blocks: list[str] = []
    skipped_files: dict[Path, str] = {}
    total_source_lines = 0

    for file_path in files_to_pack:
        try:
            rel_path = file_path.relative_to(root_path).as_posix()
        except ValueError:
            rel_path = file_path.as_posix() if hasattr(file_path, "as_posix") else str(file_path)

        # Optional per-file size limit.
        if max_file_size is not None:
            try:
                file_size = file_path.stat().st_size
            except OSError:
                file_size = 0
            if file_size > max_file_size:
                reason = f"file exceeds size limit ({_format_bytes(file_size)} > {_format_bytes(max_file_size)})"
                print(f"Warning: Skipped '{rel_path}' ({reason}).", file=sys.stderr)
                skipped_files[file_path] = f"exceeds size limit ({_format_bytes(max_file_size)})"
                continue

        content, error_reason, encoding = read_text_content(file_path)

        if content is None:
            # Unreadable/undecodable/binary files are skipped gracefully.
            print(f"Warning: Skipped '{rel_path}' ({error_reason}).", file=sys.stderr)
            skipped_files[file_path] = error_reason
            continue

        # Be transparent about transcoding: a non-UTF-8 source file is
        # converted to UTF-8 in the pack, which may surprise the user.
        if encoding is not None and not encoding.startswith("utf-8"):
            print(f"Note: '{rel_path}' was read as {encoding} and transcoded to UTF-8.", file=sys.stderr)

        total_source_lines += count_lines(content)
        content_blocks.append(format_file_block(rel_path, content, output_format))

    packed_count = len(content_blocks)
    failed_count = len(skipped_files)

    # 3. Generate the ASCII directory tree (AFTER reading files, so entries
    #    that failed to read can be visibly marked).
    tree_text = ""
    if include_tree:
        tree_lines = build_tree_lines(
            root_path,
            root_path,
            is_root=True,
            exclude_path=output_path,
            skipped_files=skipped_files,
            ignore_predicate=ignore_predicate,
        )
        tree_text = "\n".join(tree_lines)

    # 4. Assemble the complete output document and compute statistics.
    #    Token statistics are computed over the final document, so they
    #    describe exactly what would be pasted into the LLM.
    stats = {
        "project_name": root_path.name,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "packed_count": packed_count,
        "failed_count": failed_count,
        "total_lines": 0,
        "estimated_tokens": 0,
        "token_method": "",
    }

    full_output = assemble_output(stats, tree_text, content_blocks, output_format,
                                  include_tree=include_tree)

    stats["total_lines"] = count_lines(full_output)
    if enable_token_count:
        estimated_tokens, token_method = count_tokens(full_output)
    else:
        estimated_tokens, token_method = 0, "disabled"
    stats["estimated_tokens"] = estimated_tokens
    stats["token_method"] = token_method

    # Re-assemble once with the final statistics embedded in the header.
    full_output = assemble_output(stats, tree_text, content_blocks, output_format,
                                  include_tree=include_tree)

    # 5. Write to the output file
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            f.write(full_output)
    except Exception as e:
        raise OSError(f"Failed to write results to '{output_path}': {e}")

    # Report the REAL on-disk size in bytes (len() counts characters, which
    # understates the size of non-ASCII content, e.g. Cyrillic in UTF-8).
    try:
        disk_size = output_path.stat().st_size
    except OSError:
        disk_size = len(full_output.encode("utf-8"))

    # 6. Copy to the system clipboard if enabled. Any failure is reported to
    #    the caller through the returned statistics (the CLI renders the
    #    warning exactly once) instead of printing here.
    clipboard_copied = False
    clipboard_error = None

    if copy_to_clipboard:
        try:
            pyperclip.copy(full_output)
            clipboard_copied = True
        except Exception as e:
            clipboard_error = str(e)

    return {
        "root_dir": str(root_path),
        "output_file": str(output_path),
        "packed_count": packed_count,
        "failed_count": failed_count,
        "clipboard_copied": clipboard_copied,
        "clipboard_error": clipboard_error,
        "file_size": disk_size,
        "total_lines": stats["total_lines"],
        "total_source_lines": total_source_lines,
        "estimated_tokens": estimated_tokens,
        "token_method": token_method,
        "output_format": output_format,
        "include_tree": include_tree,
    }


def _format_bytes(num_bytes: int) -> str:
    """Formats a byte count as a short human-readable string."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 ** 2:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 ** 2):.2f} MB"
