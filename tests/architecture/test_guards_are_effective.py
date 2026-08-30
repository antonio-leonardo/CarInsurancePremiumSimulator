"""Meta-tests: prove the architecture guards actually catch violations,
plus an AST backstop for the import rules that does not depend on
``import-linter`` being installed.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

from tests.architecture.test_alphabetical_order import (
    _assert_sorted,
    _is_exempt,
    _parameter_names,
)

_SRC = Path(__file__).resolve().parents[2] / "src" / "car_insurance"
_FORBIDDEN_IN_CORE = ("fastapi", "pydantic", "sqlalchemy", "httpx", "structlog")


def _imports(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


@pytest.mark.parametrize(
    "layer",
    ["domain", "application"],
)
def test_core_layers_import_no_framework(layer: str) -> None:
    for path in (_SRC / layer).rglob("*.py"):
        imported = _imports(ast.parse(path.read_text(encoding="utf-8")))
        leaked = imported.intersection(_FORBIDDEN_IN_CORE)
        assert not leaked, f"{path} imports {leaked}"


def test_domain_never_imports_outward() -> None:
    for path in (_SRC / "domain").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for outward in (
            "car_insurance.application",
            "car_insurance.infrastructure",
            "car_insurance.presentation",
        ):
            assert outward not in text, f"{path} references {outward}"


def test_application_never_imports_infra_or_presentation() -> None:
    for path in (_SRC / "application").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for outward in ("car_insurance.infrastructure", "car_insurance.presentation"):
            assert outward not in text, f"{path} references {outward}"


def test_alpha_order_checker_flags_unsorted_functions() -> None:
    with pytest.raises(AssertionError):
        _assert_sorted(context="x", names=["b", "a"])


def test_alpha_order_checker_flags_unsorted_params() -> None:
    tree = ast.parse(textwrap.dedent("def f(*, b, a): ..."))
    func = tree.body[0]
    assert isinstance(func, ast.FunctionDef)
    with pytest.raises(AssertionError):
        _assert_sorted(context="params", names=_parameter_names(func))


def test_alpha_order_exemption_marker_is_recognised() -> None:
    tree = ast.parse("# alpha-order: framework\ndef f(*, b, a): ...")
    func = tree.body[0]
    lines = ["# alpha-order: framework", "def f(*, b, a): ..."]
    assert _is_exempt(lines=lines, node=func) is True


def test_alpha_order_exemptions_stay_minimal() -> None:
    hits = {
        path.name
        for path in _SRC.rglob("*.py")
        if "alembic" not in path.parts
        and "# alpha-order: framework" in path.read_text(encoding="utf-8")
    }
    # Only genuinely framework-imposed signatures: the ASGI middleware and the
    # Starlette exception-handler signature.
    assert hits == {"app.py", "errors.py"}, f"unexpected alpha-order exemptions: {hits}"
