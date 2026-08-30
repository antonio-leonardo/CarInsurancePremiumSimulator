"""``Percentage`` value object — a finite, non-negative fractional rate."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from car_insurance.domain.errors import PercentageError


@dataclass(frozen=True, slots=True)
class Percentage:
    """A fractional rate where ``Decimal("0.10")`` means 10%.

    Used for deductible, coverage and the applied rate.  Signed adjustments
    (the GIS delta) are modelled by
    :class:`~car_insurance.domain.value_objects.geographic_rate_adjustment.GeographicRateAdjustment`
    instead, so this type stays non-negative.
    """

    value: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal):
            raise PercentageError("value must be a Decimal")
        if not self.value.is_finite():
            raise PercentageError("value must be finite")
        if self.value < 0:
            raise PercentageError("value must be greater than or equal to zero")

    @classmethod
    def of(cls, *, value: Decimal | float | int | str) -> Percentage:
        """Build a :class:`Percentage` coercing ``value`` through ``Decimal(str(...))``."""

        return cls(Decimal(str(value)))
