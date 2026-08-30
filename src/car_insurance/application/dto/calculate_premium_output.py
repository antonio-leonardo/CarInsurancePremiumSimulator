"""Output DTO for the premium use cases (framework-free primitives)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CarOutput:
    """The echoed vehicle facts — exactly ``make``, ``model``, ``value``, ``year``."""

    make: str
    model: str
    value: Decimal
    year: int


@dataclass(frozen=True, slots=True)
class CalculatePremiumOutput:
    """The full result of a simulation.

    The HTTP ``calculate`` response projects only ``applied_rate``,
    ``calculated_premium``, ``car``, ``deductible_value`` and ``policy_limit``;
    the history endpoints use the remaining fields as well.
    """

    applied_rate: Decimal
    calculated_premium: Decimal
    car: CarOutput
    created_at: datetime
    deductible_value: Decimal
    policy_limit: Decimal
    rules_version: str
    simulation_id: UUID


@dataclass(frozen=True, slots=True)
class SimulationPage:
    """A cursor-paginated slice of simulation history."""

    items: tuple[CalculatePremiumOutput, ...]
    next_cursor: str | None
