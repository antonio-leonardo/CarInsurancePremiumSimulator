# ADR 0003 — Discrete value bands with `floor`

## Status
Accepted (2026-08-30)

## Decision
The value component of the rate uses discrete bands:

```
value_units = floor(vehicle.value / VALUE_BAND_AMOUNT)   # integer, truncated
value_rate  = value_units * VALUE_RATE_INCREMENT
```

Both `VALUE_BAND_AMOUNT` (default 10000) and `VALUE_RATE_INCREMENT` (default
0.005) are configuration. There is **no** `VALUE_BANDING_MODE` and no
proportional alternative — a single, predictable rule.

## Consequences
Boundary behaviour (covered by a parametrised test):

| value    | value_units | contribution |
|----------|-------------|--------------|
| 9999.99  | 0           | 0%           |
| 10000.00 | 1           | 0.5%         |
| 19999.99 | 1           | 0.5%         |
| 20000.00 | 2           | 1%           |
| 100000.00| 10          | 5%           |

## Amendment (2026-09-02) — deductible ceiling `0 ≤ x ≤ 1`

The audit (finding A3) showed that `MAX_DEDUCTIBLE_PERCENTAGE=1.5` plus
`deductible_percentage=1.5` produced a **negative** premium and policy limit.

<!-- PRODUCT-DECISION -->
A deductible is a fraction of the vehicle value: `1.0` (100%) is the economic
maximum and is **allowed** (premium collapses to the broker fee, policy limit to
zero); anything above 1 is meaningless. `RatingRules.__post_init__` now requires
`0 ≤ max_deductible_percentage ≤ 1`, so a misconfigured ceiling fails the boot
(ADR 0016), and the `deductible_percentage` request field carries `le=1`, so an
over-100% input is a 422.
