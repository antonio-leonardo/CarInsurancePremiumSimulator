"""``HttpGeographicRateProvider`` — calls an external geographic risk service."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import httpx
import structlog

from car_insurance.application.ports.geographic_rate_provider import GeographicRateProviderError
from car_insurance.domain.errors import GeographicRateAdjustmentError
from car_insurance.domain.value_objects.address import Address
from car_insurance.domain.value_objects.geographic_rate_adjustment import GeographicRateAdjustment

_FAIL_OPEN = "fail_open"
_logger = structlog.get_logger(__name__)


class HttpGeographicRateProvider:
    """Resolves an :class:`Address` to an adjustment via HTTP, honouring the failure mode.

    On timeout, transport error, a malformed body or an out-of-range value:
    ``fail_closed`` raises :class:`GeographicRateProviderError` (the API turns it
    into a 503); ``fail_open`` logs a warning and falls back to a zero
    adjustment.  Diagnostic logs never contain the address or the request URL —
    only the exception *type*.  The location travels in the JSON request **body**
    of a POST (never the query string), so not even an httpx WARNING/ERROR log
    of a failed request URL can carry it.
    """

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        failure_mode: str,
        max_adjustment: Decimal,
        min_adjustment: Decimal,
        timeout_seconds: float,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._failure_mode = failure_mode
        self._max_adjustment = max_adjustment
        self._min_adjustment = min_adjustment
        self._timeout_seconds = timeout_seconds

    def _fallback(self, *, cause: str, reason: str) -> GeographicRateAdjustment:
        if self._failure_mode == _FAIL_OPEN:
            # ``cause`` is a bare exception class name / short tag — never a
            # message, which could echo the URL and its location query string.
            _logger.warning("gis.fallback", cause=cause, reason=reason)
            return GeographicRateAdjustment.zero()
        raise GeographicRateProviderError(reason)

    def adjustment_for(self, *, address: Address) -> GeographicRateAdjustment:
        """Query the service for ``address`` and validate the response range."""

        headers = {"X-API-Key": self._api_key} if self._api_key else {}
        location = {
            "city": address.city,
            "country": address.country,
            "postal_code": address.postal_code,
            "region": address.region,
        }
        try:
            response = httpx.post(
                f"{self._base_url}/adjustments",
                headers=headers,
                json={key: value for key, value in location.items() if value is not None},
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict):
                raise TypeError("adjustment response body is not a JSON object")
            raw_adjustment = body["adjustment"]
        except (httpx.HTTPError, LookupError, TypeError, ValueError) as exc:
            return self._fallback(cause=type(exc).__name__, reason="geographic risk service error")

        try:
            return GeographicRateAdjustment.within(
                maximum=self._max_adjustment,
                minimum=self._min_adjustment,
                value=Decimal(str(raw_adjustment)),
            )
        except (GeographicRateAdjustmentError, InvalidOperation):
            return self._fallback(
                cause="OutOfRange",
                reason="geographic risk service returned an out-of-range value",
            )
