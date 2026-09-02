"""HTTP contract tests for the premium endpoints."""

from __future__ import annotations

_EXAMPLE_A = {
    "broker_fee": 50.0,
    "car": {"make": "Toyota", "model": "Corolla", "value": 100000.0, "year": 2016},
    "deductible_percentage": 0.10,
}


def test_calculate_returns_exactly_five_fields(client) -> None:
    response = client.post("/api/v1/premiums/calculate", json=_EXAMPLE_A)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "applied_rate",
        "calculated_premium",
        "car",
        "deductible_value",
        "policy_limit",
    }
    assert set(body["car"]) == {"make", "model", "value", "year"}
    assert body["applied_rate"] == 0.1
    assert body["calculated_premium"] == 9050.0
    assert body["deductible_value"] == 10000.0
    assert body["policy_limit"] == 90000.0


def test_calculate_example_b(client) -> None:
    payload = {**_EXAMPLE_A, "car": {**_EXAMPLE_A["car"], "year": 2012}}
    body = client.post("/api/v1/premiums/calculate", json=payload).json()
    assert body["applied_rate"] == 0.12
    assert body["calculated_premium"] == 10850.0


def test_calculate_does_not_echo_location(client) -> None:
    payload = {
        **_EXAMPLE_A,
        "registration_location": {
            "country": "US",
            "postal_code": "90001",
            "region": "CA",
        },
    }
    body = client.post("/api/v1/premiums/calculate", json=payload).json()
    assert "registration_location" not in body
    assert "broker_fee" not in body


def test_future_year_is_422(client) -> None:
    payload = {**_EXAMPLE_A, "car": {**_EXAMPLE_A["car"], "year": 2999}}
    response = client.post("/api/v1/premiums/calculate", json=payload)
    assert response.status_code == 422
    assert "detail" in response.json()


def test_negative_value_is_422(client) -> None:
    payload = {**_EXAMPLE_A, "car": {**_EXAMPLE_A["car"], "value": -1.0}}
    assert client.post("/api/v1/premiums/calculate", json=payload).status_code == 422


def test_unknown_field_is_422(client) -> None:
    payload = {**_EXAMPLE_A, "surprise": 1}
    assert client.post("/api/v1/premiums/calculate", json=payload).status_code == 422


def test_gis_unavailable_returns_503(api_context) -> None:
    from tests.conftest import FakeGeographicRateProvider

    client = api_context["client"]
    from datetime import UTC, datetime

    from car_insurance.application.use_cases.calculate_premium import CalculatePremium
    from car_insurance.infrastructure.config.rules_factory import build_rating_rules
    from car_insurance.infrastructure.config.settings import Settings
    from car_insurance.presentation.api import dependencies
    from tests.conftest import FakeLogger, FixedClock

    settings = Settings()
    failing = CalculatePremium(
        clock=FixedClock(moment=datetime(2026, 3, 1, tzinfo=UTC)),
        event_publisher=api_context["publisher"],
        geographic_rate_provider=FakeGeographicRateProvider(error=True),
        logger=FakeLogger(),
        maximum_broker_fee=settings.max_broker_fee,
        maximum_vehicle_value=settings.max_vehicle_value,
        persistence_failure_mode="fail_closed",
        repository=api_context["repository"],
        rules=build_rating_rules(settings=settings),
    )
    client.app.dependency_overrides[dependencies.get_calculate_premium] = lambda: failing

    payload = {**_EXAMPLE_A, "registration_location": {"country": "US"}}
    response = client.post("/api/v1/premiums/calculate", json=payload)
    assert response.status_code == 503
    assert response.json() == {"detail": "geographic risk service unavailable"}


def test_history_is_404_when_persistence_disabled(client) -> None:
    response = client.get("/api/v1/premiums/123e4567-e89b-12d3-a456-426614174000")
    assert response.status_code == 404


def test_history_list_is_empty_when_persistence_disabled(client) -> None:
    body = client.get("/api/v1/premiums").json()
    assert body == {"items": [], "next_cursor": None}


def test_request_id_header_round_trips(client) -> None:
    response = client.post(
        "/api/v1/premiums/calculate",
        json=_EXAMPLE_A,
        headers={"X-Request-ID": "abc-123"},
    )
    assert response.headers["X-Request-ID"] == "abc-123"
