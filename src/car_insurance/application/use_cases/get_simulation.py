"""``GetSimulation`` use case — fetch one persisted simulation by id."""

from __future__ import annotations

from car_insurance.application.dto.calculate_premium_output import CalculatePremiumOutput
from car_insurance.application.ports.simulation_repository import SimulationRepository
from car_insurance.domain.value_objects.simulation_id import SimulationId


class GetSimulation:
    """Returns the stored record, or ``None`` when persistence is disabled/absent."""

    def __init__(self, *, repository: SimulationRepository) -> None:
        self._repository = repository

    def execute(self, *, simulation_id: SimulationId) -> CalculatePremiumOutput | None:
        """Look up ``simulation_id`` in the repository."""

        return self._repository.get(simulation_id=simulation_id)
