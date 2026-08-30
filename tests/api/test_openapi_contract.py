"""Phase 4 gate: the OpenAPI document matches the published contract."""

from __future__ import annotations


def test_openapi_paths_and_operation_ids(client) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]

    assert schema["info"]["version"] == "2026.08.0"
    assert "0.10" in schema["info"]["description"]

    expected = {
        ("/api/v1/premiums/calculate", "post"): "calculatePremium",
        ("/api/v1/premiums", "get"): "listSimulations",
        ("/api/v1/premiums/{simulation_id}", "get"): "getSimulation",
        ("/health/live", "get"): "healthLive",
        ("/health/ready", "get"): "healthReady",
    }
    for (path, method), operation_id in expected.items():
        assert path in paths, f"missing path {path}"
        assert paths[path][method]["operationId"] == operation_id


def test_calculate_response_schema_is_narrow(client) -> None:
    schema = client.get("/openapi.json").json()
    ref = schema["paths"]["/api/v1/premiums/calculate"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    name = ref.rsplit("/", 1)[-1]
    response_model = schema["components"]["schemas"][name]

    assert set(response_model["properties"]) == {
        "applied_rate",
        "calculated_premium",
        "car",
        "deductible_value",
        "policy_limit",
    }
    assert set(response_model["required"]) == set(response_model["properties"])


def test_error_responses_are_documented(client) -> None:
    schema = client.get("/openapi.json").json()
    responses = schema["paths"]["/api/v1/premiums/calculate"]["post"]["responses"]
    assert {"200", "422", "503"}.issubset(responses)


def test_docs_and_redoc_render(client) -> None:
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
