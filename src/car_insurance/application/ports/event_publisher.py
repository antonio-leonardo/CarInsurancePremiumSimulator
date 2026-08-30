"""``EventPublisher`` port — how domain events leave the application."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from car_insurance.domain.events.premium_simulation_calculated import PremiumSimulationCalculated


class EventPublisher(Protocol):
    """Publishes the events pulled from an aggregate after a successful use case."""

    def publish(self, *, events: Sequence[PremiumSimulationCalculated]) -> None: ...
