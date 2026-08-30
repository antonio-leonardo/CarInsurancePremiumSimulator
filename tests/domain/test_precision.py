"""Precision policy: no early quantisation, quantised rate is the one reused,
and the coverage leg follows the spec formula (not ``base - deductible_value``).

Each test is written so that a plausible wrong implementation produces a
*different* number — they are mutation-killers, not smoke tests.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from car_insurance.domain.aggregates.premium_simulation import PremiumSimulation
from car_insurance.domain.value_objects.geographic_rate_adjustment import (
    GeographicRateAdjustment,
)
from car_insurance.domain.value_objects.money import Money
from car_insurance.domain.value_objects.percentage import Percentage
from car_insurance.domain.value_objects.vehicle_snapshot import VehicleSnapshot
from car_insurance.domain.value_objects.vehicle_year import VehicleYear

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _simulate(*, broker="0", deductible="0.10", rules, value="100000", year=2016):
    return PremiumSimulation.calculate(
        broker_fee=Money(Decimal(broker), "USD"),
        deductible_percentage=Percentage(Decimal(deductible)),
        geographic_adjustment=GeographicRateAdjustment.zero(),
        now=_NOW,
        registration_location=None,
        rules=rules,
        vehicle=VehicleSnapshot(
            make="M",
            model="D",
            value=Money(Decimal(value), "USD"),
            year=VehicleYear(year),
        ),
    )


def test_quantised_rate_is_reused_in_the_premium(rules) -> None:
    # rate_decimal_places = 2 makes quantisation visible: raw 0.125 -> 0.13 (HALF_UP).
    coarse = replace(rules, rate_decimal_places=2)
    # value 250000 -> 25 bands * 0.005 = 0.125 ; age 0 -> raw rate 0.125.
    simulation = _simulate(rules=coarse, value="250000", year=2026, deductible="0", broker="0")

    assert simulation.applied_rate.value == Decimal("0.13")
    # base_premium must use 0.13, NOT the unquantised 0.125.
    assert simulation.calculated_premium.amount == Decimal("32500.00")  # 250000 * 0.13
    assert simulation.calculated_premium.amount != Decimal("31250.00")  # 250000 * 0.125


def test_intermediates_are_full_precision(rules) -> None:
    # value 100.06, rate 0.1 (age 20) -> base_premium 10.006 (full precision).
    # deductible 0.5 -> discount 5.003 ; premium = quantize(10.006 - 5.003) = 5.00.
    # A build that quantised base_premium/discount first would get 10.01 - 5.00 = 5.01.
    simulation = _simulate(rules=rules, value="100.06", year=2006, deductible="0.5", broker="0")

    assert simulation.applied_rate.value == Decimal("0.100000")
    assert simulation.calculated_premium.amount == Decimal("5.00")
    assert simulation.calculated_premium.amount != Decimal("5.01")


def test_policy_limit_uses_spec_formula_not_base_minus_deductible_value(rules) -> None:
    # base_policy_limit = 100 ; deductible 0.12345 -> base*ded = 12.345.
    # deductible_value = quantize(12.345)   = 12.35 (HALF_UP)
    # policy_limit     = quantize(100 - 12.345) = quantize(87.655) = 87.66 (HALF_UP)
    # base - deductible_value                = 87.65  -> must NOT equal policy_limit.
    simulation = _simulate(rules=rules, value="100", year=2026, deductible="0.12345", broker="0")

    assert simulation.deductible_value.amount == Decimal("12.35")
    assert simulation.policy_limit.amount == Decimal("87.66")
    assert simulation.policy_limit.amount != (
        simulation.vehicle.value.amount - simulation.deductible_value.amount
    )


def test_broker_fee_is_added_after_the_deductible_discount(rules) -> None:
    # If broker_fee were discounted too, a 100% deductible would zero it out.
    simulation = _simulate(rules=rules, deductible="1.0", broker="123.45", value="100000")
    assert simulation.calculated_premium.amount == Decimal("123.45")


def test_deductible_zero_echoes_base_premium_and_limit(rules) -> None:
    simulation = _simulate(rules=rules, deductible="0", broker="0", value="100000", year=2016)
    # applied_rate 0.10 -> base_premium 10000 ; no discount, no broker.
    assert simulation.calculated_premium.amount == Decimal("10000.00")
    assert simulation.deductible_value.amount == Decimal("0.00")
    assert simulation.policy_limit.amount == Decimal("100000.00")


def test_output_scales_are_exact(rules) -> None:
    simulation = _simulate(rules=rules, value="100000", year=2012)
    assert simulation.applied_rate.value.as_tuple().exponent == -6
    for money in (
        simulation.calculated_premium,
        simulation.deductible_value,
        simulation.policy_limit,
    ):
        assert money.amount.as_tuple().exponent == -2


def test_rounding_mode_is_honoured(rules) -> None:
    # value 100.10, age 10 -> rate 0.05 -> base_premium 5.005 ; no discount/broker.
    # premium = 5.005 -> HALF_UP 5.01 ; ROUND_DOWN 5.00 (exact half, so the mode decides).
    half_up = _simulate(
        rules=replace(rules, money_rounding_mode="ROUND_HALF_UP"),
        value="100.10",
        year=2016,
        deductible="0",
        broker="0",
    )
    down = _simulate(
        rules=replace(rules, money_rounding_mode="ROUND_DOWN"),
        value="100.10",
        year=2016,
        deductible="0",
        broker="0",
    )
    assert half_up.calculated_premium.amount == Decimal("5.01")
    assert down.calculated_premium.amount == Decimal("5.00")


def test_calculation_is_reproducible(rules) -> None:
    first = _simulate(rules=rules, value="73210.55", year=2011, deductible="0.17", broker="12.5")
    second = _simulate(rules=rules, value="73210.55", year=2011, deductible="0.17", broker="12.5")

    assert first.applied_rate == second.applied_rate
    assert first.calculated_premium == second.calculated_premium
    assert first.deductible_value == second.deductible_value
    assert first.policy_limit == second.policy_limit
    assert first.id != second.id  # identity still fresh each run


@pytest.mark.parametrize("adjustment", ["-0.02", "-0.5", "-999"])
def test_negative_gis_never_pushes_rate_below_minimum(adjustment, rules) -> None:
    floored = replace(rules, minimum_applied_rate=Decimal("0.00"))
    simulation = PremiumSimulation.calculate(
        broker_fee=Money(Decimal(0), "USD"),
        deductible_percentage=Percentage(Decimal(0)),
        geographic_adjustment=GeographicRateAdjustment(Decimal(adjustment)),
        now=_NOW,
        registration_location=None,
        rules=floored,
        vehicle=VehicleSnapshot(
            make="M",
            model="D",
            value=Money(Decimal(100000), "USD"),
            year=VehicleYear(2026),
        ),
    )
    assert simulation.applied_rate.value >= Decimal(0)
