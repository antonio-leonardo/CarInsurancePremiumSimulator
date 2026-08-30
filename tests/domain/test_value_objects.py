"""Value object invariant tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from car_insurance.domain.errors import (
    AddressError,
    CurrencyMismatchError,
    GeographicRateAdjustmentError,
    MoneyError,
    PercentageError,
    RatingRulesError,
    VehicleYearError,
)
from car_insurance.domain.value_objects.address import Address
from car_insurance.domain.value_objects.geographic_rate_adjustment import (
    GeographicRateAdjustment,
)
from car_insurance.domain.value_objects.money import Money
from car_insurance.domain.value_objects.percentage import Percentage
from car_insurance.domain.value_objects.rating_rules import RatingRules
from car_insurance.domain.value_objects.simulation_id import SimulationId
from car_insurance.domain.value_objects.vehicle_year import VehicleYear


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-Infinity"])
def test_money_rejects_non_finite(amount) -> None:
    with pytest.raises(MoneyError):
        Money(Decimal(amount), "USD")


def test_money_rejects_bad_currency() -> None:
    with pytest.raises(MoneyError):
        Money(Decimal(1), "US")


def test_money_arithmetic_requires_same_currency() -> None:
    with pytest.raises(CurrencyMismatchError):
        Money(Decimal(1), "USD") + Money(Decimal(1), "EUR")


def test_percentage_rejects_negative() -> None:
    with pytest.raises(PercentageError):
        Percentage(Decimal("-0.01"))


def test_percentage_of_coerces_via_string() -> None:
    assert Percentage.of(value=0.1).value == Decimal("0.1")


@pytest.mark.parametrize("year", [1899, 1800])
def test_vehicle_year_below_minimum(year) -> None:
    with pytest.raises(VehicleYearError):
        VehicleYear.create(minimum=1900, value=year)


def test_vehicle_year_rejects_bool() -> None:
    with pytest.raises(VehicleYearError):
        VehicleYear(True)


def test_address_requires_alpha2_country() -> None:
    with pytest.raises(AddressError):
        Address(country="USA")


def test_address_normalises_country() -> None:
    assert Address(country="us").country == "US"


def test_geographic_adjustment_range() -> None:
    with pytest.raises(GeographicRateAdjustmentError):
        GeographicRateAdjustment.within(
            maximum=Decimal("0.02"), minimum=Decimal("-0.02"), value=Decimal("0.05")
        )


def test_simulation_id_roundtrip() -> None:
    identifier = SimulationId.new()
    assert SimulationId.from_string(value=str(identifier)) == identifier


def test_rating_rules_rejects_zero_value_band() -> None:
    with pytest.raises(RatingRulesError):
        RatingRules(
            age_rate_increment=Decimal("0.005"),
            base_rate=Decimal(0),
            coverage_percentage=Decimal(1),
            currency_code="USD",
            max_deductible_percentage=Decimal(1),
            maximum_applied_rate=None,
            min_vehicle_year=1900,
            minimum_applied_rate=Decimal(0),
            money_decimal_places=2,
            money_rounding_mode="ROUND_HALF_UP",
            rate_decimal_places=6,
            rate_rounding_mode="ROUND_HALF_UP",
            rules_version="x",
            value_band_amount=Decimal(0),
            value_rate_increment=Decimal("0.005"),
        )
