"""API test fixtures: a TestClient with fakes wired in."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from car_insurance.application.use_cases.calculate_premium import CalculatePremium
from car_insurance.application.use_cases.get_simulation import GetSimulation
from car_insurance.application.use_cases.list_simulations import ListSimulations
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


@pytest.fixture
def api_context() -> Iterator[dict[str, object]]:
    dependencies.get_settings.cache_clear()
    dependencies.get_rating_rules.cache_clear()
    settings = Settings()
    rules = build_rating_rules(settings=settings)
    clock = FixedClock(moment=datetime(2026, 3, 1, 12, 0, tzinfo=UTC))
    provider = FakeGeographicRateProvider()
    publisher = FakeEventPublisher()
    repository = FakeRepository()

    calculate = CalculatePremium(
        clock=clock,
        event_publisher=publisher,
        geographic_rate_provider=provider,
        logger=FakeLogger(),
        maximum_broker_fee=settings.max_broker_fee,
        maximum_vehicle_value=settings.max_vehicle_value,
        persistence_failure_mode="fail_closed",
        repository=repository,
        rules=rules,
    )

    app = create_app()
    app.dependency_overrides[dependencies.get_calculate_premium] = lambda: calculate
    app.dependency_overrides[dependencies.get_get_simulation] = lambda: GetSimulation(
        repository=repository
    )
    app.dependency_overrides[dependencies.get_list_simulations] = lambda: ListSimulations(
        repository=repository
    )

    with TestClient(app) as client:
        yield {
            "client": client,
            "provider": provider,
            "publisher": publisher,
            "repository": repository,
        }
    app.dependency_overrides.clear()


@pytest.fixture
def client(api_context: dict[str, object]) -> TestClient:
    return api_context["client"]  # type: ignore[return-value]
