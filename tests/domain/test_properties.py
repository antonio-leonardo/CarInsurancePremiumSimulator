"""Property-based checks for the calculation invariants."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from car_insurance.domain.aggregates.premium_simulation import PremiumSimulation
from car_insurance.domain.value_objects.geographic_rate_adjustment import (
    GeographicRateAdjustment,
)
from car_insurance.domain.value_objects.money import Money
from car_insurance.domain.value_objects.percentage import Percentage
from car_insurance.domain.value_objects.rating_rules import RatingRules
from car_insurance.domain.value_objects.vehicle_snapshot import VehicleSnapshot
from car_insurance.domain.value_objects.vehicle_year import VehicleYear

_NOW = datetime(2026, 1, 1, tzinfo=UTC)

_RULES = RatingRules(
    age_rate_increment=Decimal("0.005"),
    base_rate=Decimal(0),
    coverage_percentage=Decimal("1.00"),
    currency_code="USD",
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

_deductibles = st.decimals(min_value=Decimal(0), max_value=Decimal(1), places=2)
_values = st.integers(min_value=1, max_value=5_000_000).map(Decimal)
_years = st.integers(min_value=1990, max_value=2026)


def _run(*, deductible: Decimal, value: Decimal, year: int) -> PremiumSimulation:
    return PremiumSimulation.calculate(
        broker_fee=Money(Decimal(25), "USD"),
        deductible_percentage=Percentage(deductible),
        geographic_adjustment=GeographicRateAdjustment.zero(),
        now=_NOW,
        registration_location=None,
        rules=_RULES,
        vehicle=VehicleSnapshot(
            make="M", model="D", value=Money(value, "USD"), year=VehicleYear(year)
        ),
    )


@given(deductible=_deductibles, value=_values, year=_years)
@settings(max_examples=200, deadline=None)
def test_limit_invariants(deductible: Decimal, value: Decimal, year: int) -> None:
    simulation = _run(deductible=deductible, value=value, year=year)
    base = value * _RULES.coverage_percentage

    assert Decimal(0) <= simulation.deductible_value.amount <= base + Decimal("0.01")
    assert abs(
        simulation.policy_limit.amount - (base - simulation.deductible_value.amount)
    ) <= Decimal("0.01")


@given(deductible=_deductibles, value=_values, year=_years)
@settings(max_examples=200, deadline=None)
def test_rate_floor_holds(deductible: Decimal, value: Decimal, year: int) -> None:
    simulation = _run(deductible=deductible, value=value, year=year)
    assert simulation.applied_rate.value >= _RULES.minimum_applied_rate


@given(
    deductible=_deductibles,
    value=_values,
    younger=_years,
    older=_years,
)
@settings(max_examples=200, deadline=None)
def test_rate_monotonic_in_age(
    deductible: Decimal, older: int, value: Decimal, younger: int
) -> None:
    older, younger = min(older, younger), max(older, younger)
    older_rate = _run(deductible=deductible, value=value, year=older).applied_rate.value
    younger_rate = _run(deductible=deductible, value=value, year=younger).applied_rate.value
    assert older_rate >= younger_rate
