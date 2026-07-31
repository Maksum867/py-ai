"""
filters.py module
=================
Filtering logic for the py-ai utility:

- Built-in ignore rules (should_ignore): VCS folders, caches, build
  artifacts, binary extensions, hidden files (with an allowlist).
- Security rule: anything resolving outside of the project root (symlinks)
  is always ignored.
- User-provided glob exclude patterns (--exclude).
- Optional support for .gitignore / .pyaiignore files when the 'pathspec'
  package is installed (extra: pip install py-for-ai[gitignore]).
"""

from __future__ import annotations

import fnmatch
import os
import sys
from pathlib import Path

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
    '.a', '.lib', '.exe', '.msi', '.apk', '.dmg', '.iso', '.img', '.bin',
    '.dat', '.wasm',
    # Archives/Compressed files
    '.zip', '.tar', '.gz', '.bz2', '.xz', '.rar', '.7z', '.tgz', '.jar',
    '.war', '.ear',
    # Images and multimedia
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp', '.tiff', '.svg',
    '.mp3', '.wav', '.ogg', '.flac', '.mp4', '.mkv', '.avi', '.mov', '.webm',
    # Fonts
    '.woff', '.woff2', '.ttf', '.eot', '.otf',
    # Databases, binary documents and ML artifacts
    '.db', '.sqlite', '.sqlite3', '.pdf', '.epub', '.pkl', '.pickle',
    '.joblib', '.npy', '.npz', '.parquet', '.onnx', '.pt', '.h5', '.hdf5',
    # Office documents
    '.docx', '.xlsx', '.pptx', '.doc', '.xls', '.ppt'
}

# Hidden files (starting with a dot) are ignored by default, EXCEPT these
# explicitly allowed, commonly useful configuration files.
# Stored lowercase; the comparison in should_ignore() is case-insensitive.
ALLOWED_HIDDEN_FILES = {
    '.gitignore', '.gitattributes', '.gitmodules',
    '.env.example', '.env.template',
    '.pylintrc', '.flake8', '.coveragerc',
    '.dockerignore', '.editorconfig',
    '.pre-commit-config.yaml', '.python-version',
    '.readthedocs.yaml', '.readthedocs.yml', '.codecov.yml',
}

# Names of ignore files honored when the optional 'pathspec' dependency
# is installed, in priority order.
IGNORE_FILE_NAMES = ('.pyaiignore', '.gitignore')


def _is_outside_root(path: Path, root_dir: Path) -> bool:
    """
    Checks whether the fully-resolved path escapes the project root.

    :param path: Path to check.
    :param root_dir: Root directory of the project.
    :return: True if the resolved path points outside the root directory
             (only possible through symlinks) or cannot be resolved at all.
    """
    try:
        path.resolve().relative_to(root_dir.resolve())
        return False
    except (ValueError, OSError):
        # ValueError: not a subpath of the root.
        # OSError: unresolvable (e.g. too many symlink levels, ELOOP).
        return True


def should_ignore(path: Path, root_dir: Path) -> bool:
    """
    Checks if a file or directory should be ignored based on the built-in
    exclusion rules.

    Anything resolving outside of the project root (e.g. a symlink pointing to
    /etc or $HOME) is always ignored, so files outside the packed project can
    never leak into the generated context.

    :param path: Path to the file or folder to verify.
    :param root_dir: Root directory of the project.
    :return: True if the path should be ignored, False otherwise.
    """
    try:
        # Resolve to absolute paths to avoid issues with relative path operations
        abs_root = root_dir.resolve()
        abs_path = path.resolve()
    except OSError:
        # Unresolvable path (dangling symlink chain, ELOOP, etc.): play safe.
        return True

    try:
        # Calculate path relative to the root directory
        rel_path = abs_path.relative_to(abs_root)
    except ValueError:
        # The path (typically via a symlink) points outside of the project
        # root. Ignore it so external files are never packed.
        return True

    # Check each part of the relative path.
    # If any parent folder is in the ignored list, ignore the entire subtree.
    for part in rel_path.parts:
        lowered = part.lower()
        if lowered in IGNORED_NAMES:
            return True

        # Python packaging artifacts are named "<pkg>.egg-info", not ".egg-info"
        if lowered.endswith('.egg-info'):
            return True

        # Ignore any hidden folders/files (starting with a dot),
        # except explicitly allowed configuration files such as
        # .gitignore, .env.example or .editorconfig
        if part.startswith('.') and lowered not in ALLOWED_HIDDEN_FILES:
            return True

    # Additional file-level checks for extensions and file names
    if path.is_file():
        if path.suffix.lower() in IGNORED_EXTENSIONS:
            return True
        if path.name.lower() in IGNORED_NAMES:
            return True

    return False


def load_ignore_matcher(root_dir: Path):
    """
    Loads '.pyaiignore' and/or '.gitignore' files located at the project root
    into a single matcher, when the optional 'pathspec' package is available.

    :param root_dir: Root directory of the project.
    :return: A 'pathspec.PathSpec' matcher, or None when the dependency is
             missing or no ignore files exist.
    """
    found_files = [root_dir / name for name in IGNORE_FILE_NAMES if (root_dir / name).is_file()]
    if not found_files:
        return None

    try:
        import pathspec
    except ImportError:
        names = ", ".join(f.name for f in found_files)
        print(
            f"Note: ignore file(s) ({names}) found, but the optional 'pathspec' package is not "
            f"installed. Install it with 'pip install py-for-ai[gitignore]' to respect them.",
            file=sys.stderr,
        )
        return None

    matcher = None
    for ignore_file in found_files:
        try:
            lines = ignore_file.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        except OSError as e:
            print(f"Warning: could not read '{ignore_file}': {e}", file=sys.stderr)
            continue
        # pathspec >= 0.12 renamed the 'gitwildmatch' factory to 'gitignore';
        # fall back to the legacy name for older versions.
        try:
            spec = pathspec.PathSpec.from_lines("gitignore", lines)
        except Exception:
            spec = pathspec.PathSpec.from_lines("gitwildmatch", lines)
        matcher = spec if matcher is None else matcher + spec

    return matcher


def matches_user_patterns(path: Path, root_dir: Path, patterns) -> bool:
    """
    Checks a path against user-provided glob patterns (--exclude).
    Patterns are matched (fnmatch) against the POSIX relative path and
    against the bare file name, so both 'docs/*' and '*.log' work.

    :param path: Path to check.
    :param root_dir: Root directory of the project.
    :param patterns: Iterable of glob patterns.
    :return: True if any pattern matches.
    """
    if not patterns:
        return False
    try:
        rel_posix = path.relative_to(root_dir).as_posix()
    except ValueError:
        rel_posix = path.as_posix()
    name = path.name
    for pattern in patterns:
        if fnmatch.fnmatch(rel_posix, pattern) or fnmatch.fnmatch(name, pattern):
            return True
    return False


def matches_ignore_files(path: Path, root_dir: Path, matcher) -> bool:
    """
    Checks a path against the .gitignore/.pyaiignore matcher (if loaded).

    :param path: Path to check.
    :param root_dir: Root directory of the project.
    :param matcher: A pathspec.PathSpec instance or None.
    :return: True if the matcher ignores the path.
    """
    if matcher is None:
        return False
    try:
        rel_posix = path.relative_to(root_dir).as_posix()
    except ValueError:
        return False
    if matcher.match_file(rel_posix):
        return True
    # Directory patterns like 'build/' only match paths with a trailing slash.
    if path.is_dir() and matcher.match_file(rel_posix + "/"):
        return True
    return False


def make_filter(root_dir: Path, patterns=(), matcher=None):
    """
    Builds a single ignore predicate combining all filtering layers:
    built-in rules -> user glob patterns -> .gitignore/.pyaiignore matcher.

    :param root_dir: Root directory of the project.
    :param patterns: User-provided glob patterns (--exclude).
    :param matcher: Optional pathspec matcher (load_ignore_matcher).
    :return: Callable[[Path], bool]; True means 'ignore'.
    """
    root_dir = Path(root_dir)

    def _ignore(path: Path) -> bool:
        if should_ignore(path, root_dir):
            return True
        if matches_user_patterns(path, root_dir, patterns):
            return True
        if matches_ignore_files(path, root_dir, matcher):
            return True
        return False

    return _ignore
