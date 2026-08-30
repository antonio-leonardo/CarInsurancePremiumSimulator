"""Health probe tests."""

from __future__ import annotations


def test_live_is_always_200(client) -> None:
    assert client.get("/health/live").json() == {"status": "alive"}


def test_ready_is_200_without_persistence(client) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
