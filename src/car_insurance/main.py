"""ASGI entry point: ``uvicorn car_insurance.main:app``."""

from __future__ import annotations

from car_insurance.presentation.api.app import create_app

app = create_app()
