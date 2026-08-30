# ADR 0010 — GIS: the domain only knows `GeographicRateAdjustment`

## Status
Accepted (2026-08-30)

## Decision
* The domain models geography as a single value object,
  `GeographicRateAdjustment` (a signed `Decimal` in rate points). It knows
  nothing about HTTP, API keys or providers.
* `GeographicRateProvider.adjustment_for(*, address)` is the port.
  `NullGeographicRateProvider` (default) returns zero.
  `HttpGeographicRateProvider` calls the external service with `httpx`, a
  `GIS_TIMEOUT_SECONDS` timeout, and validates the response is within
  `[GIS_MIN_ADJUSTMENT, GIS_MAX_ADJUSTMENT]` (defaults `[-0.02, +0.02]`).
* Failure / timeout / out-of-range: `fail_closed` (default) → propagate as HTTP
  503; `fail_open` → adjustment 0 + `logger.warning`.
* A location supplied while `GIS_ENABLED=false` is accepted, adjustment zero; no
  `warnings` are ever added to the response body.
* Logs and events never contain the full address or `GIS_API_KEY`. The HTTP
  adapter logs only the exception *class name* on failure (never a message,
  which could echo the request URL and its location query string), and
  `configure_logging` pins the `httpx`/`httpcore` loggers to `WARNING`.
* A malformed `200` body (missing key, wrong JSON type) is treated exactly like
  a transport error — routed through the failure mode (`fail_open` → 0,
  `fail_closed` → 503), never a `500`.
* `Address` is the minimal VO. A provider needing more fields requires a new ADR
  before Phase 8.
