"""``request_id`` binding: sanitisation and contextvar semantics."""

from __future__ import annotations

import pytest

from car_insurance.infrastructure.observability.request_context import (
    bind_request_id,
    current_request_id,
)


@pytest.mark.parametrize(
    "supplied",
    [
        "abc-123",
        "01HXY.trace_id~9",
        "A" * 128,
    ],
)
def test_well_formed_ids_are_kept(supplied: str) -> None:
    assert bind_request_id(request_id=supplied) == supplied


@pytest.mark.parametrize(
    "supplied",
    [
        "has spaces",
        "with\ttab",
        "with\nnewline",
        "inject: X-Evil: 1",
        "A" * 129,
        "unicöde",
        "",
        "semicolon;value",
        "<script>alert(1)</script>",
    ],
)
def test_hostile_ids_are_replaced_with_a_uuid(supplied: str) -> None:
    resolved = bind_request_id(request_id=supplied)
    assert resolved != supplied
    assert len(resolved) == 36  # uuid4 string
    assert "\n" not in resolved and " " not in resolved


def test_missing_id_generates_one() -> None:
    resolved = bind_request_id(request_id=None)
    assert current_request_id() == resolved
    assert len(resolved) == 36


def test_binding_is_context_local() -> None:
    bind_request_id(request_id="outer")
    assert current_request_id() == "outer"
    bind_request_id(request_id="inner")
    assert current_request_id() == "inner"
