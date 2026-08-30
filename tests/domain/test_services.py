"""Direct tests for the pure domain services."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from car_insurance.domain.services.rate_calculator import RateCalculator
from car_insurance.domain.value_objects.geographic_rate_adjustment import (
    GeographicRateAdjustment,
)
from car_insurance.domain.value_objects.money import Money
from car_insurance.domain.value_objects.vehicle_snapshot import VehicleSnapshot
from car_insurance.domain.value_objects.vehicle_year import VehicleYear


def _vehicle(value: str = "100000", year: int = 2016) -> VehicleSnapshot:
    return VehicleSnapshot(
        make="Toyota",
        model="Corolla",
        value=Money(Decimal(value), "USD"),
        year=VehicleYear(year),
    )


def test_rate_calculator_applies_ceiling(rules) -> None:
    capped = RateCalculator.calculate(
        calculation_year=2026,
        geographic_adjustment=GeographicRateAdjustment.zero(),
        rules=replace(rules, maximum_applied_rate=Decimal("0.08")),
        vehicle=_vehicle(year=2000),
    )
    assert capped.value == Decimal("0.080000")


def test_rate_calculator_applies_floor(rules) -> None:
    floored = RateCalculator.calculate(
        calculation_year=2026,
        geographic_adjustment=GeographicRateAdjustment(Decimal("-0.02")),
        rules=replace(rules, minimum_applied_rate=Decimal("0.01")),
        vehicle=_vehicle(value="1000", year=2026),
    )
    assert floored.value == Decimal("0.010000")


def test_negative_gis_adjustment_lowers_rate(rules) -> None:
    lowered = RateCalculator.calculate(
        calculation_year=2026,
        geographic_adjustment=GeographicRateAdjustment(Decimal("-0.01")),
        rules=rules,
        vehicle=_vehicle(year=2012),
    )
    assert lowered.value == Decimal("0.110000")
