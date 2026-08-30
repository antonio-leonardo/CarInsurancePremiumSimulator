"""Extra property-based invariants for the calculation."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

from hypothesis import assume, given, settings
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

_values = st.integers(min_value=1, max_value=5_000_000).map(Decimal)
_deductibles = st.decimals(min_value=Decimal(0), max_value=Decimal(1), places=3)
_years = st.integers(min_value=1970, max_value=2026)


def _run(*, deductible: Decimal, rules: RatingRules = _RULES, value: Decimal, year: int):
    return PremiumSimulation.calculate(
        broker_fee=Money(Decimal(0), "USD"),
        deductible_percentage=Percentage(deductible),
        geographic_adjustment=GeographicRateAdjustment.zero(),
        now=_NOW,
        registration_location=None,
        rules=rules,
        vehicle=VehicleSnapshot(
            make="M", model="D", value=Money(value, "USD"), year=VehicleYear(year)
        ),
    )


@given(deductible=_deductibles, value=_values, year=_years)
@settings(max_examples=150, deadline=None)
def test_rate_never_below_floor_even_with_a_ceiling(
    deductible: Decimal, value: Decimal, year: int
) -> None:
    rules = replace(
        _RULES,
        minimum_applied_rate=Decimal("0.01"),
        maximum_applied_rate=Decimal("0.30"),
    )
    simulation = _run(deductible=deductible, rules=rules, value=value, year=year)
    assert Decimal("0.01") <= simulation.applied_rate.value <= Decimal("0.30")


@given(value=_values, year=_years)
@settings(max_examples=150, deadline=None)
def test_premium_is_monotonic_in_the_rate(value: Decimal, year: int) -> None:
    low = _run(deductible=Decimal(0), value=value, year=year)
    steeper = replace(_RULES, age_rate_increment=Decimal("0.02"))
    high = _run(deductible=Decimal(0), rules=steeper, value=value, year=year)
    assume(high.applied_rate.value > low.applied_rate.value)
    assert high.calculated_premium.amount >= low.calculated_premium.amount


@given(value=_values, year=_years)
@settings(max_examples=150, deadline=None)
def test_zero_deductible_keeps_the_whole_limit(value: Decimal, year: int) -> None:
    simulation = _run(deductible=Decimal(0), value=value, year=year)
    base = value * _RULES.coverage_percentage
    assert simulation.deductible_value.amount == Decimal("0.00")
    assert simulation.policy_limit.amount == _RULES.quantize_money(amount=base)


@given(deductible=_deductibles, value=_values, year=_years)
@settings(max_examples=150, deadline=None)
def test_full_deductible_zeroes_the_limit(deductible: Decimal, value: Decimal, year: int) -> None:
    simulation = _run(deductible=Decimal(1), value=value, year=year)
    assert simulation.policy_limit.amount == Decimal("0.00")
    assert simulation.calculated_premium.amount == Decimal("0.00")  # broker_fee is 0


@given(deductible=_deductibles, value=_values, year=_years)
@settings(max_examples=150, deadline=None)
def test_rate_monotonic_in_value(deductible: Decimal, value: Decimal, year: int) -> None:
    smaller = _run(deductible=deductible, value=value, year=year)
    bigger = _run(deductible=deductible, value=value * 3, year=year)
    assert bigger.applied_rate.value >= smaller.applied_rate.value
