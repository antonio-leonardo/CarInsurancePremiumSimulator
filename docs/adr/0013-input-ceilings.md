# ADR 0013 — Configurable input ceilings for money fields

## Status
Accepted (2026-09-02)

## Context
The blind adversarial audit (finding A1) showed two defects at the HTTP edge:

* `car.value = 1e100` reached the `Decimal` quantisation step and raised
  `InvalidOperation`, surfacing as **HTTP 500** instead of a validation error.
* `car.value = 9007199254740993` (just above `2^53`) was echoed back as
  `9007199254740992.0` — the `Decimal → float` projection lost a digit.

## Decision
* Two configuration knobs, `MAX_VEHICLE_VALUE` (default `1e11`) and
  `MAX_BROKER_FEE` (default `1e9`). A value above its ceiling is a **422**
  (`DomainError` from `CalculatePremium.execute`), never a 500.
  <!-- PRODUCT-DECISION -->
* The Pydantic schemas keep a fixed `le=1e11` sanity guard on `car.value` and
  `broker_fee` as an anti-`InvalidOperation` backstop. The configurable ceiling
  is the operative limit and can only be **lowered** below the guard in
  practice; raising `MAX_VEHICLE_VALUE` above `1e11` has no effect because the
  schema rejects first. This is deliberate — a lossless `Decimal → JSON number`
  echo (`NumberOut`: integral ⇒ `int`, else `float`) is only guaranteed for
  magnitudes `< 2^53` with scale ≤ `MONEY_DECIMAL_PLACES`, which `≤ 1e11`
  guarantees.
* The three domain calculators run inside `high_precision()` (`prec=80`) so the
  only rounding is the explicit `quantize_money` / `quantize_rate`.

## Consequences
* `value = 1e100` → 422 with a `ValidationErrorResponse` body.
* `value = 99999999999.99`, `broker_fee = 12345.67` → echoed exactly.
* `MAX_VEHICLE_VALUE` / `MAX_BROKER_FEE` are documented in `.env.example` and the
  README configuration matrix. Both are validated at startup (finite, `> 0`).
