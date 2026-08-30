"""Composition root — every object graph the routers need is assembled here.

Definitions are alphabetical like the rest of ``src/``.  This is safe because
``from __future__ import annotations`` turns every ``Annotated[..., Depends(x)]``
into a string that FastAPI only resolves (via ``get_type_hints``) when the
routes are registered, long after this module has finished importing; the
function bodies resolve their collaborators at call time.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from car_insurance.application.ports.clock import Clock
from car_insurance.application.ports.event_publisher import EventPublisher
from car_insurance.application.ports.geographic_rate_provider import GeographicRateProvider
from car_insurance.application.ports.logger import Logger
from car_insurance.application.ports.simulation_repository import SimulationRepository
from car_insurance.application.use_cases.calculate_premium import CalculatePremium
from car_insurance.application.use_cases.get_simulation import GetSimulation
from car_insurance.application.use_cases.list_simulations import ListSimulations
from car_insurance.domain.value_objects.rating_rules import RatingRules
from car_insurance.infrastructure.config.rules_factory import build_rating_rules
from car_insurance.infrastructure.config.settings import Settings
from car_insurance.infrastructure.events.logging_event_publisher import LoggingEventPublisher
from car_insurance.infrastructure.events.outbox_event_publisher import OutboxEventPublisher
from car_insurance.infrastructure.gis.http_geographic_rate_provider import (
    HttpGeographicRateProvider,
)
from car_insurance.infrastructure.gis.null_geographic_rate_provider import (
    NullGeographicRateProvider,
)
from car_insurance.infrastructure.observability.structlog_logger import StructlogLogger
from car_insurance.infrastructure.persistence.null_repository import NullSimulationRepository
from car_insurance.infrastructure.persistence.sqlalchemy_repository import (
    SqlAlchemySimulationRepository,
)
from car_insurance.infrastructure.persistence.unit_of_work import UnitOfWork
from car_insurance.infrastructure.time.system_clock import SystemClock


@lru_cache(maxsize=1)
def _engine() -> Engine:
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        return create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(
        settings.database_url,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
    )


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=_engine(), expire_on_commit=False)


def get_calculate_premium(
    clock: Annotated[Clock, Depends(get_clock)],
    event_publisher: Annotated[EventPublisher, Depends(get_event_publisher)],
    geographic_rate_provider: Annotated[
        GeographicRateProvider, Depends(get_geographic_rate_provider)
    ],
    logger: Annotated[Logger, Depends(get_logger)],
    repository: Annotated[SimulationRepository, Depends(get_repository)],
    rules: Annotated[RatingRules, Depends(get_rating_rules)],
) -> CalculatePremium:
    """The fully wired *calculate premium* use case."""

    return CalculatePremium(
        clock=clock,
        event_publisher=event_publisher,
        geographic_rate_provider=geographic_rate_provider,
        logger=logger,
        persistence_failure_mode=get_settings().persistence_failure_mode,
        repository=repository,
        rules=rules,
    )


def get_clock() -> Clock:
    """The production :class:`Clock`."""

    return SystemClock(timezone=get_settings().business_tzinfo)


def get_engine() -> Engine | None:
    """The SQLAlchemy engine, or ``None`` when persistence is disabled.

    Returning ``None`` (instead of eagerly building an engine) means an invalid
    ``DATABASE_URL`` never breaks the stateless service.
    """

    return _engine() if get_settings().persistence_enabled else None


def get_event_publisher(
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> EventPublisher:
    """The outbox publisher with persistence on, the logging publisher otherwise."""

    if get_settings().persistence_enabled:
        return OutboxEventPublisher(unit_of_work=unit_of_work)
    return LoggingEventPublisher()


def get_geographic_rate_provider() -> GeographicRateProvider:
    """An HTTP provider when GIS is enabled, otherwise the null provider."""

    settings = get_settings()
    if settings.gis_enabled and settings.gis_base_url:
        return HttpGeographicRateProvider(
            api_key=settings.gis_api_key,
            base_url=settings.gis_base_url,
            failure_mode=settings.gis_failure_mode,
            max_adjustment=settings.gis_max_adjustment,
            min_adjustment=settings.gis_min_adjustment,
            timeout_seconds=settings.gis_timeout_seconds,
        )
    return NullGeographicRateProvider()


def get_get_simulation(
    repository: Annotated[SimulationRepository, Depends(get_repository)],
) -> GetSimulation:
    """The fully wired *get simulation* use case."""

    return GetSimulation(repository=repository)


def get_list_simulations(
    repository: Annotated[SimulationRepository, Depends(get_repository)],
) -> ListSimulations:
    """The fully wired *list simulations* use case."""

    return ListSimulations(repository=repository)


def get_logger() -> Logger:
    """The application :class:`Logger` bound to structlog."""

    return StructlogLogger(name="car_insurance.application")


@lru_cache(maxsize=1)
def get_rating_rules() -> RatingRules:
    """The immutable domain rule set, built once from settings."""

    return build_rating_rules(settings=get_settings())


def get_repository(
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> SimulationRepository:
    """The SQLAlchemy repository with persistence on, the null repository otherwise."""

    if get_settings().persistence_enabled:
        return SqlAlchemySimulationRepository(
            session_factory=_session_factory(),
            unit_of_work=unit_of_work,
        )
    return NullSimulationRepository()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The validated settings singleton."""

    return Settings()


def get_unit_of_work() -> UnitOfWork:
    """A fresh request-scoped unit of work (no session factory when stateless)."""

    factory = _session_factory() if get_settings().persistence_enabled else None
    return UnitOfWork(session_factory=factory)
