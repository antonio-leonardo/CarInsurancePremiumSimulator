"""HTTP-level contract details: methods, content types, operationId stability,
and the business log line carrying the request id."""

from __future__ import annotations

import json

import pytest
import structlog
from fastapi.testclient import TestClient

from car_insurance.presentation.api.app import create_app

_EXAMPLE = {
    "broker_fee": 50.0,
    "car": {"make": "Toyota", "model": "Corolla", "value": 100000.0, "year": 2016},
    "deductible_percentage": 0.10,
}


def test_calculate_rejects_wrong_methods(client) -> None:
    assert client.get("/api/v1/premiums/calculate").status_code in (404, 405, 422)
    assert client.put("/api/v1/premiums/calculate", json=_EXAMPLE).status_code == 405
    assert client.delete("/api/v1/premiums/calculate").status_code == 405


def test_success_content_type_is_json(client) -> None:
    response = client.post("/api/v1/premiums/calculate", json=_EXAMPLE)
    assert response.headers["content-type"].startswith("application/json")


def test_operation_ids_are_the_frozen_set(client) -> None:
    schema = client.get("/openapi.json").json()
    operation_ids = {
        method_spec["operationId"]
        for path_item in schema["paths"].values()
        for method_spec in path_item.values()
        if isinstance(method_spec, dict) and "operationId" in method_spec
    }
    assert operation_ids == {
        "calculatePremium",
        "getSimulation",
        "healthLive",
        "healthReady",
        "listSimulations",
    }


def test_unknown_path_is_404(client) -> None:
    assert client.get("/api/v1/does-not-exist").status_code == 404


def test_business_log_line_carries_the_request_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    try:
        client = TestClient(create_app())  # installs the real JSON pipeline
        capsys.readouterr()  # drop anything logged during setup
        client.post(
            "/api/v1/premiums/calculate",
            json=_EXAMPLE,
            headers={"X-Request-ID": "trace-xyz"},
        )
        lines = [
            json.loads(line)
            for line in capsys.readouterr().out.splitlines()
            if line.startswith("{")
        ]
    finally:
        structlog.reset_defaults()

    calc = next(e for e in lines if e.get("event") == "premium.calculated")
    assert calc["request_id"] == "trace-xyz"
    assert calc["rules_version"] == "2026.08.0"
    assert "timestamp" in calc

    completed = next(e for e in lines if e.get("event") == "request.completed")
    assert completed["request_id"] == "trace-xyz"
    assert completed["route"] == "/api/v1/premiums/calculate"
    assert completed["status_code"] == 200
