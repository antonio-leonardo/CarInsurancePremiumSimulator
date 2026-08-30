# ADR 0006 — Minimal DDD: one aggregate, event via a logging adapter

## Status
Accepted (2026-08-30)

## Decision
* `PremiumSimulation` is both the entity and the aggregate root, identified by
  `SimulationId`. It is only ever created through the `calculate` factory
  method, already complete and consistent.
* It contains value objects (`Money`, `Percentage`, `VehicleSnapshot`, ...),
  orchestrates the three pure domain services in canonical order, and records
  `PremiumSimulationCalculated` in an internal buffer exposed by
  `pull_events()`. It performs no I/O.
* Domain services (`RateCalculator`, `PremiumCalculator`,
  `PolicyLimitCalculator`) are stateless, pure functions (SRP).
* Event delivery is a `LoggingEventPublisher` (structlog) by default. With
  persistence enabled, `OutboxEventPublisher` writes the event to an
  `event_outbox` table in the same transaction as the row. No message broker or
  durable-delivery mechanism is invented.

## Consequences
The event's payload is deliberately small: no full address (country only), no
raw `broker_fee` / `deductible_percentage`.
