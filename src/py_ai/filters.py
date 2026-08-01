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

# File names that are ignored even when they are plain FILES (not
# directories). The generic IGNORED_NAMES set contains *directory* names
# (build, dist, env, venv, node_modules, ...) and must NOT be applied to
# regular files: a legitimate script named 'dist' or 'env' would otherwise
# be silently dropped from the pack.
IGNORED_FILE_NAMES = {
    # OS junk files
    '.DS_Store', 'Thumbs.db', 'desktop.ini',
    # Secrets files (also covered by the hidden-file rule; kept for clarity)
    '.env',
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

    is_file = path.is_file()

    # Check each part of the relative path.
    # If any parent folder is in the ignored list, ignore the entire subtree.
    # The LAST component is the item's own name: for regular files it must
    # NOT be matched against the directory-oriented IGNORED_NAMES set (a
    # legitimate script named 'dist' or 'env' would be silently dropped);
    # file-specific junk names are handled below.
    parts = rel_path.parts
    for index, part in enumerate(parts):
        is_last = index == len(parts) - 1
        lowered = part.lower()
        if lowered in IGNORED_NAMES and not (is_file and is_last):
            return True

        # Python packaging artifacts are named "<pkg>.egg-info", not ".egg-info"
        if lowered.endswith('.egg-info'):
            return True

        # Ignore any hidden folders/files (starting with a dot),
        # except explicitly allowed configuration files such as
        # .gitignore, .env.example or .editorconfig
        if part.startswith('.') and lowered not in ALLOWED_HIDDEN_FILES:
            return True

    # Additional file-level checks for extensions and file names.
    # Only FILE-specific names are checked here (IGNORED_FILE_NAMES);
    # directory names from IGNORED_NAMES must never filter regular files.
    if is_file:
        if path.suffix.lower() in IGNORED_EXTENSIONS:
            return True
        if path.name.lower() in IGNORED_FILE_NAMES:
            return True

    return False


def _find_ignore_files(root_dir: Path) -> list[tuple[Path, str]]:
    """
    Collects every '.pyaiignore' / '.gitignore' file inside the project.

    :param root_dir: Root directory of the project.
    :return: List of ``(base_dir, file_name)`` pairs, ordered so that rules
             applied later win (git semantics): root files first, then deeper
             files; at the same level '.pyaiignore' (tool-specific) comes
             after '.gitignore' so it can override it.
    """
    found: list[tuple[Path, str]] = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Never descend into ignored directory subtrees (perf + correctness).
        dirnames[:] = [
            d for d in dirnames
            if d.lower() not in IGNORED_NAMES and not d.lower().endswith(".egg-info")
        ]
        base = Path(dirpath)
        for name in IGNORE_FILE_NAMES:
            if name in filenames:
                found.append((base, name))

    def _key(item: tuple[Path, str]) -> tuple:
        depth = len(item[0].relative_to(root_dir).parts)
        # .gitignore (0) before .pyaiignore (1) at the same depth.
        is_pyaiignore = item[1] == ".pyaiignore"
        return (depth, is_pyaiignore, item[0].as_posix())

    found.sort(key=_key)
    return found


def _rebase_ignore_line(line: str, rel_dir: str) -> str:
    """
    Rebases one ignore pattern so it is relative to the project root.

    Git semantics: patterns inside 'sub/.gitignore' apply only inside 'sub/',
    so they are prefixed with 'sub/'. The '!' negation prefix and anchored
    '/' leading slashes are preserved. Comments/blank lines pass through.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return line
    if not rel_dir:
        return stripped

    negate = ""
    pattern = stripped
    if pattern.startswith("!"):
        negate = "!"
        pattern = pattern[1:].lstrip()
    # An anchored pattern ('/foo') is relative to the ignore file's own dir.
    pattern = pattern.lstrip("/")
    if pattern:
        return f"{negate}{rel_dir}/{pattern}"
    return line


def load_ignore_matcher(root_dir: Path):
    """
    Loads all '.pyaiignore' / '.gitignore' files inside the project into a
    SINGLE matcher, when the optional 'pathspec' package is available.

    Merging everything into one PathSpec is important: negation rules ('!')
    only work within one spec, so separate specs would make it impossible for
    '.pyaiignore' to re-include / override rules from '.gitignore' (and vice
    versa). Nested ignore files are discovered and their patterns are rebased
    relative to the project root.

    :param root_dir: Root directory of the project.
    :return: A 'pathspec.PathSpec' matcher, or None when the dependency is
             missing or no ignore files exist.
    """
    root_dir = Path(root_dir)
    found_files = _find_ignore_files(root_dir)
    if not found_files:
        return None

    try:
        import pathspec
    except ImportError:
        names = ", ".join(f"{base.name}/{name}" if base != root_dir else name
                          for base, name in found_files[:5])
        if len(found_files) > 5:
            names += f", ... ({len(found_files)} files total)"
        print(
            f"Note: ignore file(s) ({names}) found, but the optional 'pathspec' package is not "
            f"installed. Install it with 'pip install py-for-ai[gitignore]' to respect them.",
            file=sys.stderr,
        )
        return None

    all_lines: list[str] = []
    for base_dir, name in found_files:
        ignore_file = base_dir / name
        try:
            lines = ignore_file.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        except OSError as e:
            print(f"Warning: could not read '{ignore_file}': {e}", file=sys.stderr)
            continue
        if base_dir == root_dir:
            rel_dir = ""
        else:
            rel_dir = base_dir.relative_to(root_dir).as_posix()
        all_lines.extend(_rebase_ignore_line(line, rel_dir) for line in lines)
        all_lines.append("")  # blank separator between ignore files

    # pathspec >= 0.12 renamed the 'gitwildmatch' factory to 'gitignore';
    # fall back to the legacy name for older versions.
    try:
        spec = pathspec.PathSpec.from_lines("gitignore", all_lines)
    except Exception:
        spec = pathspec.PathSpec.from_lines("gitwildmatch", all_lines)
    return spec


def matches_user_patterns(path: Path, root_dir: Path, patterns) -> bool:
    """
    Checks a path against user-provided glob patterns (--exclude).
    Patterns are matched (fnmatch) against the POSIX relative path and
    against the bare file name, so both 'docs/*' and '*.log' work.

    Git-style directory patterns are supported: a trailing slash ('build/')
    matches the directory itself and everything under it.

    NOTE: unlike gitignore, Python's fnmatch '*' matches across '/', so
    'docs/*' also excludes 'docs/deep/file.py'.

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
        if pattern.endswith("/"):
            # Directory pattern ('build/'): match the directory itself (only
            # if `path` IS a directory — a same-named file must not match) or
            # anything under it. This keeps git-style semantics.
            pat = pattern[:-1]
            if not pat:
                continue
            if rel_posix.startswith(pat + "/"):
                return True
            if path.is_dir() and rel_posix == pat:
                return True
        elif fnmatch.fnmatch(rel_posix, pattern) or fnmatch.fnmatch(name, pattern):
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
    # A plain pattern or a directory pattern ('build/' matches only with a
    # trailing slash) can ignore the path.
    return (
        matcher.match_file(rel_posix)
        or (path.is_dir() and matcher.match_file(rel_posix + "/"))
    )


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
        return (
            should_ignore(path, root_dir)
            or matches_user_patterns(path, root_dir, patterns)
            or matches_ignore_files(path, root_dir, matcher)
        )

    return _ignore
