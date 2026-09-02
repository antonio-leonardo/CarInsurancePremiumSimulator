"""``PremiumSimulation`` aggregate root."""

from __future__ import annotations

from datetime import datetime

from car_insurance.domain.errors import (
    BrokerFeeError,
    CurrencyMismatchError,
    DeductibleOutOfRangeError,
    GeographicRateAdjustmentError,
    VehicleYearError,
)
from car_insurance.domain.events.premium_simulation_calculated import PremiumSimulationCalculated
from car_insurance.domain.services.policy_limit_calculator import PolicyLimitCalculator
from car_insurance.domain.services.premium_calculator import PremiumCalculator
from car_insurance.domain.services.rate_calculator import RateCalculator
from car_insurance.domain.value_objects.address import Address
from car_insurance.domain.value_objects.geographic_rate_adjustment import GeographicRateAdjustment
from car_insurance.domain.value_objects.money import Money
from car_insurance.domain.value_objects.percentage import Percentage
from car_insurance.domain.value_objects.rating_rules import RatingRules
from car_insurance.domain.value_objects.simulation_id import SimulationId
from car_insurance.domain.value_objects.vehicle_snapshot import VehicleSnapshot


class PremiumSimulation:
    """A fully computed premium quote.

    Instances are only ever produced by :meth:`calculate`, which runs the three
    domain services in canonical order, assembles the results as value objects
    and records a :class:`PremiumSimulationCalculated` event.  The aggregate
    performs no I/O.
    """

    __slots__ = (
        "_events",
        "applied_rate",
        "calculated_premium",
        "deductible_value",
        "id",
        "occurred_at",
        "policy_limit",
        "registration_country",
        "rules_version",
        "vehicle",
    )

    def __init__(
        self,
        *,
        applied_rate: Percentage,
        calculated_premium: Money,
        deductible_value: Money,
        occurred_at: datetime,
        policy_limit: Money,
        registration_country: str | None,
        rules_version: str,
        simulation_id: SimulationId,
        vehicle: VehicleSnapshot,
    ) -> None:
        self._events: list[PremiumSimulationCalculated] = []
        self.applied_rate = applied_rate
        self.calculated_premium = calculated_premium
        self.deductible_value = deductible_value
        self.id = simulation_id
        self.occurred_at = occurred_at
        self.policy_limit = policy_limit
        self.registration_country = registration_country
        self.rules_version = rules_version
        self.vehicle = vehicle

    def _record(self, event: PremiumSimulationCalculated) -> None:
        self._events.append(event)

    @classmethod
    def calculate(
        cls,
        *,
        broker_fee: Money,
        deductible_percentage: Percentage,
        geographic_adjustment: GeographicRateAdjustment,
        now: datetime,
        registration_location: Address | None,
        rules: RatingRules,
        vehicle: VehicleSnapshot,
    ) -> PremiumSimulation:
        """Build a consistent :class:`PremiumSimulation` from validated inputs."""

        if vehicle.year.is_after(year=now.year):
            raise VehicleYearError("vehicle year must not be in the future")
        # Defense in depth: a buggy or hostile GeographicRateProvider adapter
        # could hand us an adjustment outside the configured band. The adapter's
        # ``GeographicRateAdjustment.within`` already guards, but the aggregate
        # must not trust its collaborators blindly. A *zero* adjustment is the
        # neutral element (GIS disabled, or no provider result) and is always
        # accepted, even if the configured band happens to exclude zero.
        if geographic_adjustment.value != 0 and not (
            rules.gis_min_adjustment <= geographic_adjustment.value <= rules.gis_max_adjustment
        ):
            raise GeographicRateAdjustmentError("geographic adjustment outside the configured band")
        if broker_fee.currency != rules.currency_code:
            raise CurrencyMismatchError("broker_fee currency differs from configured currency")
        if vehicle.value.currency != rules.currency_code:
            raise CurrencyMismatchError("vehicle currency differs from configured currency")
        if broker_fee.amount < 0:
            raise BrokerFeeError("broker_fee must be greater than or equal to zero")
        if (
            deductible_percentage.value < 0
            or deductible_percentage.value > rules.max_deductible_percentage
        ):
            raise DeductibleOutOfRangeError(
                f"deductible_percentage must be between 0 and {rules.max_deductible_percentage}"
            )

        applied_rate = RateCalculator.calculate(
            calculation_year=now.year,
            geographic_adjustment=geographic_adjustment,
            rules=rules,
            vehicle=vehicle,
        )
        premium = PremiumCalculator.calculate(
            applied_rate=applied_rate,
            broker_fee=broker_fee,
            deductible_percentage=deductible_percentage,
            rules=rules,
            vehicle=vehicle,
        )
        limit = PolicyLimitCalculator.calculate(
            deductible_percentage=deductible_percentage,
            rules=rules,
            vehicle=vehicle,
        )

        country = registration_location.country if registration_location is not None else None
        simulation = cls(
            applied_rate=applied_rate,
            calculated_premium=Money(premium.calculated_premium, rules.currency_code),
            deductible_value=Money(limit.deductible_value, rules.currency_code),
            occurred_at=now,
            policy_limit=Money(limit.policy_limit, rules.currency_code),
            registration_country=country,
            rules_version=rules.rules_version,
            simulation_id=SimulationId.new(),
            vehicle=vehicle,
        )
        simulation._record(
            PremiumSimulationCalculated(
                applied_rate=applied_rate.value,
                calculated_premium=premium.calculated_premium,
                deductible_value=limit.deductible_value,
                location_country=country,
                occurred_at=now,
                policy_limit=limit.policy_limit,
                rules_version=rules.rules_version,
                simulation_id=simulation.id,
                vehicle_make=vehicle.make,
                vehicle_model=vehicle.model,
                vehicle_year=vehicle.year.value,
            )
        )
        return simulation

    def pull_events(self) -> list[PremiumSimulationCalculated]:
        """Return the recorded events and clear the internal buffer."""

        events = list(self._events)
        self._events.clear()
        return events
