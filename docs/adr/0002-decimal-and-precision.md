# ADR 0002 — `Decimal` everywhere and the precision policy

## Status
Accepted (2026-08-30)

## Context
Money and rates must be reproducible and free of binary floating-point drift.

## Decision
* Every financial/rate value is a `decimal.Decimal`. `float` is banned in
  `domain/` and `application/` (enforced by review + the arithmetic being on
  `Decimal`). Inbound primitives are coerced with `Decimal(str(value))`.
* Intermediate results (`base_premium`, `deductible_discount`,
  `base_policy_limit`) are kept at **full precision** — no early quantisation.
* Quantisation happens exactly once per external number:
  * `applied_rate` → `RATE_DECIMAL_PLACES` (default 6), `RATE_ROUNDING_MODE`.
  * `calculated_premium`, `deductible_value`, `policy_limit` →
    `MONEY_DECIMAL_PLACES` (default 2), `MONEY_ROUNDING_MODE`.
* The **quantised** `applied_rate` returned in the response is the same value
  used to compute the premium, so results are reproducible.
* `vehicle.value` is echoed after validation, never recomputed.
* `geographic_adjustment` is additive in rate points; `Decimal("0")` when GIS is
  off.

## Consequences
Rate pipeline (canonical, in `RateCalculator`):
`raw = age_rate + value_rate + base_rate + gis` → `max(raw, MINIMUM)` →
(`min(_, MAXIMUM)` if set) → `quantize`.

The three domain services run their arithmetic inside `high_precision()`
(`domain/calculation_context.py`, `prec=80`), so the default 28-digit `decimal`
context never silently rounds an intermediate (or raises `InvalidOperation` on
`quantize`) for large `vehicle.value`. Only `quantize_money` / `quantize_rate`
round. `MINIMUM_APPLIED_RATE` and (if set) `MAXIMUM_APPLIED_RATE` must be
representable at `RATE_DECIMAL_PLACES`, otherwise the post-quantisation
`applied_rate` could cross the bound by up to half a ULP — validated in
`RatingRules`.
