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
