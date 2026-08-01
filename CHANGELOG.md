# Changelog

## [0.3.0] - 2026-08-01

### Added
- **`--quiet` / `-q` and `--verbose` / `-v`** (`cli.py`): suppress all
  informational output (scan banner, summary, clipboard status) for CI, or
  print extra details (e.g. total source lines). Errors and warnings still go
  to stderr. The flags are mutually exclusive.
- **`--no-tree`** (`cli.py`, `core.py`, `formatting.py`): omit the directory
  tree section from both output formats.
- **`--no-token-count`** (`cli.py`, `core.py`): skip token estimation for
  large projects; the header then shows `Estimated tokens: disabled`.
- **Transcoding transparency** (`readers.py`, `core.py`): the reader now
  reports which codec was actually used, and the packer prints a note when a
  non-UTF-8 file (cp1251, latin-1, UTF-16/32) is transcoded to UTF-8.

### Fixed
- **`--exclude 'dir/'` also matched a same-named regular file** (`filters.py`):
  a git-style directory pattern now matches only the directory itself (or
  anything under it), not a file literally named like the pattern.
- **`ai_context.txt` exclusion was applied at any depth** (`core.py`): only a
  root-level leftover pack with the default output name is excluded now; a
  legitimate nested file named `ai_context.txt` stays in the pack.
- **Stale type annotations** for the visited-directories set (`core.py`):
  they describe the actual `_dir_identity()` keys.
- Docs: removed the brittle hardcoded test count from the README.
- Added `verify_all.ps1`: one-file pre-release verification (tests, lint,
  CLI smoke, git hygiene, build, wheel smoke).
- **Ruff lint fixes** (`src/`, `tests/`): sorted imports/`__all__`, removed an
  unused import, `IOError` → `OSError` (alias in Python 3), dropped a
  redundant UTF-8 argument; added a `[tool.ruff]` config documenting the
  intentionally-ignored rules (`BLE001`, `S110`, `DTZ005`).
- **Silent data loss on filesystems with unreliable inodes** (`core.py`): duplicate/cycle
  detection keyed only on `(st_dev, st_ino)` treated every directory as a duplicate when
  `st_ino` was 0 or repeated (some network/FUSE mounts), silently dropping whole subtrees.
  A stable directory identity (inode when available, resolved path otherwise) is used now.
- **`.pyaiignore` / `.gitignore` interplay** (`filters.py`): both files were compiled into
  separate `PathSpec` objects, so `!` negation never worked across files and `.pyaiignore`
  could not override `.gitignore`. All ignore files are now merged into a single matcher
  (later rules win), so `.pyaiignore` correctly takes precedence.
- **Nested `.gitignore` files were ignored** (`filters.py`): only root-level ignore files
  were read. All ignore files inside the project are now discovered and their patterns are
  rebased relative to the project root (git semantics).
- **`Output Size` reported characters instead of bytes** (`core.py`): `len()` understated
  non-ASCII content (e.g. Cyrillic in UTF-8). The on-disk byte size is reported now.
- **Legitimate files named like ignored directories were dropped** (`filters.py`): files
  literally named `dist`, `env`, `build`, `venv`, ... (no extension) were silently excluded
  because directory-oriented `IGNORED_NAMES` was applied to file names too. Only
  file-specific junk names (`.DS_Store`, `Thumbs.db`, `desktop.ini`, `.env`) filter files now.
- **`--exclude 'dir/'` did not work** (`filters.py`): a trailing-slash pattern now excludes
  the directory and everything under it (git-style); the `*`-crosses-`/` fnmatch behaviour is
  documented in the README.
- **Leftover default output packs were re-packed** (`core.py`): `ai_context.txt` from a
  previous run is never included in a new pack, even when the new output uses another name.
- **Misleading tree note for plain symlink aliases** (`core.py`): a normal `alias -> real`
  directory link is now annotated as "cyclic or duplicate link — already traversed, not
  followed" instead of "skipped".
- **`py-ai --version` printed `pyai 0.2.0`** (`cli.py`): the program name is now derived
  from how the tool was invoked.
- **`--max-file-size 0` (or sub-byte sizes) was accepted** (`cli.py`): values `<= 0` are
  rejected with a clear error instead of silently skipping every file.
- **Potential unhandled `OSError` in the CLI banner** (`cli.py`): `Path.resolve()` is now
  guarded.
- **Committed junk removed from the repository**: `.idea/` and `src/py_ai/__pycache__/*.pyc`
  are no longer tracked; `.gitignore` covers them (and more).
- **Missing CI file**: the promised `.github/workflows/tests.yml` (3 OS × Python 3.8–3.14)
  is now present.
- **`verify_release.ps1` hardcoded the version**: it now reads it from `pyproject.toml`.
- Docs: test count and supported Python versions updated.

## [0.2.0] - 2026-07-31

### Added
- **Token estimation** (`py_ai/tokens.py`): every pack reports the total line count and an estimated token count in the output header and CLI summary. Uses `tiktoken` (`cl100k_base`) when installed (`pip install py-for-ai[tokens]`), otherwise a ~4 chars/token heuristic (the CLI always says which method was used).
- **Markdown output format** (`--format markdown`, `py_ai/formatting.py`): `#` statistics header, fenced ASCII tree, per-file fenced code blocks with language detection by extension and adaptive backtick fences (contents containing ``` are escaped safely).
- **`--max-file-size SIZE`** (e.g. `512KB`, `10MB`): oversized files are skipped with a warning and marked `[skipped: exceeds size limit (...)]` in the tree.
- **`--exclude PATTERN`** (repeatable): extra glob exclusions matched against the relative POSIX path and the file name.
- **`.pyaiignore` / `.gitignore` support** (`py_ai/filters.py`): honored when the optional dependency `pathspec` is installed (`pip install py-for-ai[gitignore]`); disable with `--no-gitignore`. A hint is printed when the files exist but the dependency is missing.
- **`--version`** flag.
- Optional dependency extras in `pyproject.toml`: `tokens`, `gitignore`, `all`, `dev`.
- **Full pytest suite** (55 tests) under `tests/` covering filtering, readers/encodings, symlink safety, output ordering/formatting, CLI exit codes and edge cases (1100-deep nesting, unreadable directories).
- **CI** (`.github/workflows/tests.yml`): pytest matrix on Linux/Windows/macOS × Python 3.8–3.13.
- CLI summary now also prints the output format and total line count.

### Fixed
- **Content ordering regression** (introduced during the 0.1.2 recursion fix): files within a directory were collected in reverse order and before their sibling subtrees. The walker now uses a single mixed work stack reproducing the exact classic DFS order (directories-with-subtrees first, then files, all sorted), and the ordering is locked by a test.
- **Aliased packing via directory symlinks**: a directory symlink (`alias -> real`) caused files to be packed under the alias path. Directory symlinks are now never traversed; they are rendered in the tree as `[directory symlink — not followed]` or, when their target was already visited, as a cycle/duplicate note.
- Markdown blocks no longer render a blank line before the closing fence when the file ends with a newline.
- Removed deprecation warnings with `pathspec` >= 0.12 (new 'gitignore' pattern factory with a legacy fallback).
- **Windows line endings**: the output file was written in text mode, so on
  Windows every `\n` was translated to `\r\n` and CRLF-sourced content was
  doubled to `\r\r\n` (visible as blank lines between all lines). The output
  is now written with `newline=""` (byte-exact). Found by the test suite on
  Windows / Python 3.14.
- Added CI coverage for the newest Python 3.14.

### Changed
- Codebase reorganized into focused modules: `filters.py` (ignore rules), `readers.py` (encodings), `tokens.py` (statistics), `formatting.py` (output assembly); `core.py` keeps orchestration and re-exports the previously public names (`should_ignore`, `read_text_content`, `IGNORED_NAMES`, ...) for backwards compatibility.

## [0.1.2] - 2026-07-31

### Fixed
- **Python 3.8/3.9 support**: the package declared `requires-python = ">=3.8"` but crashed on import with `TypeError: unsupported operand type(s) for |` (PEP 604 `str | Path` annotations were evaluated at import time). Added `from __future__ import annotations` so the declared `>=3.8` support now actually works.
- **Security**: symlinks resolving outside of the project root (e.g. pointing to `/etc` or `$HOME`) were silently packed into the output. Such entries are now excluded from the packed content and shown in the directory tree with an explicit warning note.
- **Symlink cycles**: a cyclic symlink (e.g. `sub/loop -> ../sub`) inflated the directory tree with ~40 nested duplicate levels (until the OS hit ELOOP). Directory traversal now tracks visited `(device, inode)` pairs and traverses cycles/duplicates only once.
- **RecursionError** on deeply nested projects (>~1000 levels): `maximum recursion depth exceeded` aborted the run with exit code 1. Both the directory walker and the tree builder are now iterative (explicit stack).
- **Inconsistent output**: the output file itself (e.g. `ai_context.txt`) was listed in the DIRECTORY TREE on repeated runs while being excluded from the content. It is now excluded from both. Files that fail to be read are kept visible in the tree with a `[skipped: ...]` note.
- **Incomplete binary filtering**: `.exe`, `.bin`, `.dat`, `.msi`, `.jar` and ML artifacts (`.pkl`, `.onnx`, etc.) were missing from the extension list and only caught by the decode-error fallback. The extension list is extended and a NUL-byte content heuristic was added.
- **`*.egg-info` directories** (e.g. `py_for_ai.egg-info/`) were packed even though `.egg-info` was listed in ignored names (real directories never match that exact name). Any path component ending in `.egg-info` is now ignored.
- **Non-UTF-8 text files** (e.g. legacy Windows-1250/1251 Cyrillic files, UTF-16 with BOM) were dropped from the pack. Added BOM-aware decoding and a fallback chain (UTF-8 → cp1251 → latin-1).
- **Duplicate clipboard warning** was printed twice (once from `core`, once from the CLI). The warning is now rendered exactly once by the CLI; `core` only reports it in the returned statistics.
- **Version mismatch**: `py_ai.__version__` reported `0.1.0` while the distribution was `0.1.1`. The version is now read from the installed distribution metadata (`importlib.metadata`) with a sensible fallback.
- **Double tree entry** for unreadable directories (the directory plus an extra sibling line with the error). The access error is now rendered as a single child note of the directory.
- **Docs**: wrong installation command (`pip install py-ai` — no such distribution), broken shield badges (`py-ai-pack`), undocumented `py-ai` alias and undocumented hidden-files filtering policy.

### Added
- CLI summary now prints the generated output size (`💾 Output Size`).
- `CHANGELOG.md`.

### Changed
- The hidden-files allowlist now also includes `.gitattributes`, `.gitmodules`, `.flake8`, `.coveragerc`, `.dockerignore`, `.editorconfig`, `.pre-commit-config.yaml`, `.python-version`, `.readthedocs.yaml`, `.readthedocs.yml`, `.codecov.yml` (matched case-insensitively).

## [0.1.1] - 2026-07-30
- Patch release.

## [0.1.0] - 2026-07-30
- Initial release.