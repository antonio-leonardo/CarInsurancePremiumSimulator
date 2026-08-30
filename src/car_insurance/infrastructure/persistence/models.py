"""SQLAlchemy 2.x imperative mappings for optional persistence."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, Numeric, String, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Unbounded NUMERIC: the money/rate scale is configuration (MONEY_DECIMAL_PLACES,
# RATE_DECIMAL_PLACES), so the column must not impose its own scale — otherwise a
# valid config could make the stored history diverge from the response.
_MONEY = Numeric()
_RATE = Numeric()


class Base(DeclarativeBase):
    """Declarative base for every persisted model."""


class EventOutboxRecord(Base):
    """A domain event awaiting downstream delivery, written in the save transaction."""

    __tablename__ = "event_outbox"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    simulation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("premium_simulations.id"), nullable=False
    )


class PremiumSimulationRecord(Base):
    """A persisted premium simulation (no full address is ever stored)."""

    __tablename__ = "premium_simulations"
    __table_args__ = (Index("ix_premium_simulations_created_at_id", "created_at", "id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True)
    applied_rate: Mapped[Decimal] = mapped_column(_RATE, nullable=False)
    calculated_premium: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    deductible_value: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    location_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    policy_limit: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    rules_version: Mapped[str] = mapped_column(String(40), nullable=False)
    vehicle_make: Mapped[str] = mapped_column(String(120), nullable=False)
    vehicle_model: Mapped[str] = mapped_column(String(120), nullable=False)
    vehicle_value: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    vehicle_year: Mapped[int] = mapped_column(Integer, nullable=False)
