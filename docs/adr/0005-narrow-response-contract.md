# ADR 0005 — Narrow `calculate` response contract

## Status
Accepted (2026-08-30)

## Decision
`POST /api/v1/premiums/calculate` returns **exactly** five top-level fields:
`applied_rate`, `calculated_premium`, `car`, `deductible_value`, `policy_limit`.
`car` contains **exactly** `make`, `model`, `value`, `year`.

The response never echoes `broker_fee`, `deductible_percentage`,
`registration_location`, identifiers or metadata. `applied_rate` is a fractional
JSON number (`0.12` means 12%). Pydantic models use `extra="forbid"` and the
OpenAPI contract test asserts the property set.

The history endpoints (`GET /api/v1/premiums/{id}` and `GET /api/v1/premiums`)
use a **separate, additive** record schema that does include `simulation_id`,
`created_at` and `rules_version`.

## Consequences
A full request round-trip in the `calculate` response would require an explicit
product decision; until then the contract stays minimal.
