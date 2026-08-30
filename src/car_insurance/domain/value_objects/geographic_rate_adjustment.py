"""``GeographicRateAdjustment`` value object — a signed additive rate delta."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from car_insurance.domain.errors import GeographicRateAdjustmentError


@dataclass(frozen=True, slots=True)
class GeographicRateAdjustment:
    """An additive adjustment in rate points (may be negative).

    This is the *only* geographic concept the domain knows about: no HTTP, no
    API key, no provider.  Bounds are supplied by configuration through
    :meth:`within`.
    """

    value: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal):
            raise GeographicRateAdjustmentError("value must be a Decimal")
        if not self.value.is_finite():
            raise GeographicRateAdjustmentError("value must be finite")

    @classmethod
    def within(
        cls,
        *,
        maximum: Decimal,
        minimum: Decimal,
        value: Decimal | float | int | str,
    ) -> GeographicRateAdjustment:
        """Build an adjustment, rejecting anything outside ``[minimum, maximum]``."""

        coerced = Decimal(str(value))
        if not coerced.is_finite() or coerced < minimum or coerced > maximum:
            raise GeographicRateAdjustmentError(
                f"adjustment {coerced} outside allowed range [{minimum}, {maximum}]"
            )
        return cls(coerced)

    @classmethod
    def zero(cls) -> GeographicRateAdjustment:
        """The neutral adjustment used when GIS is disabled."""

        return cls(Decimal("0"))
