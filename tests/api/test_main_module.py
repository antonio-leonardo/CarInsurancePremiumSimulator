"""The ASGI entry point imports and exposes an app."""

from __future__ import annotations

from fastapi import FastAPI

from car_insurance.main import app


def test_main_exposes_fastapi_app() -> None:
    assert isinstance(app, FastAPI)
