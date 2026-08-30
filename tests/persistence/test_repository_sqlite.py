"""Repository / unit-of-work / outbox tests against in-memory SQLite.

These exercise the same adapter code paths the PostgreSQL integration tests use,
without needing a container, so they run in the default suite.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from car_insurance.application.dto.calculate_premium_input import (
    CalculatePremiumInput,
    CarInput,
)
from car_insurance.application.ports.simulation_repository import (
    InvalidCursorError,
    SimulationRepositoryError,
)
from car_insurance.application.use_cases.calculate_premium import CalculatePremium
from car_insurance.application.use_cases.get_simulation import GetSimulation
from car_insurance.application.use_cases.list_simulations import ListSimulations
from car_insurance.domain.value_objects.simulation_id import SimulationId
from car_insurance.infrastructure.events.outbox_event_publisher import (
    OutboxEventPublisher,
)
from car_insurance.infrastructure.persistence.models import Base
from car_insurance.infrastructure.persistence.sqlalchemy_repository import (
    SqlAlchemySimulationRepository,
)
from car_insurance.infrastructure.persistence.unit_of_work import UnitOfWork
from tests.conftest import FakeGeographicRateProvider, FakeLogger, FixedClock


@pytest.fixture
def factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _request(year: int = 2012) -> CalculatePremiumInput:
    return CalculatePremiumInput(
        broker_fee=Decimal(50),
        car=CarInput(make="Toyota", model="Corolla", value=Decimal(100000), year=year),
        deductible_percentage=Decimal("0.10"),
    )


def _use_case(factory, rules) -> CalculatePremium:
    unit_of_work = UnitOfWork(session_factory=factory)
    return CalculatePremium(
        clock=FixedClock(moment=datetime(2026, 1, 1, tzinfo=UTC)),
        event_publisher=OutboxEventPublisher(unit_of_work=unit_of_work),
        geographic_rate_provider=FakeGeographicRateProvider(),
        logger=FakeLogger(),
        persistence_failure_mode="fail_closed",
        repository=SqlAlchemySimulationRepository(
            session_factory=factory, unit_of_work=unit_of_work
        ),
        rules=rules,
    )


def test_save_writes_row_and_outbox_together(factory, rules) -> None:
    output = _use_case(factory, rules).execute(request=_request())

    with factory() as session:
        rows = session.execute(text("SELECT count(*) FROM premium_simulations")).scalar()
        outbox = session.execute(text("SELECT count(*) FROM event_outbox")).scalar()
    assert rows == 1
    assert outbox == 1

    repository = SqlAlchemySimulationRepository(
        session_factory=factory, unit_of_work=UnitOfWork(session_factory=factory)
    )
    fetched = GetSimulation(repository=repository).execute(
        simulation_id=SimulationId(output.simulation_id)
    )
    assert fetched is not None
    assert fetched.calculated_premium == Decimal("10850.00")
    assert fetched.car.make == "Toyota"


def test_get_missing_returns_none(factory) -> None:
    repository = SqlAlchemySimulationRepository(
        session_factory=factory, unit_of_work=UnitOfWork(session_factory=factory)
    )
    assert repository.get(simulation_id=SimulationId.new()) is None


def test_list_paginates_with_cursor(factory, rules) -> None:
    use_case = _use_case(factory, rules)
    for _ in range(3):
        use_case.execute(request=_request())

    repository = SqlAlchemySimulationRepository(
        session_factory=factory, unit_of_work=UnitOfWork(session_factory=factory)
    )
    lister = ListSimulations(repository=repository)
    first = lister.execute(cursor=None, limit=2)
    assert len(first.items) == 2
    assert first.next_cursor is not None

    second = lister.execute(cursor=first.next_cursor, limit=2)
    assert len(second.items) == 1
    assert second.next_cursor is None


def test_invalid_cursor_raises(factory) -> None:
    repository = SqlAlchemySimulationRepository(
        session_factory=factory, unit_of_work=UnitOfWork(session_factory=factory)
    )
    with pytest.raises(InvalidCursorError):
        repository.list(cursor="not-a-valid-cursor", limit=10)


def test_transaction_rolls_back_on_error(factory) -> None:
    unit_of_work = UnitOfWork(session_factory=factory)
    with pytest.raises(RuntimeError), unit_of_work.transaction() as session:
        session.execute(text("SELECT 1"))
        raise RuntimeError("boom")


def test_db_failures_become_repository_errors() -> None:
    from sqlalchemy.exc import OperationalError

    def _broken_factory():
        raise OperationalError("SELECT 1", {}, Exception("connection lost"))

    repository = SqlAlchemySimulationRepository(
        session_factory=_broken_factory,
        unit_of_work=UnitOfWork(session_factory=_broken_factory),
    )
    with pytest.raises(SimulationRepositoryError):
        repository.get(simulation_id=SimulationId.new())
    with pytest.raises(SimulationRepositoryError):
        repository.list(cursor=None, limit=10)


def test_save_failure_becomes_repository_error(factory, rules) -> None:
    use_case = _use_case(factory, rules)
    with factory() as session:  # drop the tables so the INSERT fails mid-transaction
        session.execute(text("DROP TABLE event_outbox"))
        session.execute(text("DROP TABLE premium_simulations"))
        session.commit()
    with pytest.raises(SimulationRepositoryError):
        use_case.execute(request=_request())
