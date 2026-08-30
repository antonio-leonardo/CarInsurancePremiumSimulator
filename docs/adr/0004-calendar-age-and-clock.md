# ADR 0004 — Vehicle age by calendar year; injectable `Clock`

## Status
Accepted (2026-08-30)

## Decision
* `car_age = calculation_year - vehicle.year`, where `calculation_year` is the
  year of `Clock.now()` evaluated in `BUSINESS_TIMEZONE` (default `UTC`).
* `Clock` is a port (`application/ports/clock.py`); production uses
  `SystemClock`, tests use `FixedClock`.
* A model year later than `calculation_year` is rejected (HTTP 422). This check
  lives in the use case, where the current year is available; the
  `PremiumSimulation` aggregate factory receives `now` as a parameter rather
  than importing the `Clock` port (the dependency rule forbids
  `domain -> application`).
* `VehicleYear.__post_init__` enforces only that the year is a positive
  integer. The configurable `MIN_VEHICLE_YEAR` bound (default 1900) is applied by
  `VehicleYear.create(minimum=...)`, which the use case always calls with
  `rules.min_vehicle_year` — so the bound can be **relaxed or tightened** purely
  by config, with no hard floor baked into the type.

## Consequences
Age is stable within a calendar year and independent of the request instant's
month/day. All year-dependent tests inject `FixedClock`.
