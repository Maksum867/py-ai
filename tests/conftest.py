"""
Shared fixtures for the py-ai test suite.
"""

import pytest


@pytest.fixture()
def sample_project(tmp_path):
    """
    Builds a standard sample project tree:

    sample/
    ├── .git/config                 (ignored: VCS)
    ├── .venv/lib/lib.so            (ignored: virtualenv + binary ext)
    ├── .env                        (ignored: secrets)
    ├── .env.example                (packed: allowlisted hidden file)
    ├── .gitignore                  (packed: allowlisted hidden file)
    ├── src/
    │   ├── __init__.py
    │   └── main.py
    ├── docs/
    │   └── guide.md
    ├── data/
    │   └── logo.png                (ignored: binary ext)
    ├── README.md
    └── pyproject.toml
    """
    root = tmp_path / "sample"
    (root / ".git").mkdir(parents=True)
    (root / ".venv" / "lib").mkdir(parents=True)
    (root / "src").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    (root / "data").mkdir(parents=True)

    (root / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (root / ".venv" / "lib" / "lib.so").write_bytes(b"\x7fELF\x00\x00")
    (root / ".env").write_text("SECRET=hunter2\n", encoding="utf-8")
    (root / ".env.example").write_text("SECRET=\n", encoding="utf-8")
    (root / ".gitignore").write_text("*.log\n", encoding="utf-8")
    (root / "src" / "__init__.py").write_text("", encoding="utf-8")
    (root / "src" / "main.py").write_text("def main():\n    return 42\n", encoding="utf-8")
    (root / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (root / "data" / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00")
    (root / "README.md").write_text("# sample\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname = \"s\"\n", encoding="utf-8")
    return root
