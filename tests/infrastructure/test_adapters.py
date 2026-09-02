"""Small adapter tests: clock, null adapters, publishers, settings."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from car_insurance.domain.events.premium_simulation_calculated import (
    PremiumSimulationCalculated,
)
from car_insurance.domain.value_objects.address import Address
from car_insurance.domain.value_objects.simulation_id import SimulationId
from car_insurance.infrastructure.config.rules_factory import build_rating_rules
from car_insurance.infrastructure.config.settings import Settings
from car_insurance.infrastructure.events.logging_event_publisher import (
    LoggingEventPublisher,
)
from car_insurance.infrastructure.gis.null_geographic_rate_provider import (
    NullGeographicRateProvider,
)
from car_insurance.infrastructure.observability.structlog_logger import StructlogLogger
from car_insurance.infrastructure.persistence.null_repository import (
    NullSimulationRepository,
)
from car_insurance.infrastructure.time.system_clock import SystemClock


def _event() -> PremiumSimulationCalculated:
    return PremiumSimulationCalculated(
        applied_rate=Decimal("0.12"),
        calculated_premium=Decimal(100),
        deductible_value=Decimal(10),
        location_country="US",
        occurred_at=datetime(2026, 1, 1, tzinfo=ZoneInfo("UTC")),
        policy_limit=Decimal(90),
        rules_version="v",
        simulation_id=SimulationId.new(),
        vehicle_make="Toyota",
        vehicle_model="Corolla",
        vehicle_year=2016,
    )


def test_system_clock_is_timezone_aware() -> None:
    moment = SystemClock(timezone=ZoneInfo("America/Sao_Paulo")).now()
    assert moment.tzinfo is not None


def test_null_repository_behaviour() -> None:
    repository = NullSimulationRepository()
    repository.save(simulation=None)  # type: ignore[arg-type]
    assert repository.get(simulation_id=SimulationId.new()) is None
    page = repository.list(cursor=None, limit=10)
    assert page.items == ()
    assert page.next_cursor is None


def test_null_gis_provider_returns_zero() -> None:
    adjustment = NullGeographicRateProvider().adjustment_for(address=Address(country="US"))
    assert adjustment.value == Decimal(0)


def test_logging_event_publisher_does_not_raise() -> None:
    LoggingEventPublisher().publish(events=[_event()])


def test_structlog_logger_forwards_all_levels() -> None:
    from structlog.testing import capture_logs

    logger = StructlogLogger(name="test")
    with capture_logs() as events:
        logger.info("i", a=1)
        logger.warning("w", b=2)
        logger.error("e", c=3)
    assert [(e["event"], e["log_level"]) for e in events] == [
        ("i", "info"),
        ("w", "warning"),
        ("e", "error"),
    ]


def test_structlog_logger_bind_returns_a_logger_carrying_fields() -> None:
    from structlog.testing import capture_logs

    logger = StructlogLogger(name="test")
    child = logger.bind(simulation_id="abc-123")
    with capture_logs() as events:
        child.info("premium.calculated", applied_rate="0.10")
        logger.info("unbound.line")
    assert events[0]["simulation_id"] == "abc-123"
    assert "simulation_id" not in events[1]  # bind does not mutate the parent


def test_settings_defaults_build_rules() -> None:
    rules = build_rating_rules(settings=Settings())
    assert rules.currency_code == "USD"
    assert rules.rate_decimal_places == 6


@pytest.mark.parametrize(
    "env",
    [
        {"GIS_FAILURE_MODE": "sideways"},
        {"PERSISTENCE_FAILURE_MODE": "sideways"},
        {"LOG_FORMAT": "smoke-signals"},
        {"MONEY_ROUNDING_MODE": "ROUND_SOMEHOW"},
        {"RATE_ROUNDING_MODE": "ROUND_SOMEHOW"},
        {"GIS_MIN_ADJUSTMENT": "0.5", "GIS_MAX_ADJUSTMENT": "0.1"},
        {"GIS_ENABLED": "true"},
        {
            "GIS_ENABLED": "true",
            "GIS_BASE_URL": "https://x",
            "GIS_TIMEOUT_SECONDS": "0",
        },
        {"BUSINESS_TIMEZONE": "Mars/Olympus"},
        {"PERSISTENCE_ENABLED": "true", "DATABASE_URL": "not-a-dsn"},
        {"PERSISTENCE_ENABLED": "true", "DATABASE_URL": ""},
        {"DB_POOL_SIZE": "0"},
        {"DB_MAX_OVERFLOW": "-1"},
        {"MONEY_DECIMAL_PLACES": "-1"},
    ],
)
def test_settings_rejects_bad_config(env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):
        Settings()


def test_persistence_off_tolerates_an_unreachable_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    # A syntactically valid DSN that simply cannot connect is fine while
    # persistence is off — no engine is ever built (A7).
    monkeypatch.setenv("PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@nohost:5432/db")
    assert Settings().persistence_enabled is False


def test_malformed_dsn_fails_boot_even_with_persistence_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A DSN that is not even a URL stops the boot regardless of persistence (A7):
    # it must never surface as a request-time 500.
    monkeypatch.setenv("PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("DATABASE_URL", "not-a-dsn")
    with pytest.raises(ValueError):
        Settings()


def test_settings_blank_maximum_rate_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAXIMUM_APPLIED_RATE", "")
    assert Settings().maximum_applied_rate is None


def test_settings_business_tzinfo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUSINESS_TIMEZONE", "America/Sao_Paulo")
    assert Settings().business_tzinfo.key == "America/Sao_Paulo"
