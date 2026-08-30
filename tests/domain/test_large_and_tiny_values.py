"""The calculation stays exact well beyond realistic magnitudes, and copes
with tiny values, thanks to the wide-precision calculation context."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal, getcontext

import pytest

from car_insurance.domain.aggregates.premium_simulation import PremiumSimulation
from car_insurance.domain.calculation_context import (
    CALCULATION_PRECISION,
    high_precision,
)
from car_insurance.domain.value_objects.geographic_rate_adjustment import (
    GeographicRateAdjustment,
)
from car_insurance.domain.value_objects.money import Money
from car_insurance.domain.value_objects.percentage import Percentage
from car_insurance.domain.value_objects.vehicle_snapshot import VehicleSnapshot
from car_insurance.domain.value_objects.vehicle_year import VehicleYear

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _simulate(*, deductible: str, rules, value: str, year: int = 2016) -> PremiumSimulation:
    return PremiumSimulation.calculate(
        broker_fee=Money(Decimal(0), "USD"),
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


def test_context_manager_widens_and_restores_precision() -> None:
    outer = getcontext().prec
    with high_precision():
        assert getcontext().prec == CALCULATION_PRECISION
    assert getcontext().prec == outer


def test_thirty_digit_value_is_still_exact_to_the_cent(rules) -> None:
    # 1e29 dollars. The coverage leg is rate-independent: with coverage 1.0 and a
    # 25% deductible the deductible_value is 2.5e28 -> a 31-digit coefficient at
    # the quantise step, which the default 28-digit context cannot represent.
    value = Decimal("1" + "0" * 29)  # 1e29
    simulation = _simulate(deductible="0.25", rules=rules, value=str(value), year=2026)

    with high_precision():
        expected_deductible = (value * Decimal("0.25")).quantize(Decimal("0.01"))
        expected_limit = (value * Decimal("0.75")).quantize(Decimal("0.01"))
        expected_base = value.quantize(Decimal("0.01"))

    assert simulation.deductible_value.amount == expected_deductible
    assert simulation.policy_limit.amount == expected_limit
    assert simulation.deductible_value.amount + simulation.policy_limit.amount == expected_base


def test_premium_leg_exact_with_a_huge_value_and_matching_band(rules) -> None:
    # keep the rate sane by scaling VALUE_BAND_AMOUNT with the value
    big = replace(rules, value_band_amount=Decimal("1" + "0" * 25))
    value = Decimal("1" + "0" * 27)  # 1e27 ; value_units = floor(1e27/1e25) = 100
    simulation = _simulate(deductible="0.10", rules=big, value=str(value), year=2026)

    # value_rate = 100 * 0.005 = 0.5 ; age 0 -> applied_rate 0.500000
    assert simulation.applied_rate.value == Decimal("0.500000")
    with high_precision():
        base_premium = value * Decimal("0.5")
        expected = (base_premium - base_premium * Decimal("0.10")).quantize(Decimal("0.01"))
    assert simulation.calculated_premium.amount == expected


def test_default_context_would_have_failed() -> None:
    # Sanity: prove the wide context is doing real work — the same maths in the
    # default 28-digit context raises on the quantise step.
    from decimal import Context, InvalidOperation, localcontext

    with localcontext(Context(prec=28)), pytest.raises(InvalidOperation):
        (Decimal("1" + "0" * 29) * Decimal("0.25")).quantize(Decimal("0.01"))


def test_one_cent_vehicle_value(rules) -> None:
    simulation = _simulate(deductible="0.10", rules=rules, value="0.01", year=2016)
    # everything rounds to zero cents except the echoed base policy limit
    assert simulation.calculated_premium.amount == Decimal("0.00")
    assert simulation.deductible_value.amount == Decimal("0.00")
    assert simulation.policy_limit.amount == Decimal("0.01")  # quantise(0.01 - 0.001)


def test_many_decimal_places_in_value(rules) -> None:
    simulation = _simulate(deductible="0.10", rules=rules, value="19999.999999999999", year=2026)
    # floor(19999.999.../10000) = 1 -> value_rate 0.005 ; age 0 -> applied_rate 0.005
    assert simulation.applied_rate.value == Decimal("0.005000")
