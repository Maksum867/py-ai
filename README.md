<div align="center">

# py-ai 🚀

[![PyPI version](https://img.shields.io/pypi/v/py-ai-pack.svg)](https://pypi.org/project/py-ai-pack/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Support](https://img.shields.io/pypi/pyversions/py-ai-pack.svg)](https://pypi.org/project/py-ai-pack/)

`py-ai` is a lightweight, zero-configuration command-line interface (CLI) tool designed for developers. It recursively scans your local Python codebase, filters out unnecessary files, and compiles your entire project—complete with a beautiful ASCII directory tree—into a single, organized text file while automatically copying it to your clipboard. 

Perfect for instantly feeding your codebase context into Large Language Models (LLMs) like ChatGPT, Claude, and Gemini.

</div>

---

## ✨ Features

- **Smart Filtering**: Automatically ignores VCS folders (`.git`), virtual environments (`.venv`, `venv`), IDE settings (`.vscode`, `.idea`), build artifacts (`dist`, `build`), and binary files (images, archives, databases).
- **ASCII Directory Tree**: Generates a clean, sorted representation of your project layout at the top of the output.
- **Normalized File Markers**: Wraps each file's code in distinct delimiters (`--- START OF FILE: ... ---`) using normalized cross-platform POSIX paths (`/`).
- **Clipboard Integration**: Automatically copies the packed content. Gracefully falls back with a warning in headless/SSH environments rather than crashing.
- **PyPI & Hatchling Ready**: Out-of-the-box support for modern PEP 621 packaging.

---

## 📂 Project Layout

```text
py_ai_project/
├── pyproject.toml
├── README.md
└── src/
    └── py_ai/
        ├── __init__.py
        ├── __main__.py
        ├── core.py
        └── cli.py
```

---

## 🚀 Quick Start

### Installation

Install the utility directly from PyPI:

```bash
pip install py-ai
```

*(Or install it locally for development)*:

```bash
git clone https://github.com/Maksum867/py-ai.git
cd py_ai_project
pip install -e .
```

### Usage

Run the utility from any terminal session:

```bash
# 1. Pack current directory and copy to clipboard:
pyai

# 2. Pack a specific directory:
pyai /path/to/your/project

# 3. Save the results to a custom file:
pyai . -o custom_output.txt

# 4. Run without clipboard copy (ideal for remote servers or CI/CD):
pyai --no-clipboard
```

---

## 📄 Output Format Example

```text
================================================================================
PROJECT CONTEXT PACK: my_project
Generated on: 2026-07-31 12:00:00
Total files packed: 2
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

---

## 🛠️ Requirements & Dependencies

- Python `3.8` or higher.
- `pyperclip` (for clipboard operations).