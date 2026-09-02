"""Translation of domain/application failures into HTTP responses."""

from __future__ import annotations

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from car_insurance.application.ports.geographic_rate_provider import GeographicRateProviderError
from car_insurance.application.ports.simulation_repository import InvalidCursorError
from car_insurance.domain.errors import DomainError
from car_insurance.infrastructure.observability.request_context import (
    REQUEST_ID_HEADER,
    current_request_id,
)

_logger = structlog.get_logger(__name__)


def _validation_response(*, message: str, type_: str) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": [{"loc": [], "msg": message, "type": type_}]},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the domain / cursor / GIS / unexpected error handlers to ``app``."""

    async def handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return _validation_response(message=str(exc), type_="domain_error")

    async def handle_gis_error(_: Request, __: GeographicRateProviderError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": "geographic risk service unavailable"},
        )

    async def handle_invalid_cursor(_: Request, __: InvalidCursorError) -> JSONResponse:
        return _validation_response(message="invalid pagination cursor", type_="invalid_cursor")

    async def handle_request_validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Normalise Pydantic's entries to exactly ``loc`` / ``msg`` / ``type`` so
        # the 422 body matches ``ValidationErrorResponse`` and never leaks the
        # echoed ``input`` value or a ``ctx`` object (ADR 0008).
        detail = [
            {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
            for error in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": detail})

    # alpha-order: framework (Starlette calls handlers as ``handler(request, exc)``)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None) or current_request_id() or "unknown"
        _logger.error("request.unhandled_error", error=type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={"detail": "internal error", "request_id": request_id},
            headers={REQUEST_ID_HEADER: request_id},
        )

    app.add_exception_handler(DomainError, handle_domain_error)  # type: ignore[arg-type]
    app.add_exception_handler(GeographicRateProviderError, handle_gis_error)  # type: ignore[arg-type]
    app.add_exception_handler(InvalidCursorError, handle_invalid_cursor)  # type: ignore[arg-type]
    app.add_exception_handler(
        RequestValidationError,
        handle_request_validation_error,  # type: ignore[arg-type]
    )
    app.add_exception_handler(Exception, handle_unexpected_error)
