# ADR 0011 — FastAPI only (Flask / Django noted)

## Status
Accepted (2026-08-30)

## Decision
The HTTP delivery mechanism is **FastAPI** (+ Uvicorn, Pydantic v2). Flask and
Django are known alternatives and are mentioned here for completeness only.

Because the architecture is hexagonal, a Flask or Django adapter would live
entirely in a new `presentation/` package: it would translate HTTP to
`application/use_cases` inputs and back, reusing `application/` and `domain/`
unchanged. No domain or application code assumes an ASGI framework, a request
object, or a specific serializer.

## Consequences
`domain/` and `application/` must not import `fastapi` or `pydantic`
(`import-linter`). Request/response validation is Pydantic in `presentation/`;
the use cases receive plain dataclass DTOs.
