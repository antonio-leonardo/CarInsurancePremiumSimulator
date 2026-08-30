"""``NullGeographicRateProvider`` — always a zero adjustment."""

from __future__ import annotations

from car_insurance.domain.value_objects.address import Address
from car_insurance.domain.value_objects.geographic_rate_adjustment import GeographicRateAdjustment


class NullGeographicRateProvider:
    """The default provider, used whenever GIS is disabled."""

    def adjustment_for(self, *, address: Address) -> GeographicRateAdjustment:
        """Ignore the address and return a neutral adjustment."""

        return GeographicRateAdjustment.zero()
