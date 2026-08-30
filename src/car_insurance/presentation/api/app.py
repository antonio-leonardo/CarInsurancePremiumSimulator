"""FastAPI application factory."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

import structlog
from fastapi import FastAPI, Request, Response

from car_insurance.infrastructure.observability.logging import configure_logging
from car_insurance.infrastructure.observability.request_context import (
    REQUEST_ID_HEADER,
    bind_request_id,
)
from car_insurance.presentation.api.dependencies import get_engine, get_rating_rules, get_settings
from car_insurance.presentation.api.errors import register_exception_handlers
from car_insurance.presentation.api.routers import health, premiums

_DESCRIPTION = (
    "Simulates a car insurance premium.\n\n"
    "Rate = base rate + age increment per year + value increment per value band "
    "+ optional geographic adjustment, clamped to the configured minimum "
    "(and maximum, if set) and then quantised. Only `applied_rate` and the three "
    "money outputs are rounded; intermediates keep full precision.\n\n"
    "`deductible_percentage`: use `0.10` for 10%. Maximum 1.0 (100%).\n\n"
    "When GIS is disabled a supplied `registration_location` is accepted and "
    "applied as a **zero** adjustment (no warnings are added to the body).\n\n"
    "Errors: `422` (schema or a domain invariant), `503` (GIS unavailable in "
    'fail-closed mode), `500` (sanitised — `{ "detail": "internal error", '
    '"request_id": ... }`, also echoed in the `X-Request-ID` header).'
)

_logger = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    """Build and wire the application."""

    settings = get_settings()
    configure_logging(
        log_format=settings.log_format,
        log_level=settings.log_level,
        rules_version=settings.rules_version,
    )
    # Fail fast: materialise the domain rule set (and the DB engine, if enabled)
    # now, so an invalid configuration stops the process instead of turning every
    # request into a 422/500.
    get_rating_rules()
    if settings.persistence_enabled:
        get_engine()

    app = FastAPI(
        title="Car Insurance Premium Simulator",
        description=_DESCRIPTION,
        version=settings.rules_version,
        contact={"name": "Car Insurance Premium Simulator"},
    )

    @app.middleware("http")  # alpha-order: framework (ASGI dispatch signature)
    async def request_context_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = bind_request_id(request_id=request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        response.headers[REQUEST_ID_HEADER] = request_id
        _logger.info(
            "request.completed",
            duration_ms=duration_ms,
            route=request.url.path,
            status_code=response.status_code,
        )
        return response

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(premiums.router)
    return app
