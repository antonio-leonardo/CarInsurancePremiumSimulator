# ADR 0014 — A `Logger` port keeps `structlog` out of the core

## Status
Accepted (2026-09-02)

## Context
The blind adversarial audit (finding A11) found `import structlog` in
`application/use_cases/calculate_premium.py`. The application layer must depend
only on the domain — not on a logging framework — and neither the
`import-linter` contract nor the AST guard forbade it.

## Decision
* `application/ports/logger.py` defines a minimal `Logger` `Protocol`:
  `bind(**fields) -> Logger`, `error(event, **fields)`, `info(...)`,
  `warning(...)`. `bind` returns a logger that carries the given fields on every
  subsequent line; the use case binds `simulation_id` once and logs through the
  bound logger.
* `CalculatePremium` receives a `Logger` by constructor injection. No
  `application/` or `domain/` module imports `structlog`.
* `infrastructure/observability/structlog_logger.py` (`StructlogLogger`) binds
  the port to `structlog`; it is wired in `dependencies.get_logger`.
* The `import-linter` "framework-free" contract and `_FORBIDDEN_IN_CORE` in
  `tests/architecture/test_guards_are_effective.py` both list `structlog`
  alongside `fastapi` / `pydantic` / `sqlalchemy` / `httpx`. A meta-test proves
  the guard fails if `structlog` reappears in the core.

## Consequences
* `grep -rn structlog src/car_insurance/application src/car_insurance/domain` is
  empty.
* Swapping the logging library is an infrastructure-only change.
