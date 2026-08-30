"""Composition-root wiring picks the right adapter per configuration."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from car_insurance.infrastructure.events.logging_event_publisher import (
    LoggingEventPublisher,
)
from car_insurance.infrastructure.events.outbox_event_publisher import (
    OutboxEventPublisher,
)
from car_insurance.infrastructure.gis.http_geographic_rate_provider import (
    HttpGeographicRateProvider,
)
from car_insurance.infrastructure.gis.null_geographic_rate_provider import (
    NullGeographicRateProvider,
)
from car_insurance.infrastructure.persistence.null_repository import (
    NullSimulationRepository,
)
from car_insurance.infrastructure.persistence.sqlalchemy_repository import (
    SqlAlchemySimulationRepository,
)
from car_insurance.presentation.api import dependencies


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    for cached in (
        dependencies._engine,
        dependencies._session_factory,
        dependencies.get_rating_rules,
        dependencies.get_settings,
    ):
        cached.cache_clear()
    yield
    for cached in (
        dependencies._engine,
        dependencies._session_factory,
        dependencies.get_rating_rules,
        dependencies.get_settings,
    ):
        cached.cache_clear()


def test_defaults_pick_null_adapters() -> None:
    unit_of_work = dependencies.get_unit_of_work()
    assert isinstance(
        dependencies.get_repository(unit_of_work=unit_of_work), NullSimulationRepository
    )
    assert isinstance(
        dependencies.get_event_publisher(unit_of_work=unit_of_work),
        LoggingEventPublisher,
    )
    assert isinstance(dependencies.get_geographic_rate_provider(), NullGeographicRateProvider)


def test_persistence_enabled_picks_sqlalchemy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSISTENCE_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    unit_of_work = dependencies.get_unit_of_work()
    assert isinstance(
        dependencies.get_repository(unit_of_work=unit_of_work),
        SqlAlchemySimulationRepository,
    )
    assert isinstance(
        dependencies.get_event_publisher(unit_of_work=unit_of_work),
        OutboxEventPublisher,
    )


def test_gis_enabled_picks_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIS_ENABLED", "true")
    monkeypatch.setenv("GIS_BASE_URL", "https://gis.example")
    assert isinstance(dependencies.get_geographic_rate_provider(), HttpGeographicRateProvider)


def test_postgres_engine_is_pooled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSISTENCE_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/db")
    monkeypatch.setenv("DB_POOL_SIZE", "7")
    engine = dependencies.get_engine()  # create_engine is lazy — no connection attempt
    assert engine is not None
    assert engine.pool.size() == 7


def test_stateless_engine_is_none() -> None:
    assert dependencies.get_engine() is None
