"""A tiny synchronous Unit of Work coordinating the save + outbox transaction."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from sqlalchemy.orm import Session, sessionmaker

from car_insurance.domain.events.premium_simulation_calculated import PremiumSimulationCalculated


class UnitOfWork:
    """Owns one request-scoped list of staged events and hands out a session.

    ``OutboxEventPublisher`` stages events here; ``SqlAlchemySimulationRepository``
    drains them inside the same transaction that writes the simulation row.
    """

    def __init__(self, *, session_factory: sessionmaker[Session] | None) -> None:
        # ``None`` when persistence is disabled: the null repository / logging
        # publisher never open a transaction, so no engine is ever created.
        self._pending: list[PremiumSimulationCalculated] = []
        self._session_factory = session_factory

    def drain_events(self) -> list[PremiumSimulationCalculated]:
        """Return the staged events and clear the buffer."""

        events = list(self._pending)
        self._pending.clear()
        return events

    def stage_events(self, *, events: Sequence[PremiumSimulationCalculated]) -> None:
        """Buffer events to be written in the next transaction."""

        self._pending.extend(events)

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        """Yield a session, committing on success and rolling back on error."""

        if self._session_factory is None:  # pragma: no cover - guarded by wiring
            raise RuntimeError("unit of work has no session factory (persistence disabled)")
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
