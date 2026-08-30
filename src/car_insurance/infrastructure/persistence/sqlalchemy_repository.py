"""``SqlAlchemySimulationRepository`` — PostgreSQL-backed persistence adapter."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from car_insurance.application.dto.calculate_premium_output import (
    CalculatePremiumOutput,
    CarOutput,
    SimulationPage,
)
from car_insurance.application.ports.simulation_repository import (
    InvalidCursorError,
    SimulationRepositoryError,
)
from car_insurance.domain.aggregates.premium_simulation import PremiumSimulation
from car_insurance.domain.value_objects.simulation_id import SimulationId
from car_insurance.infrastructure.persistence.models import (
    EventOutboxRecord,
    PremiumSimulationRecord,
)
from car_insurance.infrastructure.persistence.unit_of_work import UnitOfWork


def _decode_cursor(*, cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        created_at_raw, simulation_id = raw.split("|", 1)
        return datetime.fromisoformat(created_at_raw), UUID(simulation_id)
    except (ValueError, binascii.Error) as exc:
        raise InvalidCursorError(f"invalid cursor: {cursor}") from exc


def _encode_cursor(*, record: PremiumSimulationRecord) -> str:
    raw = f"{record.created_at.isoformat()}|{record.id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def _to_output(*, record: PremiumSimulationRecord) -> CalculatePremiumOutput:
    return CalculatePremiumOutput(
        applied_rate=record.applied_rate,
        calculated_premium=record.calculated_premium,
        car=CarOutput(
            make=record.vehicle_make,
            model=record.vehicle_model,
            value=record.vehicle_value,
            year=record.vehicle_year,
        ),
        created_at=record.created_at,
        deductible_value=record.deductible_value,
        policy_limit=record.policy_limit,
        rules_version=record.rules_version,
        simulation_id=record.id,
    )


class SqlAlchemySimulationRepository:
    """Reads/writes :class:`PremiumSimulation` data and its outbox rows."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        unit_of_work: UnitOfWork,
    ) -> None:
        self._session_factory = session_factory
        self._unit_of_work = unit_of_work

    def get(self, *, simulation_id: SimulationId) -> CalculatePremiumOutput | None:
        """Fetch one record by id."""

        try:
            with self._session_factory() as session:
                record = session.get(PremiumSimulationRecord, simulation_id.value)
                return _to_output(record=record) if record is not None else None
        except SQLAlchemyError as exc:
            raise SimulationRepositoryError("failed to read simulation") from exc

    def list(self, *, cursor: str | None, limit: int) -> SimulationPage:
        """Return a descending-by-time page of history."""

        try:
            with self._session_factory() as session:
                statement = select(PremiumSimulationRecord).order_by(
                    PremiumSimulationRecord.created_at.desc(),
                    PremiumSimulationRecord.id.desc(),
                )
                if cursor is not None:
                    created_before, simulation_id = _decode_cursor(cursor=cursor)
                    statement = statement.where(
                        or_(
                            PremiumSimulationRecord.created_at < created_before,
                            (PremiumSimulationRecord.created_at == created_before)
                            & (PremiumSimulationRecord.id < simulation_id),
                        )
                    )
                records = list(session.scalars(statement.limit(limit + 1)))
            has_more = len(records) > limit
            page = records[:limit]
            next_cursor = _encode_cursor(record=page[-1]) if has_more and page else None
            return SimulationPage(
                items=tuple(_to_output(record=record) for record in page),
                next_cursor=next_cursor,
            )
        except SQLAlchemyError as exc:
            raise SimulationRepositoryError("failed to list simulations") from exc

    def save(self, *, simulation: PremiumSimulation) -> None:
        """Persist the simulation row and its outbox events in one transaction."""

        try:
            with self._unit_of_work.transaction() as session:
                session.add(
                    PremiumSimulationRecord(
                        applied_rate=simulation.applied_rate.value,
                        calculated_premium=simulation.calculated_premium.amount,
                        created_at=simulation.occurred_at,
                        currency_code=simulation.calculated_premium.currency,
                        deductible_value=simulation.deductible_value.amount,
                        id=simulation.id.value,
                        location_country=simulation.registration_country,
                        policy_limit=simulation.policy_limit.amount,
                        rules_version=simulation.rules_version,
                        vehicle_make=simulation.vehicle.make,
                        vehicle_model=simulation.vehicle.model,
                        vehicle_value=simulation.vehicle.value.amount,
                        vehicle_year=simulation.vehicle.year.value,
                    )
                )
                session.flush()
                for event in self._unit_of_work.drain_events():
                    session.add(
                        EventOutboxRecord(
                            event_type="PremiumSimulationCalculated",
                            occurred_at=event.occurred_at,
                            payload={
                                "applied_rate": str(event.applied_rate),
                                "calculated_premium": str(event.calculated_premium),
                                "deductible_value": str(event.deductible_value),
                                "location_country": event.location_country,
                                "policy_limit": str(event.policy_limit),
                                "rules_version": event.rules_version,
                                "vehicle_make": event.vehicle_make,
                                "vehicle_model": event.vehicle_model,
                                "vehicle_year": event.vehicle_year,
                            },
                            simulation_id=event.simulation_id.value,
                        )
                    )
        except SQLAlchemyError as exc:
            raise SimulationRepositoryError("failed to save simulation") from exc
