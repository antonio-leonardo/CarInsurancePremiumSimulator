"""``SimulationRepository`` port — optional persistence of computed simulations."""

from __future__ import annotations

from typing import Protocol

from car_insurance.application.dto.calculate_premium_output import (
    CalculatePremiumOutput,
    SimulationPage,
)
from car_insurance.domain.aggregates.premium_simulation import PremiumSimulation
from car_insurance.domain.value_objects.simulation_id import SimulationId


class InvalidCursorError(Exception):
    """Raised when a client supplies a pagination cursor that cannot be decoded.

    This is a *client* error (mapped to HTTP 422), unlike
    :class:`SimulationRepositoryError` which signals an infrastructure failure.
    """


class SimulationRepositoryError(Exception):
    """Raised when a repository operation fails (mapped per ``PERSISTENCE_FAILURE_MODE``)."""


class SimulationRepository(Protocol):
    """Synchronous store for :class:`PremiumSimulation` aggregates.

    The ``Null`` adapter makes ``save`` a no-op and returns empty reads; the
    SQLAlchemy adapter persists to PostgreSQL within a unit of work.
    """

    def get(self, *, simulation_id: SimulationId) -> CalculatePremiumOutput | None: ...

    def list(self, *, cursor: str | None, limit: int) -> SimulationPage: ...

    def save(self, *, simulation: PremiumSimulation) -> None: ...
