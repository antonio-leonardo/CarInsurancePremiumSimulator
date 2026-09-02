"""Exhaustive branch coverage for value-object validation."""

from __future__ import annotations

from decimal import Decimal

import pytest

from car_insurance.domain.errors import (
    AddressError,
    GeographicRateAdjustmentError,
    MoneyError,
    PercentageError,
    RatingRulesError,
    VehicleSnapshotError,
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
from car_insurance.domain.value_objects.vehicle_snapshot import VehicleSnapshot
from car_insurance.domain.value_objects.vehicle_year import VehicleYear


def _rules(**overrides: object) -> RatingRules:
    base: dict[str, object] = {
        "age_rate_increment": Decimal("0.005"),
        "base_rate": Decimal(0),
        "coverage_percentage": Decimal(1),
        "currency_code": "USD",
        "gis_max_adjustment": Decimal("0.02"),
        "gis_min_adjustment": Decimal("-0.02"),
        "max_deductible_percentage": Decimal(1),
        "maximum_applied_rate": None,
        "min_vehicle_year": 1900,
        "minimum_applied_rate": Decimal(0),
        "money_decimal_places": 2,
        "money_rounding_mode": "ROUND_HALF_UP",
        "rate_decimal_places": 6,
        "rate_rounding_mode": "ROUND_HALF_UP",
        "rules_version": "v",
        "value_band_amount": Decimal(10000),
        "value_rate_increment": Decimal("0.005"),
    }
    base.update(overrides)
    return RatingRules(**base)  # type: ignore[arg-type]


def test_money_non_decimal_amount() -> None:
    with pytest.raises(MoneyError):
        Money(1.5, "USD")  # type: ignore[arg-type]


def test_money_add_and_sub() -> None:
    assert (Money(Decimal(3), "USD") - Money(Decimal(1), "USD")).amount == Decimal(2)
    assert (Money(Decimal(3), "usd") + Money(Decimal(1), "USD")).amount == Decimal(4)


def test_money_of_and_with_amount() -> None:
    money = Money.of(amount="10.5", currency="usd")
    assert money.currency == "USD"
    assert money.with_amount(amount=Decimal(2)).amount == Decimal(2)


def test_percentage_non_decimal_and_non_finite() -> None:
    with pytest.raises(PercentageError):
        Percentage(1.0)  # type: ignore[arg-type]
    with pytest.raises(PercentageError):
        Percentage(Decimal("NaN"))


def test_vehicle_year_create_ok_and_is_after() -> None:
    year = VehicleYear.create(minimum=1900, value=2000)
    assert year.is_after(year=1999) is True
    assert year.is_after(year=2001) is False


def test_vehicle_year_create_rejects_non_int() -> None:
    with pytest.raises(VehicleYearError):
        VehicleYear.create(minimum=1900, value="2000")  # type: ignore[arg-type]


def test_vehicle_year_constructor_rejects_non_positive() -> None:
    with pytest.raises(VehicleYearError):
        VehicleYear(0)


def test_vehicle_year_minimum_is_configurable_both_ways() -> None:
    # tighter than the default
    with pytest.raises(VehicleYearError):
        VehicleYear.create(minimum=2000, value=1995)
    # looser than the default 1900
    assert VehicleYear.create(minimum=1850, value=1860).value == 1860


def test_vehicle_snapshot_long_string() -> None:
    with pytest.raises(VehicleSnapshotError):
        VehicleSnapshot(
            make="x" * 121,
            model="ok",
            value=Money(Decimal(1), "USD"),
            year=VehicleYear(2020),
        )


def test_vehicle_snapshot_wrong_types() -> None:
    with pytest.raises(VehicleSnapshotError):
        VehicleSnapshot(make="a", model="b", value=Decimal(1), year=VehicleYear(2020))  # type: ignore[arg-type]
    with pytest.raises(VehicleSnapshotError):
        VehicleSnapshot(
            make="a",
            model="b",
            value=Money(Decimal(1), "USD"),
            year=2020,  # type: ignore[arg-type]
        )


def test_vehicle_snapshot_create_helper() -> None:
    snapshot = VehicleSnapshot.create(
        currency="USD",
        make="Toyota",
        minimum_year=1900,
        model="Corolla",
        value="1000",
        year=2020,
    )
    assert snapshot.value.amount == Decimal(1000)


def test_address_optional_fields_and_too_long() -> None:
    assert Address(country="US", city="SP", region="SP").city == "SP"
    with pytest.raises(AddressError):
        Address(country="US", line1="x" * 181)


def test_geographic_adjustment_non_decimal_and_zero() -> None:
    with pytest.raises(GeographicRateAdjustmentError):
        GeographicRateAdjustment(0.1)  # type: ignore[arg-type]
    with pytest.raises(GeographicRateAdjustmentError):
        GeographicRateAdjustment(Decimal("NaN"))
    assert GeographicRateAdjustment.zero().value == Decimal(0)
    assert GeographicRateAdjustment.within(
        maximum=Decimal("0.02"), minimum=Decimal("-0.02"), value="-0.01"
    ).value == Decimal("-0.01")


def test_simulation_id_rejects_non_uuid() -> None:
    with pytest.raises(TypeError):
        SimulationId("not-a-uuid")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "overrides",
    [
        {"age_rate_increment": Decimal("NaN")},
        {"maximum_applied_rate": Decimal("Infinity")},
        {"age_rate_increment": Decimal(-1)},
        {"base_rate": Decimal(-1)},  # a negative base rate is silently swallowed by the clamp
        {"value_rate_increment": Decimal(-1)},
        {"coverage_percentage": Decimal(0)},
        {"minimum_applied_rate": Decimal(-1)},
        {"money_decimal_places": -1},
        {"rate_decimal_places": -1},
        {"maximum_applied_rate": Decimal(0), "minimum_applied_rate": Decimal("0.5")},
        {"money_rounding_mode": "NOPE"},
        {"rate_rounding_mode": "NOPE"},
        {"currency_code": "US"},
        {"rules_version": ""},
        {"minimum_applied_rate": Decimal("0.1234567")},
        {"maximum_applied_rate": Decimal("0.1234565")},  # not representable at 6 places
        {"max_deductible_percentage": Decimal(-1)},
        {"max_deductible_percentage": Decimal("1.5")},  # > 100% would make premium negative
    ],
)
def test_rating_rules_rejects(overrides: dict[str, object]) -> None:
    with pytest.raises(RatingRulesError):
        _rules(**overrides)


def test_rating_rules_quantize_helpers() -> None:
    rules = _rules()
    assert rules.quantize_money(amount=Decimal("1.005")) == Decimal("1.01")
    assert rules.quantize_rate(rate=Decimal("0.1234565")) == Decimal("0.123457")


def test_rating_rules_accepts_maximum() -> None:
    rules = _rules(maximum_applied_rate=Decimal("0.5"))
    assert rules.maximum_applied_rate == Decimal("0.5")


def test_rating_rules_rejects_inverted_gis_band() -> None:
    with pytest.raises(RatingRulesError):
        _rules(gis_min_adjustment=Decimal("0.5"), gis_max_adjustment=Decimal("0.1"))
