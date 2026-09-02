"""Permanent guard for the blind adversarial audit (findings A1-A9).

Each scenario below reproduces — exactly — a defect confirmed live against the
worktree during the audit. If any of these goes green with a fix reverted, the
defect is back. See ``docs/REMEDIATION.md`` for the finding → fix → test map.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import structlog
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from car_insurance.presentation.api import dependencies
from car_insurance.presentation.api.app import create_app

# Derive the model year from "now" so ``car_age`` is a constant 10 every calendar
# year — the same discipline the CI smoke uses (finding A6). Rate is then always
# base(0) + age(10 * 0.005) + value(10 bands * 0.005) = 0.10.
_CAR_YEAR = datetime.now(UTC).year - 10
_EXAMPLE = {
    "broker_fee": 50.0,
    "car": {"make": "Toyota", "model": "Corolla", "value": 100000.0, "year": _CAR_YEAR},
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


def _client(monkeypatch: pytest.MonkeyPatch, **env: str) -> TestClient:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    for cached in (dependencies.get_settings, dependencies.get_rating_rules):
        cached.cache_clear()
    return TestClient(create_app())


# --- A1: Decimal->float echo corruption; car.value with no ceiling -> HTTP 500 --


def test_a1_value_1e100_is_422_with_validation_body() -> None:
    response = TestClient(create_app()).post(
        "/api/v1/premiums/calculate",
        json={**_EXAMPLE, "car": {**_EXAMPLE["car"], "value": 1e100}},
    )
    assert response.status_code == 422
    body = response.json()
    assert isinstance(body["detail"], list)
    for item in body["detail"]:
        assert set(item) == {"loc", "msg", "type"}


def test_a1_boundary_values_echo_exactly() -> None:
    client = TestClient(create_app())
    body = client.post(
        "/api/v1/premiums/calculate",
        json={
            "broker_fee": 12345.67,
            "car": {**_EXAMPLE["car"], "value": 99999999999.99},
            "deductible_percentage": 0.10,
        },
    ).json()
    assert Decimal(str(body["car"]["value"])) == Decimal("99999999999.99")


@pytest.mark.parametrize("cents", ["0.01", "0.25", "0.99", "0.50"])
def test_a1_property_two_places_round_trip(cents: str) -> None:
    client = TestClient(create_app())
    value = Decimal("50000000000") + Decimal(cents)  # within [1, 1e11], 2 places
    body = client.post(
        "/api/v1/premiums/calculate",
        json={**_EXAMPLE, "car": {**_EXAMPLE["car"], "value": float(value)}},
    ).json()
    assert Decimal(str(body["car"]["value"])) == value


def test_a1_vehicle_value_ceiling_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    # A value that passes the schema guard but exceeds the configured ceiling is
    # a 422 from the use case, never a 500.
    client = _client(monkeypatch, MAX_VEHICLE_VALUE="50000")
    response = client.post(
        "/api/v1/premiums/calculate",
        json={**_EXAMPLE, "car": {**_EXAMPLE["car"], "value": 100000.0}},
    )
    assert response.status_code == 422


def test_a1_broker_fee_ceiling_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    over_default = 5_000_000_000  # above MAX_BROKER_FEE=1e9, below the 1e11 schema guard
    assert (
        TestClient(create_app())
        .post("/api/v1/premiums/calculate", json={**_EXAMPLE, "broker_fee": over_default})
        .status_code
        == 422
    )
    client = _client(monkeypatch, MAX_BROKER_FEE="1e10")
    assert (
        client.post(
            "/api/v1/premiums/calculate", json={**_EXAMPLE, "broker_fee": over_default}
        ).status_code
        == 200
    )


# --- A2: an invalid rule configuration must not reach a serving state ----------


@pytest.mark.parametrize(
    "env",
    [
        {"VALUE_BAND_AMOUNT": "0"},
        {"COVERAGE_PERCENTAGE": "0"},
        {"MAX_DEDUCTIBLE_PERCENTAGE": "1.5"},
        {"MAXIMUM_APPLIED_RATE": "0.1234565"},
        {"MAX_BROKER_FEE": "0"},
    ],
)
def test_a2_bad_rule_config_prevents_boot(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    for cached in (dependencies.get_settings, dependencies.get_rating_rules):
        cached.cache_clear()
    with pytest.raises(Exception):  # noqa: B017 — RatingRulesError / ValidationError
        create_app()


# --- A3: MAX_DEDUCTIBLE_PERCENTAGE > 1 accepts a nonsensical deductible --------


def test_a3_deductible_above_one_is_422() -> None:
    assert (
        TestClient(create_app())
        .post("/api/v1/premiums/calculate", json={**_EXAMPLE, "deductible_percentage": 1.5})
        .status_code
        == 422
    )


def test_a3_deductible_at_one_is_200_with_zero_limit() -> None:
    body = (
        TestClient(create_app())
        .post("/api/v1/premiums/calculate", json={**_EXAMPLE, "deductible_percentage": 1.0})
        .json()
    )
    assert body["calculated_premium"] == 50.0  # == broker_fee
    assert body["policy_limit"] == 0.0


# --- A4 (worst): sensitive location must never reach any log ------------------


@pytest.mark.parametrize("mode", ["fail_open", "fail_closed"])
def test_a4_gis_failure_never_logs_the_location(
    mode: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def _explode(url: str, **_: object) -> httpx.Response:
        raise httpx.HTTPStatusError(
            f"500 for {url} city=SecretCity postal_code=12345 region=SecretRegion",
            request=httpx.Request("POST", url),
            response=httpx.Response(500, request=httpx.Request("POST", url)),
        )

    monkeypatch.setattr(httpx, "post", _explode)
    client = _client(
        monkeypatch,
        GIS_ENABLED="true",
        GIS_BASE_URL="https://gis.example",
        GIS_FAILURE_MODE=mode,
    )
    location = {
        "country": "US",
        "city": "SecretCity",
        "postal_code": "12345",
        "region": "SecretRegion",
    }
    with caplog.at_level(logging.DEBUG), capture_logs() as events:
        client.post(
            "/api/v1/premiums/calculate",
            json={**_EXAMPLE, "registration_location": location},
        )

    haystack = repr(events) + "\n" + caplog.text
    for secret in ("SecretCity", "SecretRegion", "12345"):
        assert secret not in haystack


def test_a4_httpx_loggers_are_pinned_to_warning() -> None:
    create_app()  # calls configure_logging
    assert logging.getLogger("httpx").level >= logging.WARNING
    assert logging.getLogger("httpcore").level >= logging.WARNING


# --- A5: the PostgreSQL schema must not fix money/rate precision --------------


def test_a5_numeric_columns_are_unbounded() -> None:
    from car_insurance.infrastructure.persistence.models import PremiumSimulationRecord

    for column in ("applied_rate", "calculated_premium", "vehicle_value"):
        numeric = PremiumSimulationRecord.__table__.c[column].type
        assert numeric.precision is None and numeric.scale is None


# --- A6: the CI smoke must not hard-code a single calendar year --------------


def test_a6_ci_smoke_derives_the_year_dynamically() -> None:
    ci = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml").read_text()
    assert "date -u +%Y" in ci
    assert "$(( $(date -u +%Y) - 10 ))" in ci
    assert "$(( $(date -u +%Y) - 14 ))" in ci


# --- A7: stateless mode must survive an unreachable / invalid DSN ------------


def test_a7_stateless_survives_unreachable_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(
        monkeypatch,
        PERSISTENCE_ENABLED="false",
        DATABASE_URL="postgresql+psycopg://u:p@nohost:5432/db",
    )
    assert client.get("/health/ready").status_code == 200
    assert client.post("/api/v1/premiums/calculate", json=_EXAMPLE).status_code == 200


def test_a7_persistence_on_with_bad_dsn_fails_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSISTENCE_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "not-a-dsn")
    for cached in (dependencies.get_settings, dependencies.get_rating_rules):
        cached.cache_clear()
    with pytest.raises(Exception):  # noqa: B017
        create_app()


# --- A8: a malformed GIS 200 body must honour the failure mode, never 500 ----


@pytest.mark.parametrize(
    "payload",
    [[], {}, {"adjustment": "abc"}, "x", {"adjustment": None}],
)
@pytest.mark.parametrize(
    ("mode", "expected"),
    [("fail_open", 200), ("fail_closed", 503)],
)
def test_a8_malformed_gis_body_routes_through_failure_mode(
    payload: object,
    mode: str,
    expected: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, **_: httpx.Response(200, json=payload, request=httpx.Request("POST", url)),
    )
    client = _client(
        monkeypatch,
        GIS_ENABLED="true",
        GIS_BASE_URL="https://gis.example",
        GIS_FAILURE_MODE=mode,
    )
    response = client.post(
        "/api/v1/premiums/calculate",
        json={**_EXAMPLE, "registration_location": {"country": "US"}},
    )
    assert response.status_code == expected
    if mode == "fail_open":
        assert response.json()["applied_rate"] == 0.1  # no adjustment applied


# --- A9: a configured rate ceiling must not be exceeded ----------------------


def test_a9_unrepresentable_max_rate_fails_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAXIMUM_APPLIED_RATE", "0.1234565")  # 7 places, RATE_DECIMAL_PLACES=6
    for cached in (dependencies.get_settings, dependencies.get_rating_rules):
        cached.cache_clear()
    with pytest.raises(Exception):  # noqa: B017
        create_app()


def test_a9_representable_max_rate_boots(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, MAXIMUM_APPLIED_RATE="0.123456")
    assert client.post("/api/v1/premiums/calculate", json=_EXAMPLE).status_code == 200
