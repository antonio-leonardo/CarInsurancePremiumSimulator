"""End-to-end hardening: request-id propagation, GIS through the real HTTP
adapter, malformed-cursor mapping, and no-PII logging."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
import structlog
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from car_insurance.infrastructure.persistence.models import Base
from car_insurance.presentation.api import dependencies
from car_insurance.presentation.api.app import create_app

_EXAMPLE = {
    "broker_fee": 50.0,
    "car": {"make": "Toyota", "model": "Corolla", "value": 100000.0, "year": 2012},
    "deductible_percentage": 0.10,
}


@pytest.fixture(autouse=True)
def _reset_caches() -> Iterator[None]:
    caches = (
        dependencies._engine,
        dependencies._session_factory,
        dependencies.get_rating_rules,
        dependencies.get_settings,
    )
    for cached in caches:
        cached.cache_clear()
    yield
    for cached in caches:
        cached.cache_clear()


def test_request_id_is_generated_when_absent() -> None:
    client = TestClient(create_app())
    response = client.post("/api/v1/premiums/calculate", json=_EXAMPLE)
    generated = response.headers.get("X-Request-ID")
    assert generated and len(generated) >= 8


def test_five_hundred_is_sanitised_and_carries_the_request_id() -> None:
    app = create_app()

    def _boom() -> None:
        raise RuntimeError("leak: DATABASE_URL=postgres://user:secret@host/db")

    app.dependency_overrides[dependencies.get_calculate_premium] = _boom
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/api/v1/premiums/calculate",
        json=_EXAMPLE,
        headers={"X-Request-ID": "trace-42"},
    )
    assert response.status_code == 500
    assert response.json() == {"detail": "internal error", "request_id": "trace-42"}
    assert response.headers.get("X-Request-ID") == "trace-42"
    assert "secret" not in response.text
    assert "RuntimeError" not in response.text


def test_malformed_cursor_is_422(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSISTENCE_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    Base.metadata.create_all(dependencies._engine())

    response = TestClient(create_app()).get("/api/v1/premiums", params={"cursor": "@@not-base64@@"})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_gis_enabled_shifts_rate_through_the_http_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GIS_ENABLED", "true")
    monkeypatch.setenv("GIS_BASE_URL", "https://gis.example")
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, **_: httpx.Response(
            200, json={"adjustment": 0.01}, request=httpx.Request("GET", url)
        ),
    )
    body = (
        TestClient(create_app())
        .post(
            "/api/v1/premiums/calculate",
            json={**_EXAMPLE, "registration_location": {"country": "US"}},
        )
        .json()
    )
    assert body["applied_rate"] == 0.13  # 0.12 + 0.01


def test_gis_out_of_range_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIS_ENABLED", "true")
    monkeypatch.setenv("GIS_BASE_URL", "https://gis.example")
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, **_: httpx.Response(
            200, json={"adjustment": 0.9}, request=httpx.Request("GET", url)
        ),
    )
    response = TestClient(create_app()).post(
        "/api/v1/premiums/calculate",
        json={**_EXAMPLE, "registration_location": {"country": "US"}},
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "geographic risk service unavailable"}


def test_gis_fail_open_falls_back_to_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIS_ENABLED", "true")
    monkeypatch.setenv("GIS_BASE_URL", "https://gis.example")
    monkeypatch.setenv("GIS_FAILURE_MODE", "fail_open")

    def _refuse(url, **_):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", _refuse)
    body = (
        TestClient(create_app())
        .post(
            "/api/v1/premiums/calculate",
            json={**_EXAMPLE, "registration_location": {"country": "US"}},
        )
        .json()
    )
    assert body["applied_rate"] == 0.12


def test_no_pii_reaches_the_logger() -> None:
    client = TestClient(create_app())  # configures structlog first
    with capture_logs() as events:
        client.post(
            "/api/v1/premiums/calculate",
            json={
                **_EXAMPLE,
                "broker_fee": 777.77,
                "registration_location": {
                    "country": "US",
                    "line1": "221B Baker Street",
                    "postal_code": "NW16XE",
                    "region": "London",
                },
            },
        )

    blob = repr(events)
    assert any(e.get("event") == "premium.calculated" for e in events)
    assert "221B Baker Street" not in blob
    assert "NW16XE" not in blob
    assert "London" not in blob
    assert "777.77" not in blob
    # the country code is the one location field allowed through
    assert any(e.get("country") == "US" for e in events)


def test_health_live_never_touches_the_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PERSISTENCE_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    app = create_app()

    class _BrokenEngine:
        def connect(self) -> object:
            raise RuntimeError("db is down")

    app.dependency_overrides[dependencies.get_engine] = lambda: _BrokenEngine()
    client = TestClient(app)
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 503


@pytest.fixture(autouse=True)
def _reset_structlog() -> Iterator[None]:
    yield
    structlog.reset_defaults()
