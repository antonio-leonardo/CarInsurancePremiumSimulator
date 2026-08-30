"""initial schema: premium_simulations + event_outbox

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-30 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

_MONEY = sa.Numeric()  # unbounded — scale is configuration, not schema
_RATE = sa.Numeric()


def downgrade() -> None:
    op.drop_table("event_outbox")
    op.drop_table("premium_simulations")


def upgrade() -> None:
    op.create_table(
        "premium_simulations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("applied_rate", _RATE, nullable=False),
        sa.Column("calculated_premium", _MONEY, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("deductible_value", _MONEY, nullable=False),
        sa.Column("location_country", sa.String(2), nullable=True),
        sa.Column("policy_limit", _MONEY, nullable=False),
        sa.Column("rules_version", sa.String(40), nullable=False),
        sa.Column("vehicle_make", sa.String(120), nullable=False),
        sa.Column("vehicle_model", sa.String(120), nullable=False),
        sa.Column("vehicle_value", _MONEY, nullable=False),
        sa.Column("vehicle_year", sa.Integer, nullable=False),
    )
    op.create_index(
        "ix_premium_simulations_created_at_id",
        "premium_simulations",
        ["created_at", "id"],
    )
    op.create_table(
        "event_outbox",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column(
            "simulation_id",
            sa.Uuid(),
            sa.ForeignKey("premium_simulations.id"),
            nullable=False,
        ),
    )
