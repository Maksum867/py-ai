<div align="center">

# py-ai 🚀

[![PyPI version](https://img.shields.io/pypi/v/py-for-ai.svg)](https://pypi.org/project/py-for-ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/Maksum867/py-ai/blob/main/LICENSE)
[![Python Support](https://img.shields.io/pypi/pyversions/py-for-ai.svg)](https://pypi.org/project/py-for-ai/)

`py-ai` is a lightweight, zero-configuration command-line interface (CLI) tool designed for developers. It recursively scans your local Python codebase, filters out unnecessary files, and compiles your entire project—complete with a beautiful ASCII directory tree and LLM-ready statistics (lines & estimated tokens)—into a single text or Markdown file while automatically copying it to your clipboard.

Perfect for instantly feeding your codebase context into Large Language Models (LLMs) like ChatGPT, Claude, and Gemini.

</div>

---

## ✨ Features

- **LLM-ready statistics**: every pack ends with the total line count and an **estimated token count** (accurate `cl100k_base` counting when `tiktoken` is installed, ~4 chars/token heuristic otherwise), printed in the output header and in the CLI summary.
- **Two output formats**: classic plain text (`--- START OF FILE: ... ---`) and **Markdown** (`--format markdown`) with language-aware fenced code blocks — paste straight into a chat and get syntax highlighting.
- **Smart Filtering**: automatically ignores VCS folders (`.git`, `.github`), virtual environments (`.venv`, `venv`), IDE settings (`.vscode`, `.idea`), build artifacts (`dist`, `build`, `*.egg-info`), caches (`__pycache__`, `.pytest_cache`), binary files (images, archives, databases, executables — plus a NUL-byte content heuristic) and hidden files (except explicitly allowed configs like `.gitignore`, `.env.example`, `.editorconfig`, `.dockerignore`).
- **`.gitignore` / `.pyaiignore` support**: honored automatically when the optional `pathspec` dependency is installed (`pip install py-for-ai[gitignore]`).
- **Custom exclusions**: additional glob patterns via `--exclude` (repeatable) and a per-file size cap via `--max-file-size`.
- **Output control**: `--quiet`/`-q` for CI-friendly silent runs (errors still go to stderr), `--verbose`/`-v` for extra details, `--no-tree` to drop the directory tree section, and `--no-token-count` to skip token estimation on large projects.
- **Symlink-Safe**: symlinks pointing **outside** the project root are never followed or packed; directory symlinks are never traversed, so cycles and aliased duplicates are impossible. Suspicious links stay visible in the directory tree with an explanatory note.
- **Deep-Project-Proof**: iterative (stack-based) directory traversal — no `RecursionError` on very deeply nested projects.
- **Encoding-Aware**: reads UTF-8, UTF-8-BOM, UTF-16/32 (via BOM), legacy Cyrillic `cp1251` and other 8-bit encodings automatically; true binary files are skipped with a clear warning and marked in the tree.
- **ASCII Directory Tree**: a clean, sorted representation of your project layout, consistent with the packed content (skipped files are annotated).
- **Clipboard Integration**: automatically copies the packed content; gracefully falls back with a warning in headless/SSH environments.

---

## 📂 Project Layout

```text
py_ai_project/
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── .github/workflows/tests.yml   # CI: pytest on 3 OS × 6 Python versions
├── tests/                        # pytest suite
└── src/py_ai/
    ├── __init__.py               # version (read from installed metadata)
    ├── __main__.py               # python -m py_ai
    ├── cli.py                    # argument parsing & user interaction
    ├── core.py                   # traversal orchestration + tree builder
    ├── filters.py                # ignore rules, --exclude, .gitignore support
    ├── readers.py                # encoding/binary-aware file reading
    ├── tokens.py                 # line & token statistics
    └── formatting.py             # text / markdown output assembly
```

---

## 🚀 Quick Start

### Installation

Install the utility directly from PyPI (note: the **distribution** name is `py-for-ai`):

```bash
pip install py-for-ai
```

Optional extras:

```bash
pip install "py-for-ai[tokens]"       # accurate token counting via tiktoken
pip install "py-for-ai[gitignore]"    # respect .gitignore / .pyaiignore files
pip install "py-for-ai[all]"          # everything above
```

*(Or install it locally for development)*:

```bash
git clone https://github.com/Maksum867/py-ai.git
cd py-ai
pip install -e ".[dev]"
pytest
```

### Full pre-release verification (one command)

Run everything — tests, lint, CLI smoke checks, git hygiene, build, wheel smoke — from the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File verify_all.ps1     # full check
.\verify_all.ps1 -SkipBuild                                  # quick check (no build)
```

The script exits `0` when every check passes and `1` when anything fails.

### Usage

Run the utility from any terminal session — both `pyai` and the `py-ai` alias are available:

```bash
# 1. Pack current directory and copy to clipboard:
pyai

# 2. Pack a specific directory:
pyai /path/to/your/project

# 3. Save the results to a custom file:
pyai . -o custom_output.txt

# 4. Run without clipboard copy (ideal for remote servers or CI/CD):
pyai --no-clipboard

# 5. Markdown output with syntax-aware code fences:
pyai --format markdown -o context.md

# 6. Skip large files and extra paths:
pyai --max-file-size 200KB --exclude '*.log' --exclude 'docs/*'

# 7. Same via the alias or as a module; show the installed version:
py-ai --no-clipboard
python -m py_ai --version

# 8. CI-friendly: no informational output, no clipboard, no tree:
pyai --quiet --no-clipboard --no-tree -o context.txt

# 9. Skip token estimation (faster on big repos) or show extra details:
pyai --no-token-count
pyai --verbose
```

---

## 📄 Output Format Examples

### Plain text (default)

```text
================================================================================
PROJECT CONTEXT PACK: my_project
Generated on: 2026-07-31 12:00:00
Total files packed: 2
Total lines: 33
Estimated tokens: ~410 (heuristic (~4 chars/token))
================================================================================

================================================================================
DIRECTORY TREE
================================================================================
my_project/
├── src/
│   └── main.py
└── pyproject.toml

================================================================================
FILES CONTENT
================================================================================

--- START OF FILE: pyproject.toml ---
[project]
name = "my_project"
version = "0.1.0"
--- END OF FILE: pyproject.toml ---

--- START OF FILE: src/main.py ---
def main():
    print("Hello, AI!")
--- END OF FILE: src/main.py ---
```

### Markdown (`--format markdown`)

````markdown
# Project Context Pack
- Project: my_project
- Generated on: 2026-07-31 12:00:00
- Total files packed: 1
- Total lines: 15
- Estimated tokens: ~120 (cl100k_base (tiktoken))

## Directory Tree

```text
my_project/
└── src/
    └── main.py
```

## Files Content

### `src/main.py`
```python
def main():
    print("Hello, AI!")
```
````

Files that exist in the project but were not packed (binaries, oversized files, unsafe symlinks) remain visible in the tree with an explanatory note, e.g.:

```text
├── data/
│   ├── dump.bin  [skipped: binary file]
│   ├── huge.log  [skipped: exceeds size limit (200.0 KB)]
│   └── notes.txt -> /etc/hostname  [symlink outside project root — not followed, not packed]
```

---

## ⚙️ Filtering Behavior (what exactly is excluded)

- **Directories/files by name**: `.git`, `.github`, `.gitlab`, `.svn`, `.hg`, `node_modules`, `__pycache__`, `.venv`, `venv`, `env`, `.env`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.tox`, `.nox`, `build`, `dist`, `.idea`, `.vscode`, `.settings`, `.DS_Store`, `Thumbs.db`, `desktop.ini` (matched case-insensitively), any path component ending in `.egg-info`.
- **Binary extensions**: compiled artifacts, archives, images, audio/video, fonts, databases, office documents, ML artifacts (`.pkl`, `.npy`, `.onnx`, …) and executables (`.exe`, `.msi`, `.bin`, `.dll`, `.so`, …). Files of any other type that contain NUL bytes are treated as binary too and skipped with a warning.
- **Hidden files** (starting with `.`) are ignored, **except**: `.gitignore`, `.gitattributes`, `.gitmodules`, `.env.example`, `.env.template`, `.pylintrc`, `.flake8`, `.coveragerc`, `.dockerignore`, `.editorconfig`, `.pre-commit-config.yaml`, `.python-version`, `.readthedocs.yaml`, `.readthedocs.yml`, `.codecov.yml`.
- **`.gitignore` / `.pyaiignore` rules** (when `py-for-ai[gitignore]` is installed; disable with `--no-gitignore`).
- **User patterns** from `--exclude` (matched against the relative POSIX path and the file name). Git-style directory patterns work too: `--exclude 'build/'` excludes the `build/` directory and everything under it. Note: patterns use Python's `fnmatch`, where `*` also matches across `/` (so `docs/*` excludes `docs/deep/file.py` as well).
- **Oversized files** when `--max-file-size` is given.
- **Symlinks resolving outside the project root** and **directory symlinks** are never followed or packed (shown in the tree with a note).
- The **output file itself** is never included in its own pack.

---

## 🪙 Token Estimation

- With `pip install py-for-ai[tokens]`, tokens are counted precisely with `tiktoken` using the `cl100k_base` encoding (used by GPT-3.5/4 families and a reasonable approximation for other models).
- Without it, a widely used heuristic of ~4 characters per token is applied, and the CLI tells you which method was used.

---

## 🛠️ Requirements & Dependencies

- Python `3.8` or higher (verified in CI on 3.8–3.14, Linux/Windows/macOS).
- `pyperclip` (for clipboard operations; requires `xclip`/`xsel` on X11 or `wl-clipboard` on Wayland for Linux desktops — otherwise a warning is shown and the output file is still produced).

---

## 🤝 Contributing

```bash
git clone https://github.com/Maksum867/py-ai.git
cd py-ai
pip install -e ".[dev]"
pytest
```

Please make sure the whole `pytest` suite passes and add tests for new features.