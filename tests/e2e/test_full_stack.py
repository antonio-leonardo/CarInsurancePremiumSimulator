"""End-to-end tests: the real ASGI app over real transport and real storage.

Unlike the ``tests/api`` suite (which injects fakes) and ``tests/persistence``
(PostgreSQL via testcontainers), these exercise the wiring the way production
runs it:

* the GIS adapter makes a **real** ``httpx`` POST to a throwaway local HTTP
  server — so serialization, timeouts and connection failures are exercised for
  real, not monkeypatched;
* persistence runs against a **real** on-disk SQLite database created by the
  **real** Alembic migration (``alembic upgrade head``), driven through the HTTP
  surface (`POST` → `GET {id}` → `GET` list → pagination → 404);
* the OpenAPI document is the one FastAPI actually serves.

Marked ``e2e``; still part of the default ``-m "not integration"`` run because
everything is self-contained (a background thread + a temp file).
"""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import structlog
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from car_insurance.presentation.api import dependencies
from car_insurance.presentation.api.app import create_app

pytestmark = pytest.mark.e2e

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CAR_YEAR = datetime.now(UTC).year - 10  # car_age == 10 in every calendar year
_EXAMPLE = {
    "broker_fee": 50.0,
    "car": {"make": "Toyota", "model": "Corolla", "value": 100000.0, "year": _CAR_YEAR},
    "deductible_percentage": 0.10,
}
_CACHES = (
    dependencies._engine,
    dependencies._session_factory,
    dependencies.get_rating_rules,
    dependencies.get_settings,
)


@pytest.fixture(autouse=True)
def _reset_wiring() -> Iterator[None]:
    for cached in _CACHES:
        cached.cache_clear()
    yield
    for cached in _CACHES:
        cached.cache_clear()
    structlog.reset_defaults()


def _client(monkeypatch: pytest.MonkeyPatch, **env: str) -> TestClient:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    for cached in _CACHES:
        cached.cache_clear()
    return TestClient(create_app())


GisHandler = Callable[[dict[str, object]], "tuple[int, object] | None"]


@contextmanager
def _gis_server(handler: GisHandler) -> Iterator[str]:
    """Run a one-route HTTP server; ``handler`` returns ``(status, payload)`` or
    ``None`` to drop the connection (simulating a transport failure)."""

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: object) -> None:  # silence the default stderr spam
            return

        def do_POST(self) -> None:
            length = int(self.headers.get("content-length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            result = handler(body)
            if result is None:
                self.close_connection = True
                return
            status, payload = result
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _free_port() -> int:
    with closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


# --------------------------------------------------------------------------- #
# Stateless happy path                                                        #
# --------------------------------------------------------------------------- #


def test_stateless_calculate_is_canonical_and_leaks_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(monkeypatch)
    with capture_logs() as logs:
        response = client.post(
            "/api/v1/premiums/calculate",
            json=_EXAMPLE,
            headers={"X-Request-ID": "e2e-trace-01"},
        )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "e2e-trace-01"
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
    # The business audit line was emitted and no log line carries the raw broker fee.
    assert any(line["event"] == "premium.calculated" for line in logs)
    assert "broker_fee" not in json.dumps(logs)


@pytest.mark.parametrize("hostile", ["x" * 200, "has spaces", "tab\there", "a;b=c"])
def test_hostile_request_id_is_dropped_not_echoed(
    hostile: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(monkeypatch)
    response = client.post(
        "/api/v1/premiums/calculate", json=_EXAMPLE, headers={"X-Request-ID": hostile}
    )
    echoed = response.headers["x-request-id"]
    assert echoed != hostile
    # what actually gets echoed is a plain UUID
    assert len(echoed) == 36 and echoed.count("-") == 4


def test_served_openapi_is_valid_and_documents_every_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(monkeypatch)
    schema = client.get("/openapi.json").json()

    operations = {
        (path, method): spec.get("operationId")
        for path, methods in schema["paths"].items()
        for method, spec in methods.items()
    }
    assert operations[("/api/v1/premiums/calculate", "post")] == "calculatePremium"
    assert operations[("/api/v1/premiums", "get")] == "listSimulations"
    assert operations[("/api/v1/premiums/{simulation_id}", "get")] == "getSimulation"
    assert operations[("/health/live", "get")] == "healthLive"
    assert operations[("/health/ready", "get")] == "healthReady"

    calc = schema["paths"]["/api/v1/premiums/calculate"]["post"]
    assert set(calc["responses"]) >= {"200", "422", "500", "503"}
    assert set(schema["paths"]["/health/ready"]["get"]["responses"]) >= {"200", "503"}
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200


# --------------------------------------------------------------------------- #
# Real GIS transport                                                          #
# --------------------------------------------------------------------------- #


def test_gis_adjusts_the_rate_over_real_http(monkeypatch: pytest.MonkeyPatch) -> None:
    received: list[dict[str, object]] = []

    def handler(body: dict[str, object]) -> tuple[int, object]:
        received.append(body)
        return 200, {"adjustment": 0.01}

    with _gis_server(handler) as base_url:
        client = _client(
            monkeypatch,
            GIS_ENABLED="true",
            GIS_BASE_URL=base_url,
            GIS_FAILURE_MODE="fail_closed",
        )
        body = client.post(
            "/api/v1/premiums/calculate",
            json={**_EXAMPLE, "registration_location": {"country": "US", "city": "Denver"}},
        ).json()

    assert body["applied_rate"] == 0.11  # 0.10 base + 0.01 geographic
    assert body["calculated_premium"] == 9950.0  # 11000 - 1100 + 50
    assert received == [{"country": "US", "city": "Denver"}]  # POST body, not query string


@pytest.mark.parametrize(("mode", "expected"), [("fail_closed", 503), ("fail_open", 200)])
def test_gis_upstream_500_honours_failure_mode_over_real_http(
    mode: str, expected: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _gis_server(lambda _body: (500, {"error": "boom"})) as base_url:
        client = _client(
            monkeypatch,
            GIS_ENABLED="true",
            GIS_BASE_URL=base_url,
            GIS_FAILURE_MODE=mode,
        )
        with capture_logs() as logs:
            response = client.post(
                "/api/v1/premiums/calculate",
                json={
                    **_EXAMPLE,
                    "registration_location": {
                        "country": "US",
                        "city": "SecretCity",
                        "postal_code": "SECRET99",
                        "region": "SecretRegion",
                    },
                },
            )

    assert response.status_code == expected
    if expected == 200:
        assert response.json()["applied_rate"] == 0.1  # fell back to zero adjustment
    for secret in ("SecretCity", "SecretRegion", "SECRET99"):
        assert secret not in json.dumps(logs)


@pytest.mark.parametrize(("mode", "expected"), [("fail_closed", 503), ("fail_open", 200)])
def test_gis_connection_refused_honours_failure_mode(
    mode: str, expected: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    dead = _free_port()  # allocated, then released — nothing is listening
    client = _client(
        monkeypatch,
        GIS_ENABLED="true",
        GIS_BASE_URL=f"http://127.0.0.1:{dead}",
        GIS_FAILURE_MODE=mode,
        GIS_TIMEOUT_SECONDS="1.0",
    )
    response = client.post(
        "/api/v1/premiums/calculate",
        json={**_EXAMPLE, "registration_location": {"country": "US"}},
    )
    assert response.status_code == expected


@pytest.mark.parametrize(("mode", "expected"), [("fail_closed", 503), ("fail_open", 200)])
def test_gis_timeout_honours_failure_mode(
    mode: str, expected: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    import time

    def slow(_body: dict[str, object]) -> tuple[int, object]:
        time.sleep(0.8)
        return 200, {"adjustment": 0.0}

    with _gis_server(slow) as base_url:
        client = _client(
            monkeypatch,
            GIS_ENABLED="true",
            GIS_BASE_URL=base_url,
            GIS_FAILURE_MODE=mode,
            GIS_TIMEOUT_SECONDS="0.2",
        )
        response = client.post(
            "/api/v1/premiums/calculate",
            json={**_EXAMPLE, "registration_location": {"country": "US"}},
        )
    assert response.status_code == expected


# --------------------------------------------------------------------------- #
# Real persistence: real SQLite file + real Alembic migration                 #
# --------------------------------------------------------------------------- #


@pytest.fixture
def migrated_sqlite(tmp_path: Path) -> str:
    db_path = tmp_path / "e2e.db"
    url = f"sqlite:///{db_path}"
    config = Config(str(_REPO_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    return url


def test_persisted_history_round_trips_through_http(
    migrated_sqlite: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(
        monkeypatch,
        PERSISTENCE_ENABLED="true",
        DATABASE_URL=migrated_sqlite,
    )

    assert client.get("/health/ready").status_code == 200

    created_ids = []
    for _ in range(3):
        created = client.post("/api/v1/premiums/calculate", json=_EXAMPLE)
        assert created.status_code == 200
        # the calculate response is still the narrow 5-field contract
        assert "simulation_id" not in created.json()

    listing = client.get("/api/v1/premiums?limit=2").json()
    assert len(listing["items"]) == 2
    assert listing["next_cursor"] is not None
    created_ids = [item["simulation_id"] for item in listing["items"]]

    page2 = client.get(f"/api/v1/premiums?limit=2&cursor={listing['next_cursor']}").json()
    assert len(page2["items"]) == 1
    assert page2["items"][0]["simulation_id"] not in created_ids

    record = client.get(f"/api/v1/premiums/{created_ids[0]}").json()
    assert record["calculated_premium"] == 9050.0
    assert record["rules_version"] == "2026.08.0"
    assert set(record["car"]) == {"make", "model", "value", "year"}

    missing = client.get("/api/v1/premiums/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404


def test_malformed_cursor_is_422_not_500(
    migrated_sqlite: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(
        monkeypatch,
        PERSISTENCE_ENABLED="true",
        DATABASE_URL=migrated_sqlite,
    )
    response = client.get("/api/v1/premiums?cursor=not-a-real-cursor")
    assert response.status_code == 422
    for item in response.json()["detail"]:
        assert set(item) == {"loc", "msg", "type"}


def test_outbox_row_is_written_in_the_same_transaction(
    migrated_sqlite: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy import create_engine, text

    client = _client(
        monkeypatch,
        PERSISTENCE_ENABLED="true",
        DATABASE_URL=migrated_sqlite,
    )
    client.post("/api/v1/premiums/calculate", json=_EXAMPLE)

    engine = create_engine(migrated_sqlite)
    with engine.connect() as connection:
        simulations = connection.execute(text("SELECT count(*) FROM premium_simulations")).scalar()
        outbox = connection.execute(text("SELECT count(*) FROM event_outbox")).scalar()
        payload = connection.execute(text("SELECT payload FROM event_outbox")).scalar_one()
    engine.dispose()

    assert simulations == 1
    assert outbox == 1
    assert "broker_fee" not in str(payload)


def test_stateless_mode_survives_a_dead_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    # persistence OFF: an unreachable DSN must not touch the request path at all.
    client = _client(
        monkeypatch,
        PERSISTENCE_ENABLED="false",
        DATABASE_URL="postgresql+psycopg://nobody:nobody@127.0.0.1:1/missing",
    )
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200
    assert client.post("/api/v1/premiums/calculate", json=_EXAMPLE).status_code == 200
    assert client.get("/api/v1/premiums").json() == {"items": [], "next_cursor": None}


def test_decimal_precision_config_flows_end_to_end(
    migrated_sqlite: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # MONEY_DECIMAL_PLACES=4 must reach both the response and the stored history
    # (the NUMERIC columns carry no fixed scale — audit finding A5).
    client = _client(
        monkeypatch,
        PERSISTENCE_ENABLED="true",
        DATABASE_URL=migrated_sqlite,
        MONEY_DECIMAL_PLACES="4",
    )
    body = client.post(
        "/api/v1/premiums/calculate",
        json={**_EXAMPLE, "car": {**_EXAMPLE["car"], "value": 100000.55}},
    ).json()
    # 100000.55 * 0.10 = 10000.055 ; discount 1000.0055 ; + 50 -> 9050.0495 (4 dp)
    assert Decimal(str(body["calculated_premium"])) == Decimal("9050.0495")
    listing = client.get("/api/v1/premiums").json()
    stored = client.get(f"/api/v1/premiums/{listing['items'][0]['simulation_id']}").json()
    assert stored["calculated_premium"] == body["calculated_premium"]
