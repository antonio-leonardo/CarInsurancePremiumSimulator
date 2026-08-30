"""Canonical acceptance examples, boundary table and invariant tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from car_insurance.domain.aggregates.premium_simulation import PremiumSimulation
from car_insurance.domain.errors import (
    BrokerFeeError,
    DeductibleOutOfRangeError,
    VehicleSnapshotError,
)
from car_insurance.domain.value_objects.geographic_rate_adjustment import (
    GeographicRateAdjustment,
)
from car_insurance.domain.value_objects.money import Money
from car_insurance.domain.value_objects.percentage import Percentage
from car_insurance.domain.value_objects.vehicle_snapshot import VehicleSnapshot

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _simulate(
    *,
    broker_fee: str = "50",
    deductible: str = "0.10",
    rules,
    value: str = "100000",
    year: int = 2016,
) -> PremiumSimulation:
    vehicle = VehicleSnapshot(
        make="Toyota",
        model="Corolla",
        value=Money(Decimal(value), "USD"),
        year=_year(year),
    )
    return PremiumSimulation.calculate(
        broker_fee=Money(Decimal(broker_fee), "USD"),
        deductible_percentage=Percentage(Decimal(deductible)),
        geographic_adjustment=GeographicRateAdjustment.zero(),
        now=_NOW,
        registration_location=None,
        rules=rules,
        vehicle=vehicle,
    )


def _year(value: int):
    from car_insurance.domain.value_objects.vehicle_year import VehicleYear

    return VehicleYear(value)


def test_example_a(rules) -> None:
    simulation = _simulate(rules=rules, value="100000", year=2016)

    assert simulation.applied_rate.value == Decimal("0.100000")
    assert simulation.calculated_premium.amount == Decimal("9050.00")
    assert simulation.deductible_value.amount == Decimal("10000.00")
    assert simulation.policy_limit.amount == Decimal("90000.00")


def test_example_b(rules) -> None:
    simulation = _simulate(rules=rules, value="100000", year=2012)

    assert simulation.applied_rate.value == Decimal("0.120000")
    assert simulation.calculated_premium.amount == Decimal("10850.00")
    assert simulation.deductible_value.amount == Decimal("10000.00")
    assert simulation.policy_limit.amount == Decimal("90000.00")


@pytest.mark.parametrize(
    ("value", "expected_value_rate"),
    [
        ("9999.99", Decimal(0)),
        ("10000.00", Decimal("0.005")),
        ("19999.99", Decimal("0.005")),
        ("20000.00", Decimal("0.010")),
        ("100000.00", Decimal("0.050")),
    ],
)
def test_value_band_boundaries(expected_value_rate, rules, value) -> None:
    # car_age == 0 so the age component is zero and applied_rate == value_rate.
    simulation = _simulate(rules=rules, value=value, year=2026)
    assert simulation.applied_rate.value == expected_value_rate.quantize(Decimal("0.000001"))


@pytest.mark.parametrize("car_age", [0, 1, 10, 14])
def test_age_component(car_age, rules) -> None:
    simulation = _simulate(rules=rules, value="9999.99", year=2026 - car_age)
    assert simulation.applied_rate.value == (Decimal(car_age) * Decimal("0.005")).quantize(
        Decimal("0.000001")
    )


def test_full_deductible(rules) -> None:
    simulation = _simulate(rules=rules, deductible="1.0", broker_fee="50", value="100000")

    assert simulation.calculated_premium.amount == Decimal("50.00")
    assert simulation.policy_limit.amount == Decimal("0.00")


def test_negative_broker_fee_rejected(rules) -> None:
    with pytest.raises(BrokerFeeError):
        _simulate(rules=rules, broker_fee="-1")


def test_deductible_above_maximum_rejected(rules) -> None:
    with pytest.raises(DeductibleOutOfRangeError):
        _simulate(rules=rules, deductible="1.5")


def test_zero_vehicle_value_rejected() -> None:
    with pytest.raises(VehicleSnapshotError):
        VehicleSnapshot(
            make="Toyota",
            model="Corolla",
            value=Money(Decimal(0), "USD"),
            year=_year(2020),
        )


def test_currency_mismatch_rejected(rules) -> None:
    from car_insurance.domain.errors import CurrencyMismatchError

    vehicle = VehicleSnapshot(
        make="Toyota",
        model="Corolla",
        value=Money(Decimal(100000), "USD"),
        year=_year(2016),
    )
    with pytest.raises(CurrencyMismatchError):
        PremiumSimulation.calculate(
            broker_fee=Money(Decimal(50), "EUR"),
            deductible_percentage=Percentage(Decimal("0.1")),
            geographic_adjustment=GeographicRateAdjustment.zero(),
            now=_NOW,
            registration_location=None,
            rules=rules,
            vehicle=vehicle,
        )
    with pytest.raises(CurrencyMismatchError):
        PremiumSimulation.calculate(
            broker_fee=Money(Decimal(50), "USD"),
            deductible_percentage=Percentage(Decimal("0.1")),
            geographic_adjustment=GeographicRateAdjustment.zero(),
            now=_NOW,
            registration_location=None,
            rules=rules,
            vehicle=VehicleSnapshot(
                make="Toyota",
                model="Corolla",
                value=Money(Decimal(100000), "EUR"),
                year=_year(2016),
            ),
        )


def test_aggregate_rejects_a_future_model_year(rules) -> None:
    from car_insurance.domain.errors import VehicleYearError

    with pytest.raises(VehicleYearError):
        PremiumSimulation.calculate(
            broker_fee=Money(Decimal(50), "USD"),
            deductible_percentage=Percentage(Decimal("0.1")),
            geographic_adjustment=GeographicRateAdjustment.zero(),
            now=_NOW,  # year 2026
            registration_location=None,
            rules=rules,
            vehicle=VehicleSnapshot(
                make="Toyota",
                model="Corolla",
                value=Money(Decimal(100000), "USD"),
                year=_year(2027),
            ),
        )


def test_registration_country_recorded(rules) -> None:
    from car_insurance.domain.value_objects.address import Address

    vehicle = VehicleSnapshot(
        make="Toyota",
        model="Corolla",
        value=Money(Decimal(100000), "USD"),
        year=_year(2016),
    )
    simulation = PremiumSimulation.calculate(
        broker_fee=Money(Decimal(50), "USD"),
        deductible_percentage=Percentage(Decimal("0.1")),
        geographic_adjustment=GeographicRateAdjustment.zero(),
        now=_NOW,
        registration_location=Address(country="us"),
        rules=rules,
        vehicle=vehicle,
    )
    assert simulation.registration_country == "US"
    assert simulation.pull_events()[0].location_country == "US"


def test_event_recorded(rules) -> None:
    simulation = _simulate(rules=rules)
    events = simulation.pull_events()

    assert len(events) == 1
    assert events[0].rules_version == "2026.08.0"
    assert events[0].vehicle_year == 2016
    assert simulation.pull_events() == []
