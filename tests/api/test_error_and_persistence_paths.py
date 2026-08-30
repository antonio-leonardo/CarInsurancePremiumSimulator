"""500 sanitisation and the persistence-enabled HTTP paths."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from car_insurance.infrastructure.persistence.models import Base
from car_insurance.presentation.api import dependencies
from car_insurance.presentation.api.app import create_app

_EXAMPLE_A = {
    "broker_fee": 50.0,
    "car": {"make": "Toyota", "model": "Corolla", "value": 100000.0, "year": 2016},
    "deductible_percentage": 0.10,
}


@pytest.fixture(autouse=True)
def _reset_caches() -> Iterator[None]:
    dependencies.get_settings.cache_clear()
    dependencies.get_rating_rules.cache_clear()
    dependencies._engine.cache_clear()
    dependencies._session_factory.cache_clear()
    yield
    dependencies.get_settings.cache_clear()
    dependencies.get_rating_rules.cache_clear()
    dependencies._engine.cache_clear()
    dependencies._session_factory.cache_clear()


def test_unexpected_error_is_sanitised_500() -> None:
    app = create_app()

    def _boom() -> None:
        raise RuntimeError("secret internal detail")

    app.dependency_overrides[dependencies.get_calculate_premium] = _boom
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/api/v1/premiums/calculate", json=_EXAMPLE_A)
    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "internal error"
    assert "request_id" in body
    assert "secret internal detail" not in response.text


def test_persistence_enabled_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSISTENCE_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")

    Base.metadata.create_all(dependencies._engine())
    app = create_app()
    client = TestClient(app)

    created = client.post("/api/v1/premiums/calculate", json=_EXAMPLE_A)
    assert created.status_code == 200

    listed = client.get("/api/v1/premiums").json()
    assert len(listed["items"]) == 1
    simulation_id = listed["items"][0]["simulation_id"]

    fetched = client.get(f"/api/v1/premiums/{simulation_id}")
    assert fetched.status_code == 200
    assert fetched.json()["calculated_premium"] == 9050.0

    missing = client.get("/api/v1/premiums/123e4567-e89b-12d3-a456-426614174000")
    assert missing.status_code == 404


def test_ready_probe_checks_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSISTENCE_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    Base.metadata.create_all(dependencies._engine())

    client = TestClient(create_app())
    assert client.get("/health/ready").status_code == 200


def test_ready_probe_reports_unavailable_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSISTENCE_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")

    app = create_app()

    class _BrokenEngine:
        def connect(self) -> object:
            raise RuntimeError("no database")

    app.dependency_overrides[dependencies.get_engine] = lambda: _BrokenEngine()
    response = TestClient(app).get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
