"""``GeographicRateProvider`` port — resolves an address to a rate adjustment."""

from __future__ import annotations

from typing import Protocol

from car_insurance.domain.value_objects.address import Address
from car_insurance.domain.value_objects.geographic_rate_adjustment import GeographicRateAdjustment


class GeographicRateProviderError(Exception):
    """Raised when the provider cannot return a valid adjustment (fail-closed)."""


class GeographicRateProvider(Protocol):
    """Returns the additive :class:`GeographicRateAdjustment` for an address."""

    def adjustment_for(self, *, address: Address) -> GeographicRateAdjustment: ...
