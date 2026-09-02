"""Tests for the HTTP geographic rate provider (httpx mocked)."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from car_insurance.application.ports.geographic_rate_provider import (
    GeographicRateProviderError,
)
from car_insurance.domain.value_objects.address import Address
from car_insurance.infrastructure.gis.http_geographic_rate_provider import (
    HttpGeographicRateProvider,
)

_ADDRESS = Address(country="US", region="SecretRegion", postal_code="SECRET123", city="SecretCity")


def _provider(**overrides: object) -> HttpGeographicRateProvider:
    kwargs: dict[str, object] = {
        "api_key": "secret",
        "base_url": "https://gis.example/",
        "failure_mode": "fail_closed",
        "max_adjustment": Decimal("0.02"),
        "min_adjustment": Decimal("-0.02"),
        "timeout_seconds": 1.0,
    }
    kwargs.update(overrides)
    return HttpGeographicRateProvider(**kwargs)  # type: ignore[arg-type]


def _patch_post(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    monkeypatch.setattr(httpx, "post", handler)

    # GET is where the query string (and thus a URL-logged location) would live —
    # make any accidental fallback to it an unmistakable failure.
    def _forbidden_get(*_a: object, **_k: object) -> httpx.Response:
        raise AssertionError("the GIS adapter must use POST, not GET")

    monkeypatch.setattr(httpx, "get", _forbidden_get)


def test_valid_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(url, **kwargs):
        assert kwargs["headers"] == {"X-API-Key": "secret"}
        assert kwargs["json"] == {
            "city": "SecretCity",
            "country": "US",
            "postal_code": "SECRET123",
            "region": "SecretRegion",
        }
        return httpx.Response(200, json={"adjustment": 0.01}, request=httpx.Request("POST", url))

    _patch_post(monkeypatch, handler)
    assert _provider().adjustment_for(address=_ADDRESS).value == Decimal("0.01")


def test_location_never_reaches_the_url(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def handler(url, **kwargs):
        seen["url"] = str(url)
        seen["kwargs"] = kwargs
        return httpx.Response(200, json={"adjustment": 0.0}, request=httpx.Request("POST", url))

    _patch_post(monkeypatch, handler)
    _provider(api_key=None).adjustment_for(address=_ADDRESS)

    assert "params" not in seen["kwargs"]  # type: ignore[operator]
    assert "?" not in seen["url"]  # type: ignore[operator]
    for secret in ("SecretCity", "SecretRegion", "SECRET123"):
        assert secret not in seen["url"]  # type: ignore[operator]
        assert secret in str(seen["kwargs"]["json"])  # type: ignore[index]


def test_timeout_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(url, **kwargs):
        raise httpx.TimeoutException("slow")

    _patch_post(monkeypatch, handler)
    with pytest.raises(GeographicRateProviderError):
        _provider().adjustment_for(address=_ADDRESS)


def test_timeout_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(url, **kwargs):
        raise httpx.TimeoutException("slow")

    _patch_post(monkeypatch, handler)
    result = _provider(failure_mode="fail_open").adjustment_for(address=_ADDRESS)
    assert result.value == Decimal(0)


def test_out_of_range_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(url, **kwargs):
        return httpx.Response(200, json={"adjustment": 0.5}, request=httpx.Request("POST", url))

    _patch_post(monkeypatch, handler)
    with pytest.raises(GeographicRateProviderError):
        _provider().adjustment_for(address=_ADDRESS)


def test_missing_key_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(url, **kwargs):
        return httpx.Response(200, json={"nope": 1}, request=httpx.Request("POST", url))

    _patch_post(monkeypatch, handler)
    assert _provider(api_key=None, failure_mode="fail_open").adjustment_for(
        address=_ADDRESS
    ).value == Decimal(0)
