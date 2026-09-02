# ADR 0016 — Configuration is fully validated at startup

## Status
Accepted (2026-09-02)

## Context
The adversarial audit (finding A2) showed that an invalid rating rule
(`VALUE_BAND_AMOUNT=0`) let the application boot: `/health/ready` returned 200
and only the *first* `calculate` call returned 422. A container in that state
passes its readiness gate and takes traffic it cannot serve.

## Decision
`create_app()` eagerly materialises the full configuration before the app
accepts traffic:

* `get_rating_rules()` — builds and domain-validates `RatingRules` (via
  `RatingRules.__post_init__`). Covers every numeric rule, including
  `0 ≤ MAX_DEDUCTIBLE_PERCENTAGE ≤ 1` (ADR 0003-adjacent / finding A3),
  `MAXIMUM_APPLIED_RATE` representable at `RATE_DECIMAL_PLACES` (finding A9), and
  `GIS_MIN_ADJUSTMENT ≤ GIS_MAX_ADJUSTMENT`.
* `Settings()` — `pydantic-settings` validation plus `_check_consistency`:
  failure modes, log format, rounding modes, `DATABASE_URL` URL shape (always,
  finding A7), pool sizes, GIS timeout, timezone, and the input ceilings
  `MAX_VEHICLE_VALUE` / `MAX_BROKER_FEE` (finding A1).
* `get_engine()` when `PERSISTENCE_ENABLED=true`.

Any failure raises before the first request, so the container exits non-zero and
never reports ready.

## Consequences
* No instance with an invalid configuration ever answers `200` on
  `/health/ready`.
* Regression: `tests/api/test_adversarial_audit.py::test_a2_bad_rule_config_prevents_boot`
  parametrises the known-bad configurations and asserts `create_app()` raises.
