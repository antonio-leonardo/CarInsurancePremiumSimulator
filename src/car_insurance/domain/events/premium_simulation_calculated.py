"""``PremiumSimulationCalculated`` domain event."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from car_insurance.domain.value_objects.simulation_id import SimulationId


@dataclass(frozen=True, slots=True)
class PremiumSimulationCalculated:
    """Emitted once a :class:`PremiumSimulation` has been fully calculated.

    It deliberately never carries a full address, the raw ``broker_fee`` or the
    raw ``deductible_percentage``; if a location is included it is the country
    code only.
    """

    applied_rate: Decimal
    calculated_premium: Decimal
    deductible_value: Decimal
    location_country: str | None
    occurred_at: datetime
    policy_limit: Decimal
    rules_version: str
    simulation_id: SimulationId
    vehicle_make: str
    vehicle_model: str
    vehicle_year: int
