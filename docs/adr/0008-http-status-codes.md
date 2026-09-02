# ADR 0008 — HTTP status codes

## Status
Accepted (2026-08-30)

## Decision
| Code | When | Body |
|------|------|------|
| 200  | Calculation succeeded | narrow 5-field contract |
| 422  | Invalid schema; a domain input invariant (value <= 0, NaN, infinity, future year, year < `MIN_VEHICLE_YEAR`, percentage out of range, currency mismatch, empty string); an unparseable path parameter; **or a malformed pagination cursor** | `{ "detail": [ { "loc": [], "msg": "...", "type": "..." } ] }` |
| 503  | `GIS_ENABLED=true`, `GIS_FAILURE_MODE=fail_closed`, a location was supplied and the provider failed / timed out / returned an out-of-range value | `{ "detail": "geographic risk service unavailable" }` |
| 500  | Unexpected error | `{ "detail": "internal error", "request_id": "..." }` — sanitised, no stack, no secrets; `request_id` is the caller's `X-Request-ID` (or a generated one), echoed in the body **and** the `X-Request-ID` response header |

`DomainError` subclasses map to the 422 structure via one exception handler.
A malformed cursor is a client error — `InvalidCursorError` (distinct from the
infrastructure-failure `SimulationRepositoryError`) maps to 422, not 500.

**422 body normalisation (audit finding A10).** A dedicated
`RequestValidationError` handler reshapes Pydantic's raw entries down to exactly
`loc` / `msg` / `type`, dropping the echoed `input` value and any `ctx` object.
The 422 body is therefore identical whether the failure is a schema violation or
a domain invariant, and matches `ValidationErrorResponse` / `ErrorItem`
(`extra="forbid"`).

**OpenAPI (audit finding A10).** `/calculate` documents `200`, `422`, `500`
(`InternalErrorResponse`) and `503`, each with a named example; `/health/ready`
documents `503`. Every request/response field and every `Address` field carries
a `description` and `examples`. The endpoint description states that a location
supplied with `GIS_ENABLED=false` yields a zero geographic adjustment.
