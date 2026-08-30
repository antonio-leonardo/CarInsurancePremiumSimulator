"""``ListSimulations`` use case — cursor-paginated simulation history."""

from __future__ import annotations

from car_insurance.application.dto.calculate_premium_output import SimulationPage
from car_insurance.application.ports.simulation_repository import SimulationRepository

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


class ListSimulations:
    """Returns a page of history, or an empty page when persistence is disabled."""

    def __init__(self, *, repository: SimulationRepository) -> None:
        self._repository = repository

    def execute(self, *, cursor: str | None = None, limit: int = DEFAULT_LIMIT) -> SimulationPage:
        """Return at most ``limit`` records starting after ``cursor``."""

        bounded_limit = max(1, min(limit, MAX_LIMIT))
        return self._repository.list(cursor=cursor, limit=bounded_limit)
