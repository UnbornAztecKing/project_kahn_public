"""Tests verifying the vorpal → slopr rename (Feature 1).

These tests are meta-tests: they scan the repository to ensure no stale
``from vorpal.`` imports remain and that the package entry-point is correct.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


# ── repository root ────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).parent.parent


# ── tests ─────────────────────────────────────────────────────────────────


def test_no_vorpal_imports() -> None:
    """No Python source file should import from the old 'vorpal' package."""
    py_files = list(_REPO_ROOT.rglob("*.py"))
    # Exclude __pycache__ and .git
    py_files = [
        f for f in py_files
        if "__pycache__" not in f.parts and ".git" not in f.parts
    ]
    violations: list[str] = []
    for path in py_files:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("from vorpal.") or stripped.startswith("import vorpal."):
                violations.append(str(path.relative_to(_REPO_ROOT)))
                break

    assert violations == [], (
        f"Files still import from 'vorpal':\n" + "\n".join(f"  {v}" for v in violations)
    )


def test_slopr_entry_point_in_pyproject() -> None:
    """pyproject.toml must declare the 'slopr' console script entry point."""
    pyproject = _REPO_ROOT / "pyproject.toml"
    assert pyproject.exists(), "pyproject.toml not found"
    text = pyproject.read_text(encoding="utf-8")
    assert 'slopr = "slopr.__main__:main"' in text, (
        "Expected 'slopr = \"slopr.__main__:main\"' in pyproject.toml"
    )


def test_cli_help_exits_zero() -> None:
    """'python -m slopr --help' must exit with status 0."""
    result = subprocess.run(
        [sys.executable, "-m", "slopr", "--help"],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"slopr --help exited with {result.returncode}\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
    assert "jsonl" in result.stdout.lower() or "wargame" in result.stdout.lower(), (
        f"Expected help text to mention jsonl or wargame, got:\n{result.stdout}"
    )
