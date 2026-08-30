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
Pydantic validation already produces the 422 structure.
