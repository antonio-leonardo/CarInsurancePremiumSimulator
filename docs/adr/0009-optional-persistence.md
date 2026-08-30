# ADR 0009 — Optional persistence, outbox in the same transaction

## Status
Accepted (2026-08-30)

## Decision
* Persistence is off by default (`PERSISTENCE_ENABLED=false`). Off means: `save`
  is a no-op (`NullSimulationRepository`), `GET /api/v1/premiums/{id}` returns
  404, `GET /api/v1/premiums` returns an empty page, and the `calculate`
  contract is byte-for-byte unchanged.
* On means: `SqlAlchemySimulationRepository` (SQLAlchemy 2.x sync + FastAPI
  threadpool) writes a `premium_simulations` row **and** the
  `PremiumSimulationCalculated` outbox rows in one transaction, coordinated by
  `UnitOfWork`. The use case publishes events (staging them on the UoW) before
  it calls `save`, which opens the transaction.
* A stored row never contains a full address — `location_country` only.
* Save failure: `PERSISTENCE_FAILURE_MODE=fail_closed` (default) → HTTP 500;
  `fail_open` → HTTP 200 + `logger.error`.
* Migrations: Alembic; `alembic upgrade head` runs in the container entrypoint
  only when `PERSISTENCE_ENABLED=true`.

## Consequences
* The calculation core never depends on the database.
* With persistence **off**, `DATABASE_URL` is never read and no engine is
  created — `get_engine()` returns `None`, `get_unit_of_work()` carries no
  session factory. An invalid DSN cannot break the stateless service.
* With persistence **on**, `DATABASE_URL` (must contain `://`) and the pool
  sizes are validated at startup; the domain rule set and the engine are
  materialised in `create_app()` so a bad configuration fails the boot, not the
  first request.
* Money/rate columns are unbounded `NUMERIC` (scale is `MONEY_DECIMAL_PLACES` /
  `RATE_DECIMAL_PLACES`, i.e. configuration — the schema must not impose its
  own). An integration test asserts `alembic autogenerate` is empty against the
  ORM models.
