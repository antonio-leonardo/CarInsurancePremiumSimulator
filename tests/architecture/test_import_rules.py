"""Runs import-linter to enforce the Clean Architecture dependency rule."""

from __future__ import annotations

import subprocess
from pathlib import Path
from shutil import which

import pytest

_ROOT = Path(__file__).resolve().parents[2]


def test_import_contracts_hold() -> None:
    executable = which("lint-imports")
    if executable is None:  # pragma: no cover - only when dev extras are missing
        pytest.skip("import-linter is not installed")
    result = subprocess.run(
        [executable],
        capture_output=True,
        check=False,
        cwd=_ROOT,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
