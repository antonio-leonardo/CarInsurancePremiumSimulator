"""Integration tests for the optional PostgreSQL persistence path."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

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

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
testcontainers_postgres = pytest.importorskip("testcontainers.postgres")


@pytest.fixture(scope="module")
def engine() -> Iterator[object]:
    with testcontainers_postgres.PostgresContainer("postgres:16") as postgres:
        url = postgres.get_connection_url().replace("psycopg2", "psycopg")
        # Exercise the real Alembic migration, not metadata.create_all, so the
        # migration and the ORM models are proven to agree.
        alembic_config = Config(str(_REPO_ROOT / "alembic.ini"))
        alembic_config.set_main_option("sqlalchemy.url", url)
        command.upgrade(alembic_config, "head")

        engine = create_engine(url)
        yield engine
        engine.dispose()


@pytest.fixture
def _clean(engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE premium_simulations, event_outbox CASCADE"))


def _build_use_case(engine, *, rules) -> tuple[CalculatePremium, sessionmaker]:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    unit_of_work = UnitOfWork(session_factory=factory)
    repository = SqlAlchemySimulationRepository(session_factory=factory, unit_of_work=unit_of_work)
    use_case = CalculatePremium(
        clock=FixedClock(moment=datetime(2026, 1, 1, tzinfo=UTC)),
        event_publisher=OutboxEventPublisher(unit_of_work=unit_of_work),
        geographic_rate_provider=FakeGeographicRateProvider(),
        logger=FakeLogger(),
        persistence_failure_mode="fail_closed",
        repository=repository,
        rules=rules,
    )
    return use_case, factory


def _make_request():
    from car_insurance.application.dto.calculate_premium_input import (
        CalculatePremiumInput,
        CarInput,
    )

    return CalculatePremiumInput(
        broker_fee=Decimal(50),
        car=CarInput(make="Toyota", model="Corolla", value=Decimal(100000), year=2012),
        deductible_percentage=Decimal("0.10"),
    )


@pytest.mark.usefixtures("_clean")
def test_save_persists_row_and_outbox_in_one_transaction(engine, rules) -> None:
    use_case, factory = _build_use_case(engine, rules=rules)
    output = use_case.execute(request=_make_request())

    with factory() as session:
        rows = session.execute(text("SELECT count(*) FROM premium_simulations")).scalar()
        outbox = session.execute(text("SELECT count(*) FROM event_outbox")).scalar()
    assert rows == 1
    assert outbox == 1

    fetched = GetSimulation(
        repository=SqlAlchemySimulationRepository(
            session_factory=factory, unit_of_work=UnitOfWork(session_factory=factory)
        )
    ).execute(simulation_id=SimulationId(output.simulation_id))
    assert fetched is not None
    assert fetched.calculated_premium == Decimal("10850.00")


def test_migration_matches_orm_models(engine) -> None:
    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection,
            opts={"compare_type": True, "target_metadata": Base.metadata},
        )
        diff = compare_metadata(context, Base.metadata)
    assert diff == [], f"alembic autogenerate would emit changes: {diff}"


@pytest.mark.usefixtures("_clean")
def test_outbox_payload_has_the_event_fields_and_no_pii(engine, rules) -> None:
    from car_insurance.application.dto.calculate_premium_input import (
        CalculatePremiumInput,
        CarInput,
        RegistrationLocationInput,
    )

    use_case, factory = _build_use_case(engine, rules=rules)
    use_case.execute(
        request=CalculatePremiumInput(
            broker_fee=Decimal(50),
            car=CarInput(make="Toyota", model="Corolla", value=Decimal(100000), year=2012),
            deductible_percentage=Decimal("0.10"),
            registration_location=RegistrationLocationInput(
                country="US",
                city="London",
                line1="221B Baker Street",
                postal_code="NW16XE",
            ),
        )
    )

    with factory() as session:
        row = session.execute(
            text("SELECT event_type, payload, occurred_at, simulation_id FROM event_outbox")
        ).one()
    event_type, payload, _occurred_at, _sim_id = row
    assert event_type == "PremiumSimulationCalculated"
    assert set(payload) == {
        "applied_rate",
        "calculated_premium",
        "deductible_value",
        "location_country",
        "policy_limit",
        "rules_version",
        "vehicle_make",
        "vehicle_model",
        "vehicle_year",
    }
    assert payload["location_country"] == "US"
    blob = str(payload)
    assert "221B Baker Street" not in blob
    assert "NW16XE" not in blob
    assert "London" not in blob


def test_migration_upgrade_is_idempotent_and_reversible(engine) -> None:
    config = Config(str(_REPO_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", engine.url.render_as_string(hide_password=False))

    try:
        command.upgrade(config, "head")  # already at head -> no-op, must not error
        command.downgrade(config, "base")
        with engine.connect() as connection:
            remaining = connection.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_name IN ('premium_simulations', 'event_outbox')"
                )
            ).scalar()
        assert remaining == 0
    finally:
        command.upgrade(config, "head")  # restore for the rest of the module


@pytest.mark.usefixtures("_clean")
def test_list_paginates(engine, rules) -> None:
    use_case, factory = _build_use_case(engine, rules=rules)
    for _ in range(3):
        use_case.execute(request=_make_request())

    lister = ListSimulations(
        repository=SqlAlchemySimulationRepository(
            session_factory=factory, unit_of_work=UnitOfWork(session_factory=factory)
        )
    )
    first = lister.execute(cursor=None, limit=2)
    assert len(first.items) == 2
    assert first.next_cursor is not None
    second = lister.execute(cursor=first.next_cursor, limit=2)
    assert len(second.items) == 1
