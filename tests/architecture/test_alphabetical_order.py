"""AST check: functions, methods and parameters are in alphabetical order.

Scope:
* top-level ``def`` / ``async def`` names per module;
* method names inside each class (dunder methods excluded);
* parameter names per signature (``self`` / ``cls`` excluded, positional and
  keyword-only merged).

A single function, method or class may opt out by placing the marker comment
``# alpha-order: framework`` on its ``def``/``class`` line, in its decorator
list, or on the line immediately above.  This is reserved for signatures whose
order a framework dictates (e.g. the ASGI middleware ``(request, call_next)``
signature).  Alembic migration scripts are out of scope.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "src" / "car_insurance"
_EXEMPT_MARKER = "# alpha-order: framework"
_MODULES = sorted(path for path in _SRC.rglob("*.py") if "alembic" not in path.parts)

_Func = ast.FunctionDef | ast.AsyncFunctionDef


def _assert_sorted(*, context: str, names: list[str]) -> None:
    assert names == sorted(names), f"{context}: expected alphabetical order, got {names}"


def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _is_exempt(*, lines: list[str], node: ast.AST) -> bool:
    if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return False
    start = node.lineno
    if node.decorator_list:
        start = min(decorator.lineno for decorator in node.decorator_list)
    return any(
        _EXEMPT_MARKER in lines[index - 1] for index in range(max(1, start - 1), node.lineno + 1)
    )


def _parameter_names(node: _Func) -> list[str]:
    args = node.args
    ordered = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    return [arg.arg for arg in ordered if arg.arg not in {"cls", "self"}]


@pytest.mark.parametrize("module", _MODULES, ids=lambda path: str(path.relative_to(_SRC)))
def test_module_is_alphabetical(module: Path) -> None:
    source = module.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source)
    relative = module.relative_to(_SRC)

    first_statement_line = tree.body[0].lineno if tree.body else len(lines) + 1
    if any(_EXEMPT_MARKER in line for line in lines[: first_statement_line - 1]):
        pytest.skip(f"{relative}: module-level framework exemption (see the module docstring)")

    module_functions = [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and not _is_exempt(lines=lines, node=node)
    ]
    _assert_sorted(context=f"{relative} module functions", names=module_functions)

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and not _is_exempt(
            lines=lines, node=node
        ):
            _assert_sorted(
                context=f"{relative}:{node.lineno} params of {node.name}",
                names=_parameter_names(node),
            )
        if isinstance(node, ast.ClassDef) and not _is_exempt(lines=lines, node=node):
            methods = [
                child.name
                for child in node.body
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
                and not _is_dunder(child.name)
                and not _is_exempt(lines=lines, node=child)
            ]
            _assert_sorted(context=f"{relative} methods of {node.name}", names=methods)
