"""Phase 5 gate: environment overrides change the result without code changes."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from car_insurance.application.use_cases.calculate_premium import CalculatePremium
from car_insurance.infrastructure.config.rules_factory import build_rating_rules
from car_insurance.infrastructure.config.settings import Settings
from car_insurance.presentation.api import dependencies
from car_insurance.presentation.api.app import create_app
from tests.conftest import (
    FakeEventPublisher,
    FakeGeographicRateProvider,
    FakeLogger,
    FakeRepository,
    FixedClock,
)

_EXAMPLE_A = {
    "broker_fee": 50.0,
    "car": {"make": "Toyota", "model": "Corolla", "value": 100000.0, "year": 2016},
    "deductible_percentage": 0.10,
}


def _client_with_env(monkeypatch: pytest.MonkeyPatch, **env: str) -> TestClient:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    dependencies.get_settings.cache_clear()
    dependencies.get_rating_rules.cache_clear()
    settings = Settings()
    use_case = CalculatePremium(
        clock=FixedClock(moment=datetime(2026, 1, 1, tzinfo=UTC)),
        event_publisher=FakeEventPublisher(),
        geographic_rate_provider=FakeGeographicRateProvider(),
        logger=FakeLogger(),
        persistence_failure_mode="fail_closed",
        repository=FakeRepository(),
        rules=build_rating_rules(settings=settings),
    )
    app = create_app()
    app.dependency_overrides[dependencies.get_calculate_premium] = lambda: use_case
    return TestClient(app)


def test_age_rate_increment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = (
        _client_with_env(monkeypatch).post("/api/v1/premiums/calculate", json=_EXAMPLE_A).json()
    )
    overridden = (
        _client_with_env(monkeypatch, AGE_RATE_INCREMENT="0.01")
        .post("/api/v1/premiums/calculate", json=_EXAMPLE_A)
        .json()
    )
    assert overridden["applied_rate"] > baseline["applied_rate"]


def test_money_decimal_places_override(monkeypatch: pytest.MonkeyPatch) -> None:
    body = (
        _client_with_env(monkeypatch, MONEY_DECIMAL_PLACES="0")
        .post("/api/v1/premiums/calculate", json=_EXAMPLE_A)
        .json()
    )
    assert body["calculated_premium"] == 9050.0
    assert float(body["calculated_premium"]).is_integer()


def test_value_band_amount_override(monkeypatch: pytest.MonkeyPatch) -> None:
    body = (
        _client_with_env(monkeypatch, VALUE_BAND_AMOUNT="50000")
        .post("/api/v1/premiums/calculate", json=_EXAMPLE_A)
        .json()
    )
    # value_units = floor(100000 / 50000) = 2 -> value_rate 0.01; age 10 -> 0.05; total 0.06
    assert body["applied_rate"] == 0.06


@pytest.fixture(autouse=True)
def _reset_caches() -> None:
    yield
    dependencies.get_settings.cache_clear()
    dependencies.get_rating_rules.cache_clear()
