"""``VehicleYear`` value object — a model year within an allowed range."""

from __future__ import annotations

from dataclasses import dataclass

from car_insurance.domain.errors import VehicleYearError

MIN_VEHICLE_YEAR = 1900
"""Default lower bound for :meth:`VehicleYear.create` when config supplies none."""


@dataclass(frozen=True, slots=True)
class VehicleYear:
    """A calendar model year.

    ``__post_init__`` enforces only that the year is a positive integer; the
    *configurable* ``>= MIN_VEHICLE_YEAR`` bound is applied by :meth:`create`
    (so it can be relaxed **or** tightened via config), and the "not in the
    future" invariant is enforced by the use case, where the current calendar
    year (from the ``Clock``) is available.
    """

    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise VehicleYearError("year must be an integer")
        if self.value < 1:
            raise VehicleYearError("year must be a positive integer")

    @classmethod
    def create(cls, *, minimum: int = MIN_VEHICLE_YEAR, value: int) -> VehicleYear:
        """Build a :class:`VehicleYear`, rejecting values below ``minimum``."""

        if isinstance(value, bool) or not isinstance(value, int):
            raise VehicleYearError("year must be an integer")
        if value < minimum:
            raise VehicleYearError(f"year must be greater than or equal to {minimum}")
        return cls(value)

    def is_after(self, *, year: int) -> bool:
        """Return ``True`` when this model year is later than ``year``."""

        return self.value > year
