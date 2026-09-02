"""Hardening: exact error-body shapes and status codes at the HTTP boundary."""

from __future__ import annotations

import uuid

_EXAMPLE_A = {
    "broker_fee": 50.0,
    "car": {"make": "Toyota", "model": "Corolla", "value": 100000.0, "year": 2016},
    "deductible_percentage": 0.10,
}


def _post(client, **overrides):
    payload = {**_EXAMPLE_A, **overrides}
    return client.post("/api/v1/premiums/calculate", json=payload)


def test_domain_error_body_has_fastapi_shape(client) -> None:
    response = _post(client, car={**_EXAMPLE_A["car"], "year": 3000})
    assert response.status_code == 422
    body = response.json()
    assert isinstance(body["detail"], list)
    item = body["detail"][0]
    assert set(item) == {"loc", "msg", "type"}
    assert isinstance(item["loc"], list)


def test_schema_error_also_422(client) -> None:
    response = _post(client, deductible_percentage="not-a-number")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    # normalised: exactly loc/msg/type, never Pydantic's echoed ``input`` / ``ctx``
    for item in detail:
        assert set(item) == {"loc", "msg", "type"}


def test_nan_and_infinity_rejected(client) -> None:
    for bad in ("NaN", "Infinity", "-Infinity"):
        assert _post(client, broker_fee=bad).status_code == 422


def test_empty_make_rejected(client) -> None:
    assert _post(client, car={**_EXAMPLE_A["car"], "make": "   "}).status_code == 422


def test_deductible_just_above_maximum_rejected(client) -> None:
    assert _post(client, deductible_percentage=1.0000001).status_code == 422


def test_deductible_at_maximum_allowed(client) -> None:
    response = _post(client, deductible_percentage=1.0)
    assert response.status_code == 200
    body = response.json()
    assert body["calculated_premium"] == 50.0
    assert body["policy_limit"] == 0.0


def test_bad_uuid_path_is_422_not_500(client) -> None:
    response = client.get("/api/v1/premiums/not-a-uuid")
    assert response.status_code == 422


def test_valid_uuid_absent_is_404(client) -> None:
    response = client.get(f"/api/v1/premiums/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json() == {"detail": "simulation not found"}


def test_limit_out_of_range_is_422(client) -> None:
    assert client.get("/api/v1/premiums?limit=0").status_code == 422
    assert client.get("/api/v1/premiums?limit=101").status_code == 422


def test_car_object_never_leaks_extra_fields(client) -> None:
    body = _post(
        client,
        registration_location={"country": "US", "postal_code": "90001", "region": "CA"},
    ).json()
    assert set(body["car"]) == {"make", "model", "value", "year"}
    for leaked in (
        "broker_fee",
        "deductible_percentage",
        "registration_location",
        "simulation_id",
        "rules_version",
        "created_at",
    ):
        assert leaked not in body
