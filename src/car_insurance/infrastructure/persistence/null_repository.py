"""``NullSimulationRepository`` — the adapter used when persistence is disabled."""

from __future__ import annotations

from car_insurance.application.dto.calculate_premium_output import (
    CalculatePremiumOutput,
    SimulationPage,
)
from car_insurance.domain.aggregates.premium_simulation import PremiumSimulation
from car_insurance.domain.value_objects.simulation_id import SimulationId


class NullSimulationRepository:
    """``save`` is a no-op; ``get``/``list`` always return "nothing"."""

    def get(self, *, simulation_id: SimulationId) -> CalculatePremiumOutput | None:
        """Always ``None`` — nothing is ever stored."""

        return None

    def list(self, *, cursor: str | None, limit: int) -> SimulationPage:
        """Always an empty page."""

        return SimulationPage(items=(), next_cursor=None)

    def save(self, *, simulation: PremiumSimulation) -> None:
        """Discard the aggregate — persistence is turned off."""
