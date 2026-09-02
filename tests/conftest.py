"""Shared test fixtures and fakes."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from car_insurance.application.dto.calculate_premium_output import (
    CalculatePremiumOutput,
    SimulationPage,
)
from car_insurance.application.ports.geographic_rate_provider import (
    GeographicRateProviderError,
)
from car_insurance.domain.aggregates.premium_simulation import PremiumSimulation
from car_insurance.domain.events.premium_simulation_calculated import (
    PremiumSimulationCalculated,
)
from car_insurance.domain.value_objects.address import Address
from car_insurance.domain.value_objects.geographic_rate_adjustment import (
    GeographicRateAdjustment,
)
from car_insurance.domain.value_objects.rating_rules import RatingRules
from car_insurance.domain.value_objects.simulation_id import SimulationId


class FakeEventPublisher:
    """Captures published events for assertions."""

    def __init__(self) -> None:
        self.published: list[PremiumSimulationCalculated] = []

    def publish(self, *, events: Sequence[PremiumSimulationCalculated]) -> None:
        self.published.extend(events)


class FakeLogger:
    """Records structured log calls for assertions."""

    def __init__(self, *, bound: dict[str, object] | None = None) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []
        self.bound: dict[str, object] = dict(bound or {})

    def bind(self, /, **fields: object) -> FakeLogger:
        child = FakeLogger(bound={**self.bound, **fields})
        child.calls = self.calls  # share the sink so assertions see every line
        return child

    def error(self, event: str, /, **fields: object) -> None:
        self.calls.append(("error", event, {**self.bound, **fields}))

    def info(self, event: str, /, **fields: object) -> None:
        self.calls.append(("info", event, {**self.bound, **fields}))

    def warning(self, event: str, /, **fields: object) -> None:
        self.calls.append(("warning", event, {**self.bound, **fields}))


class FakeGeographicRateProvider:
    """Returns a fixed adjustment, or raises to simulate a fail-closed provider."""

    def __init__(
        self,
        *,
        adjustment: GeographicRateAdjustment | None = None,
        error: bool = False,
    ) -> None:
        self._adjustment = adjustment or GeographicRateAdjustment.zero()
        self._error = error
        self.calls: list[Address] = []

    def adjustment_for(self, *, address: Address) -> GeographicRateAdjustment:
        self.calls.append(address)
        if self._error:
            raise GeographicRateProviderError("boom")
        return self._adjustment


class FakeRepository:
    """In-memory repository keyed by simulation id."""

    def __init__(self) -> None:
        self.saved: list[PremiumSimulation] = []
        self._store: dict[str, CalculatePremiumOutput] = {}

    def get(self, *, simulation_id: SimulationId) -> CalculatePremiumOutput | None:
        return self._store.get(str(simulation_id))

    def list(self, *, cursor: str | None, limit: int) -> SimulationPage:
        items = tuple(self._store.values())[:limit]
        return SimulationPage(items=items, next_cursor=None)

    def save(self, *, simulation: PremiumSimulation) -> None:
        self.saved.append(simulation)


class FixedClock:
    """A :class:`Clock` frozen at a fixed instant."""

    def __init__(self, *, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


@pytest.fixture
def clock_2026() -> FixedClock:
    return FixedClock(moment=datetime(2026, 6, 15, 12, 0, tzinfo=UTC))


@pytest.fixture
def rules() -> RatingRules:
    return RatingRules(
        age_rate_increment=Decimal("0.005"),
        base_rate=Decimal(0),
        coverage_percentage=Decimal("1.00"),
        currency_code="USD",
        gis_max_adjustment=Decimal("0.02"),
        gis_min_adjustment=Decimal("-0.02"),
        max_deductible_percentage=Decimal("1.0"),
        maximum_applied_rate=None,
        min_vehicle_year=1900,
        minimum_applied_rate=Decimal(0),
        money_decimal_places=2,
        money_rounding_mode="ROUND_HALF_UP",
        rate_decimal_places=6,
        rate_rounding_mode="ROUND_HALF_UP",
        rules_version="2026.08.0",
        value_band_amount=Decimal(10000),
        value_rate_increment=Decimal("0.005"),
    )
