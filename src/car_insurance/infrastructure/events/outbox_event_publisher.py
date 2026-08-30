"""``OutboxEventPublisher`` — stages events for the save transaction."""

from __future__ import annotations

from collections.abc import Sequence

from car_insurance.domain.events.premium_simulation_calculated import PremiumSimulationCalculated
from car_insurance.infrastructure.persistence.unit_of_work import UnitOfWork


class OutboxEventPublisher:
    """Hands events to the :class:`UnitOfWork`, which writes them with the row.

    The use case publishes *before* it saves, so the events are already staged
    when :meth:`SqlAlchemySimulationRepository.save` opens its transaction.
    """

    def __init__(self, *, unit_of_work: UnitOfWork) -> None:
        self._unit_of_work = unit_of_work

    def publish(self, *, events: Sequence[PremiumSimulationCalculated]) -> None:
        """Stage ``events`` on the unit of work."""

        self._unit_of_work.stage_events(events=events)
