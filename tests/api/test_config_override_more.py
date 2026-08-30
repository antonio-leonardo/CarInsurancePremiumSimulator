"""Phase 5, hardened: more env overrides change the result, no code touched."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from car_insurance.presentation.api import dependencies
from car_insurance.presentation.api.app import create_app
from tests.conftest import FixedClock

_CLOCK_2026 = FixedClock(moment=datetime(2026, 6, 1, 12, 0, tzinfo=UTC))

_EXAMPLE_B = {
    "broker_fee": 50.0,
    "car": {"make": "Toyota", "model": "Corolla", "value": 100000.0, "year": 2012},
    "deductible_percentage": 0.10,
}


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    caches = (
        dependencies._engine,
        dependencies._session_factory,
        dependencies.get_rating_rules,
        dependencies.get_settings,
    )
    for cached in caches:
        cached.cache_clear()
    yield
    for cached in caches:
        cached.cache_clear()


def _calc(monkeypatch: pytest.MonkeyPatch, **env: str) -> dict:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    for cached in (dependencies.get_settings, dependencies.get_rating_rules):
        cached.cache_clear()
    app = create_app()
    app.dependency_overrides[dependencies.get_clock] = lambda: _CLOCK_2026
    return TestClient(app).post("/api/v1/premiums/calculate", json=_EXAMPLE_B).json()


def test_base_rate_override(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _calc(monkeypatch)["applied_rate"] == 0.12
    assert _calc(monkeypatch, BASE_RATE="0.03")["applied_rate"] == 0.15


def test_maximum_applied_rate_caps_the_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _calc(monkeypatch, MAXIMUM_APPLIED_RATE="0.10")["applied_rate"] == 0.10


def test_minimum_applied_rate_floors_the_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    # a brand-new cheap car would price near zero; floor it at 0.20
    body = _calc(
        monkeypatch,
        MINIMUM_APPLIED_RATE="0.20",
        RATE_DECIMAL_PLACES="2",
    )
    assert body["applied_rate"] == 0.2


def test_coverage_percentage_override(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _calc(monkeypatch, COVERAGE_PERCENTAGE="0.80")
    # base_policy_limit = 100000 * 0.80 = 80000 ; deductible 10% -> 8000
    assert body["policy_limit"] == 72000.0
    assert body["deductible_value"] == 8000.0


def test_currency_code_override_is_transparent_to_the_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _calc(monkeypatch, CURRENCY_CODE="BRL")
    # the numeric contract is unchanged; currency is not echoed
    assert body["calculated_premium"] == 10850.0
    assert "currency" not in body


def test_rate_decimal_places_override_changes_precision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fine = _calc(monkeypatch, AGE_RATE_INCREMENT="0.00333")
    coarse = _calc(monkeypatch, AGE_RATE_INCREMENT="0.00333", RATE_DECIMAL_PLACES="3")
    assert fine["applied_rate"] != coarse["applied_rate"]


def test_invalid_env_stops_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONEY_ROUNDING_MODE", "ROUND_SIDEWAYS")
    for cached in (dependencies.get_settings, dependencies.get_rating_rules):
        cached.cache_clear()
    with pytest.raises(ValueError):
        create_app()
