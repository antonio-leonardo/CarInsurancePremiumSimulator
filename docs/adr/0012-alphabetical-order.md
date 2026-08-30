# ADR 0012 — Alphabetical ordering requirement

## Status
Accepted (2026-08-30)

## Decision
Within every `src/` module:

* top-level `def` / `async def` definitions are in alphabetical order;
* methods inside each class are in alphabetical order (dunder methods —
  `__init__`, `__post_init__`, ... — are exempt and conventionally placed
  first);
* parameters in every signature are in alphabetical order, merging positional
  and keyword-only, excluding `self` / `cls`. Functions with 2+ parameters in
  `domain/` and `application/` are keyword-only (`*`).

Verified by `tests/architecture/test_alphabetical_order.py` (AST).

## Exemptions
The marker comment `# alpha-order: framework` opts out a **single** function,
method or class (placed on its `def`/`class` line, in its decorator list, or on
the line immediately above) — never a whole file. There is exactly **one**
marker in `src/`:

* `presentation/api/app.py` — the ASGI middleware signature `(request,
  call_next)` is fixed by Starlette.

Everything else is alphabetical, `presentation/api/dependencies.py` included:
`from __future__ import annotations` turns each `Annotated[..., Depends(x)]`
into a string that FastAPI resolves only at route registration, so there is no
definition-order constraint on the composition root. The history list route
takes a `PaginationParams` query model (one parameter) rather than loose
`cursor`/`limit` arguments, so its signature sorts too. Alembic migration
scripts are out of scope.
