#!/usr/bin/env python3
"""
verify_all.py - cross-platform full verification for py-for-ai (py-ai).

Replaces the old verify_all.ps1 (Windows) and verify_all.sh (Linux/macOS)
with a single script that runs anywhere Python runs - no duplicated logic.

Checks performed:
  0. Environment (Python version)
  1. Editable install with [dev] extras            [skip with --skip-install]
  2. Byte-compile (compileall), ruff (if available), pytest
  3. CLI smoke tests (packing, filters, exit codes, formats)
  4. Git hygiene (no junk files tracked)
  5. Build (wheel + sdist) + twine check           [skip with --skip-build]
  6. Wheel smoke test in a clean temporary venv    [skip with --skip-build]

Usage (from the repo root, a virtual env is recommended):
    python verify_all.py
    python verify_all.py --skip-build
    python verify_all.py --skip-install --skip-build

Exit code: 0 = all checks passed, 1 = at least one FAIL.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent

_pass = 0
_fail = 0


def _c(code: str, text: str) -> str:
    """Wraps text in an ANSI color code when stdout is a terminal."""
    if sys.stdout.isatty():
        return f"\x1b[{code}m{text}\x1b[0m"
    return text


def ok(msg: str) -> None:
    global _pass
    _pass += 1
    print(f"  [{_c('32', 'PASS')}] {msg}")


def bad(msg: str) -> None:
    global _fail
    _fail += 1
    print(f"  [{_c('31', 'FAIL')}] {msg}")


def warn(msg: str) -> None:
    print(f"  [{_c('33', 'WARN')}] {msg}")


def section(name: str) -> None:
    print(f"\n== {name} ==")


def run(cmd: list[str], cwd: Path | None = None, capture: bool = False) -> tuple[int, str]:
    """Runs a command; returns (returncode, combined-output)."""
    sys.stdout.flush()
    try:
        if capture:
            proc = subprocess.run(
                cmd, cwd=cwd, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, errors="replace",
            )
            return proc.returncode, proc.stdout
        proc = subprocess.run(cmd, cwd=cwd)
        return proc.returncode, ""
    except FileNotFoundError:
        return 127, f"command not found: {cmd[0]}"


def read_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"', text, re.MULTILINE)
    return match.group(1) if match else "unknown"


def module_available(name: str, python: str) -> bool:
    rc, _ = run([python, "-c", f"import importlib.util; raise SystemExit(0 if importlib.util.find_spec({name!r}) else 1)"],
                capture=True)
    return rc == 0


def ensure_module(name: str, pip_package: str, python: str) -> bool:
    if module_available(name, python):
        return True
    warn(f"'{name}' not installed - trying to install '{pip_package}'...")
    rc, out = run([python, "-m", "pip", "install", "-q", pip_package], capture=True)
    if rc != 0:
        warn(f"could not install {pip_package}: {out.strip()[:120]}")
        return False
    return True


def make_sample_project(base: Path) -> Path:
    proj = base / "proj"
    (proj / "sub").mkdir(parents=True)
    (proj / "main.py").write_text('print("hello")\n', encoding="utf-8")
    (proj / "sub" / "util.py").write_text("x = 1\n", encoding="utf-8")
    (proj / ".gitignore").write_text("*.log\n", encoding="utf-8")
    (proj / "trace.log").write_text("junk\n", encoding="utf-8")
    return proj


def step_install(python: str, skip: bool) -> None:
    section("1. Install (editable, [dev] extras)")
    if skip:
        warn("skipped (--skip-install)")
        return
    rc, out = run([python, "-m", "pip", "install", "-q", "-e", ".[dev]"], cwd=ROOT, capture=True)
    if rc == 0:
        ok('pip install -e ".[dev]"')
    else:
        bad(f'pip install -e ".[dev]": {out.strip()[-200:]}')


def step_tests(python: str) -> None:
    section("2. Test suite")
    rc, _ = run([python, "-m", "compileall", "-q", "src", "tests"], cwd=ROOT)
    if rc == 0:
        ok("compileall (src, tests)")
    else:
        bad("compileall (src, tests)")

    if shutil.which("ruff") or module_available("ruff", python):
        rc, out = run([python, "-m", "ruff", "check", "src", "tests"], cwd=ROOT, capture=True)
        if rc == 0:
            ok("ruff check")
        else:
            bad(f"ruff check:\n{out.strip()}")
    else:
        warn("ruff not installed - lint check skipped")

    rc, out = run([python, "-m", "pytest", "-q"], cwd=ROOT, capture=True)
    if rc == 0:
        tail = out.strip().splitlines()[-1] if out.strip() else ""
        ok(f"pytest ({tail})")
    else:
        bad("pytest:\n" + out.strip()[-1500:])


def step_cli_smoke(python: str, version: str) -> None:
    section("3. CLI smoke tests")
    with tempfile.TemporaryDirectory(prefix="pyai_verify_") as td:
        tmp = Path(td)
        proj = make_sample_project(tmp)

        pack = tmp / "pack.txt"
        rc, _ = run([python, "-m", "py_ai", str(proj), "-o", str(pack),
                     "--no-clipboard", "--quiet"])
        if rc == 0 and pack.exists():
            ok("pack run (quiet mode)")
        else:
            bad(f"pack run (quiet mode): rc={rc}")
            return

        text = pack.read_text(encoding="utf-8")
        if ("--- START OF FILE: main.py ---" in text
                and "PROJECT CONTEXT PACK: proj" in text
                and "--- START OF FILE: trace.log" not in text):
            ok("pack content (markers, header, .gitignore '*.log' respected)")
        else:
            bad("pack content (markers, header, .gitignore '*.log' respected)")

        if "--- START OF FILE: pack.txt" not in text:
            ok("output file never packs itself")
        else:
            bad("output file never packs itself")

        rc, _ = run([python, "-m", "py_ai", str(tmp / "ghost"), "--no-clipboard"], capture=True)
        if rc == 1:
            ok("missing directory exits 1")
        else:
            bad(f"missing directory exits 1 (rc={rc})")

        rc, _ = run([python, "-m", "py_ai", str(proj), "--max-file-size", "banana",
                     "--no-clipboard"], capture=True)
        if rc == 2:
            ok("invalid --max-file-size exits 2")
        else:
            bad(f"invalid --max-file-size exits 2 (rc={rc})")

        rc, out = run([python, "-m", "py_ai", "--version"], capture=True)
        if rc == 0 and version in out:
            ok(f"--version reports {version}")
        else:
            bad(f"--version reports {version} (got: {out.strip()})")

        md = tmp / "pack.md"
        rc, _ = run([python, "-m", "py_ai", str(proj), "-o", str(md),
                     "--no-clipboard", "--quiet", "--format", "markdown"])
        md_ok = rc == 0 and md.exists()
        if md_ok:
            md_text = md.read_text(encoding="utf-8")
            md_ok = "# Project Context Pack" in md_text and "```python" in md_text
        if md_ok:
            ok("markdown format (header + python fence)")
        else:
            bad("markdown format (header + python fence)")


def step_git_hygiene() -> None:
    section("4. Git hygiene")
    if not (ROOT / ".git").exists():
        warn("not a git repository - git hygiene check skipped")
        return
    rc, out = run(["git", "ls-files"], cwd=ROOT, capture=True)
    if rc != 0:
        warn("git ls-files failed - check skipped")
        return
    junk = [line for line in out.splitlines()
            if re.search(r"(^|/)(__pycache__|\.idea|\.pytest_cache)/|\.pyc$", line)]
    if junk:
        bad(f"junk files tracked in git: {', '.join(junk[:5])}")
    else:
        ok("no junk files tracked in git")


def step_build(python: str) -> Path | None:
    section("5. Build (wheel + sdist)")
    if not ensure_module("build", "build", python):
        bad("build module unavailable - cannot build")
        return None

    dist = Path(tempfile.mkdtemp(prefix="pyai_dist_"))
    rc, out = run([python, "-m", "build", "--outdir", str(dist)], cwd=ROOT, capture=True)
    if rc != 0:
        bad(f"python -m build:\n{out.strip()[-800:]}")
        return None
    ok("python -m build (sdist + wheel)")

    if ensure_module("twine", "twine", python):
        rc, out = run([python, "-m", "twine", "check", str(dist / "*")], capture=True)
        if rc == 0:
            ok("twine check")
        else:
            bad(f"twine check:\n{out.strip()[-400:]}")
    else:
        warn("twine unavailable - check skipped")

    wheels = sorted(dist.glob("*.whl"))
    return wheels[0] if wheels else None


def step_wheel_smoke(python: str, wheel: Path | None, version: str) -> None:
    section("6. Wheel smoke test (clean venv)")
    if wheel is None:
        bad("no wheel produced - smoke test skipped")
        return
    tmp = Path(tempfile.mkdtemp(prefix="pyai_wheelsmoke_"))
    venv_dir = tmp / "venv"
    try:
        venv.create(str(venv_dir), with_pip=True, clear=True)
    except Exception as e:  # noqa: BLE001 - report and skip gracefully
        bad(f"cannot create venv ({e}) - wheel smoke skipped")
        return
    bin_dir = "Scripts" if os.name == "nt" else "bin"
    vpython = venv_dir / bin_dir / ("python.exe" if os.name == "nt" else "python")

    rc, out = run([str(vpython), "-m", "pip", "install", "-q", str(wheel)], capture=True)
    if rc != 0:
        bad(f"wheel install: {out.strip()[-300:]}")
        return

    rc, out = run([str(vpython), "-m", "py_ai", "--version"], capture=True)
    if rc != 0 or version not in out:
        bad(f"wheel --version (got: {out.strip()[:80]})")
        return

    proj = make_sample_project(tmp)
    pack = tmp / "wheel_pack.txt"
    rc, _ = run([str(vpython), "-m", "py_ai", str(proj), "-o", str(pack),
                 "--no-clipboard", "--quiet"])
    if rc == 0 and pack.exists() and "--- START OF FILE: main.py ---" in pack.read_text(encoding="utf-8"):
        ok("wheel installs and packs in a clean venv")
    else:
        bad("wheel installs and packs in a clean venv")


def main() -> int:
    parser = argparse.ArgumentParser(description="py-for-ai full pre-release verification")
    parser.add_argument("--skip-build", action="store_true", help="skip build + wheel smoke")
    parser.add_argument("--skip-install", action="store_true", help="skip pip install step")
    args = parser.parse_args()

    if os.name == "nt":
        os.system("")  # enable ANSI escape processing in the classic console

    version = read_version()
    python = sys.executable

    print("===============================================")
    print(" py-for-ai full verification")
    print("===============================================")
    print(f"Version under test: {version}")
    print(f"Python: {sys.version.split()[0]} ({sys.executable})")

    step_install(python, args.skip_install)
    step_tests(python)
    step_cli_smoke(python, version)
    step_git_hygiene()
    wheel = step_build(python) if not args.skip_build else None
    if args.skip_build:
        print("\n== 5-6. Build & wheel smoke ==")
        warn("skipped (--skip-build)")
    else:
        step_wheel_smoke(python, wheel, version)

    print("\n===============================================")
    print(f" Summary: {_pass} passed, {_fail} failed")
    print("===============================================")
    if _fail == 0 and not args.skip_build:
        print(" Ready to work")
    return 1 if _fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
