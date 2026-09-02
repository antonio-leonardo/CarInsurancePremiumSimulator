"""Regression tests for the blind-audit findings (do not let them come back)."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
import structlog
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from car_insurance.presentation.api import dependencies
from car_insurance.presentation.api.app import create_app

_EXAMPLE = {
    "broker_fee": 50.0,
    "car": {"make": "Toyota", "model": "Corolla", "value": 100000.0, "year": 2016},
    "deductible_percentage": 0.10,
}


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
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
    structlog.reset_defaults()


# --- #2: invalid rule config must stop the process at startup -------------------


@pytest.mark.parametrize(
    "env",
    [
        {"VALUE_BAND_AMOUNT": "0"},
        {"MAX_DEDUCTIBLE_PERCENTAGE": "1.5"},
        {"COVERAGE_PERCENTAGE": "0"},
        {"MAXIMUM_APPLIED_RATE": "0.1234565"},  # not representable at 6 places
    ],
)
def test_bad_rule_config_prevents_boot(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    for cached in (dependencies.get_settings, dependencies.get_rating_rules):
        cached.cache_clear()
    with pytest.raises(Exception):  # noqa: B017 - RatingRulesError / ValidationError
        create_app()


# --- #3: a >100% deductible is impossible even if misconfigured -----------------


def test_deductible_above_one_is_rejected_by_the_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_DEDUCTIBLE_PERCENTAGE", "1.0")
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/premiums/calculate", json={**_EXAMPLE, "deductible_percentage": 1.5}
    )
    assert response.status_code == 422


# --- #1: huge value -> 422, never a 500; echo stays exact ----------------------


def test_huge_value_is_422_not_500() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/premiums/calculate",
        json={**_EXAMPLE, "car": {**_EXAMPLE["car"], "value": 1e30}},
    )
    assert response.status_code == 422


def test_large_integer_value_echo_is_exact() -> None:
    client = TestClient(create_app())
    value = 90000000000  # 9e10, within the cap, an exact JSON integer
    body = client.post(
        "/api/v1/premiums/calculate",
        json={**_EXAMPLE, "car": {**_EXAMPLE["car"], "value": value}},
    ).json()
    assert body["car"]["value"] == value


# --- #7: stateless service survives an invalid DATABASE_URL --------------------


def test_stateless_ignores_an_unreachable_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@nohost:5432/db")
    client = TestClient(create_app())

    assert client.get("/health/ready").status_code == 200
    assert client.post("/api/v1/premiums/calculate", json=_EXAMPLE).status_code == 200
    assert client.get("/api/v1/premiums").json() == {"items": [], "next_cursor": None}


def test_malformed_dsn_stops_the_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("DATABASE_URL", "totally-not-a-dsn")
    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError wraps our ValueError
        create_app()


# --- #4: GIS diagnostics never carry the location -----------------------------


def test_gis_fallback_log_has_no_location(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIS_ENABLED", "true")
    monkeypatch.setenv("GIS_BASE_URL", "https://gis.example")
    monkeypatch.setenv("GIS_FAILURE_MODE", "fail_open")

    def _explode(url, **kwargs):
        raise httpx.HTTPStatusError(
            f"500 for {url}?city=SecretCity&postal_code=99999",
            request=httpx.Request("POST", url),
            response=httpx.Response(500, request=httpx.Request("POST", url)),
        )

    monkeypatch.setattr(httpx, "post", _explode)
    client = TestClient(create_app())
    with capture_logs() as events:
        body = client.post(
            "/api/v1/premiums/calculate",
            json={
                **_EXAMPLE,
                "registration_location": {
                    "country": "US",
                    "city": "SecretCity",
                    "postal_code": "99999",
                    "region": "SecretRegion",
                },
            },
        ).json()

    assert body["applied_rate"] == 0.1  # fell back to zero adjustment
    blob = repr(events)
    for secret in ("SecretCity", "SecretRegion", "99999"):
        assert secret not in blob


# --- #8: a malformed GIS 200 body honours the failure mode --------------------


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("fail_open", 200), ("fail_closed", 503)],
)
def test_gis_list_body_is_not_a_500(
    mode: str, expected: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIS_ENABLED", "true")
    monkeypatch.setenv("GIS_BASE_URL", "https://gis.example")
    monkeypatch.setenv("GIS_FAILURE_MODE", mode)
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, **_: httpx.Response(200, json=[], request=httpx.Request("POST", url)),
    )
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/premiums/calculate",
        json={**_EXAMPLE, "registration_location": {"country": "US"}},
    )
    assert response.status_code == expected
