"""Liveness and readiness probes."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import Engine, text

from car_insurance.infrastructure.config.settings import Settings
from car_insurance.presentation.api.dependencies import get_engine, get_settings
from car_insurance.presentation.api.schemas import MessageResponse

_logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Health"])


@router.get("/health/live", operation_id="healthLive", summary="Liveness probe")
def health_live() -> dict[str, str]:
    """Return 200 as long as the process is running."""

    return {"status": "alive"}


@router.get(
    "/health/ready",
    operation_id="healthReady",
    responses={
        503: {
            "model": MessageResponse,
            "description": "Persistence is enabled but the database did not answer",
        }
    },
    summary="Readiness probe",
)
def health_ready(
    engine: Annotated[Engine | None, Depends(get_engine)],
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    """200 when settings are loaded and (if persistence is on) the database answers; else 503."""

    if settings.persistence_enabled and engine is not None:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception as exc:
            _logger.warning("health.ready.db_unavailable", error=type(exc).__name__)
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "unavailable"}
    return {"status": "ready"}
