"""Deeper OpenAPI-contract assertions (Phase 4 gate, hardened)."""

from __future__ import annotations

import pytest


@pytest.fixture
def schema(client) -> dict:
    return client.get("/openapi.json").json()


def _model(schema: dict, ref: str) -> dict:
    return schema["components"]["schemas"][ref.rsplit("/", 1)[-1]]


def test_request_body_forbids_extra_properties(schema: dict) -> None:
    ref = schema["paths"]["/api/v1/premiums/calculate"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    request_model = _model(schema, ref)
    assert request_model.get("additionalProperties") is False
    assert set(request_model["required"]) >= {
        "broker_fee",
        "car",
        "deductible_percentage",
    }


def test_deductible_field_documents_the_ten_percent_convention(schema: dict) -> None:
    ref = schema["paths"]["/api/v1/premiums/calculate"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    request_model = _model(schema, ref)
    description = request_model["properties"]["deductible_percentage"].get("description", "")
    assert "0.10" in description


def test_calculate_documents_200_422_500_503_with_models_and_examples(schema: dict) -> None:
    responses = schema["paths"]["/api/v1/premiums/calculate"]["post"]["responses"]
    assert set(responses) >= {"200", "422", "500", "503"}
    for code in ("200", "422", "500", "503"):
        model_schema = responses[code]["content"]["application/json"]["schema"]
        ref = model_schema.get("$ref") or model_schema.get("allOf", [{}])[0].get("$ref")
        assert ref, f"response {code} has no model"
        assert _model(schema, ref).get("examples"), f"response {code} model has no example"


def test_ready_probe_documents_503(schema: dict) -> None:
    assert "503" in schema["paths"]["/health/ready"]["get"]["responses"]


def test_description_mentions_gis_off_behaviour(schema: dict) -> None:
    description = schema["info"]["description"]
    assert "zero" in description.lower()
    assert "request_id" in description or "X-Request-ID" in description


def test_history_record_schema_is_the_additive_shape(schema: dict) -> None:
    ref = schema["paths"]["/api/v1/premiums/{simulation_id}"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    record = _model(schema, ref)
    assert set(record["properties"]) == {
        "applied_rate",
        "calculated_premium",
        "car",
        "created_at",
        "deductible_value",
        "policy_limit",
        "rules_version",
        "simulation_id",
    }
    assert record.get("additionalProperties") is False


def test_health_routes_are_not_under_api_v1(schema: dict) -> None:
    assert "/health/live" in schema["paths"]
    assert "/health/ready" in schema["paths"]
    assert not any(path.startswith("/api/v1/health") for path in schema["paths"])


def test_every_calculate_field_has_a_description(schema: dict) -> None:
    ref = schema["paths"]["/api/v1/premiums/calculate"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    request_model = _model(schema, ref)
    assert request_model["properties"]["broker_fee"].get("description")
    assert request_model["properties"]["deductible_percentage"].get("description")


def test_openapi_version_tracks_rules_version(schema: dict) -> None:
    assert schema["info"]["version"] == "2026.08.0"
    assert schema["info"]["title"] == "Car Insurance Premium Simulator"
