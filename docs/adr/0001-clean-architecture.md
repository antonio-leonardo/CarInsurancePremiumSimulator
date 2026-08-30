# ADR 0001 — Clean Architecture and the dependency rule

## Status
Accepted (2026-08-30)

## Context
The exercise asks for a maintainable premium calculator that can outlive its
current delivery mechanism (HTTP) and storage choice (none / PostgreSQL).

## Decision
Four layers, dependencies pointing inward only:

```
presentation -> infrastructure -> application -> domain
```

* `domain/` — value objects, the `PremiumSimulation` aggregate, pure domain
  services, the domain event, domain errors. Imports nothing but the standard
  library.
* `application/` — use cases, ports (Protocols), DTOs. Imports `domain/` only.
* `infrastructure/` — adapters implementing the ports (settings, clock,
  persistence, GIS, logging).
* `presentation/` — FastAPI app, schemas, routers, error mapping, the
  composition root.

The core calculation has **no** knowledge of a repository or database: a quote
is a pure function of its inputs plus the configured `RatingRules`. Persistence
is a post-calculation side effect in the use case.

## Consequences
* `import-linter` enforces the layering and the framework ban
  (`tests/architecture/test_import_rules.py`).
* Swapping FastAPI for Flask/Django, or adding a queue, touches only
  `presentation/` or `infrastructure/`.
* A small amount of mapping boilerplate (DTO <-> schema <-> model) is the price.
