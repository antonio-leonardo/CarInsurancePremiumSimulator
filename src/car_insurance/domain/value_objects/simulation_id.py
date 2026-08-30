"""``SimulationId`` value object — the identity of a :class:`PremiumSimulation`."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class SimulationId:
    """A UUID-backed identifier."""

    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID):
            raise TypeError("SimulationId value must be a UUID")

    def __str__(self) -> str:
        return str(self.value)

    @classmethod
    def from_string(cls, *, value: str) -> SimulationId:
        """Parse a :class:`SimulationId` from its canonical string form."""

        return cls(UUID(value))

    @classmethod
    def new(cls) -> SimulationId:
        """Generate a fresh random :class:`SimulationId`."""

        return cls(uuid4())
