"""``CalculatePremium`` use case — the single orchestration entry point."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from car_insurance.application.dto.calculate_premium_input import CalculatePremiumInput
from car_insurance.application.dto.calculate_premium_output import (
    CalculatePremiumOutput,
    CarOutput,
)
from car_insurance.application.ports.clock import Clock
from car_insurance.application.ports.event_publisher import EventPublisher
from car_insurance.application.ports.geographic_rate_provider import GeographicRateProvider
from car_insurance.application.ports.logger import Logger
from car_insurance.application.ports.simulation_repository import (
    SimulationRepository,
    SimulationRepositoryError,
)
from car_insurance.domain.aggregates.premium_simulation import PremiumSimulation
from car_insurance.domain.errors import DomainError
from car_insurance.domain.value_objects.address import Address
from car_insurance.domain.value_objects.geographic_rate_adjustment import GeographicRateAdjustment
from car_insurance.domain.value_objects.money import Money
from car_insurance.domain.value_objects.percentage import Percentage
from car_insurance.domain.value_objects.rating_rules import RatingRules
from car_insurance.domain.value_objects.vehicle_snapshot import VehicleSnapshot
from car_insurance.domain.value_objects.vehicle_year import VehicleYear

_FAIL_OPEN = "fail_open"


class CalculatePremium:
    """Coordinates validation, the domain calculation and its side effects."""

    def __init__(
        self,
        *,
        clock: Clock,
        event_publisher: EventPublisher,
        geographic_rate_provider: GeographicRateProvider,
        logger: Logger,
        maximum_broker_fee: Decimal,
        maximum_vehicle_value: Decimal,
        persistence_failure_mode: str,
        repository: SimulationRepository,
        rules: RatingRules,
    ) -> None:
        self._clock = clock
        self._event_publisher = event_publisher
        self._geographic_rate_provider = geographic_rate_provider
        self._logger = logger
        self._maximum_broker_fee = maximum_broker_fee
        self._maximum_vehicle_value = maximum_vehicle_value
        self._persistence_failure_mode = persistence_failure_mode
        self._repository = repository
        self._rules = rules

    def _to_decimal(self, *, field: str, value: Decimal | float | int | str) -> Decimal:
        try:
            coerced = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise DomainError(f"{field} is not a valid number") from exc
        if not coerced.is_finite():
            raise DomainError(f"{field} must be a finite number")
        return coerced

    def execute(self, *, request: CalculatePremiumInput) -> CalculatePremiumOutput:
        """Produce a quote for ``request`` or raise a :class:`DomainError`."""

        rules = self._rules
        now = self._clock.now()

        vehicle_value = self._to_decimal(field="car.value", value=request.car.value)
        if vehicle_value > self._maximum_vehicle_value:
            raise DomainError(f"car.value must not exceed {self._maximum_vehicle_value}")
        broker_fee_amount = self._to_decimal(field="broker_fee", value=request.broker_fee)
        if broker_fee_amount > self._maximum_broker_fee:
            raise DomainError(f"broker_fee must not exceed {self._maximum_broker_fee}")

        vehicle = VehicleSnapshot(
            make=request.car.make,
            model=request.car.model,
            value=Money(vehicle_value, rules.currency_code),
            year=VehicleYear.create(minimum=rules.min_vehicle_year, value=request.car.year),
        )
        if vehicle.year.is_after(year=now.year):
            raise DomainError("car.year must not be in the future")

        broker_fee = Money(broker_fee_amount, rules.currency_code)
        deductible_percentage = Percentage(
            self._to_decimal(
                field="deductible_percentage",
                value=request.deductible_percentage,
            )
        )

        address: Address | None = None
        if request.registration_location is not None:
            location = request.registration_location
            address = Address(
                country=location.country,
                city=location.city,
                line1=location.line1,
                postal_code=location.postal_code,
                region=location.region,
            )

        adjustment = (
            self._geographic_rate_provider.adjustment_for(address=address)
            if address is not None
            else GeographicRateAdjustment.zero()
        )

        simulation = PremiumSimulation.calculate(
            broker_fee=broker_fee,
            deductible_percentage=deductible_percentage,
            geographic_adjustment=adjustment,
            now=now,
            registration_location=address,
            rules=rules,
            vehicle=vehicle,
        )

        logger = self._logger.bind(simulation_id=str(simulation.id))
        events = simulation.pull_events()
        self._event_publisher.publish(events=events)
        try:
            self._repository.save(simulation=simulation)
        except SimulationRepositoryError:
            if self._persistence_failure_mode == _FAIL_OPEN:
                logger.error("persistence.failed")
            else:
                raise

        logger.info(
            "premium.calculated",
            applied_rate=str(simulation.applied_rate.value),
            calculated_premium=str(simulation.calculated_premium.amount),
            country=simulation.registration_country,
            vehicle_year=vehicle.year.value,
        )

        return CalculatePremiumOutput(
            applied_rate=simulation.applied_rate.value,
            calculated_premium=simulation.calculated_premium.amount,
            car=CarOutput(
                make=vehicle.make,
                model=vehicle.model,
                value=vehicle.value.amount,
                year=vehicle.year.value,
            ),
            created_at=simulation.occurred_at,
            deductible_value=simulation.deductible_value.amount,
            policy_limit=simulation.policy_limit.amount,
            rules_version=simulation.rules_version,
            simulation_id=simulation.id.value,
        )
