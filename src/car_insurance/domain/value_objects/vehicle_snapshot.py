"""``VehicleSnapshot`` value object — the immutable vehicle facts used in a quote."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from car_insurance.domain.errors import VehicleSnapshotError
from car_insurance.domain.value_objects.money import Money
from car_insurance.domain.value_objects.vehicle_year import VehicleYear

MAX_TEXT_LENGTH = 120


@dataclass(frozen=True, slots=True)
class VehicleSnapshot:
    """A frozen picture of the insured vehicle at simulation time."""

    make: str
    model: str
    value: Money
    year: VehicleYear

    def __post_init__(self) -> None:
        for field_name in ("make", "model"):
            text = getattr(self, field_name)
            if not isinstance(text, str) or not text.strip():
                raise VehicleSnapshotError(f"{field_name} must be a non-empty string")
            if len(text) > MAX_TEXT_LENGTH:
                raise VehicleSnapshotError(
                    f"{field_name} must be at most {MAX_TEXT_LENGTH} characters"
                )
        if not isinstance(self.value, Money):
            raise VehicleSnapshotError("value must be a Money instance")
        if self.value.amount <= 0:
            raise VehicleSnapshotError("value amount must be greater than zero")
        if not isinstance(self.year, VehicleYear):
            raise VehicleSnapshotError("year must be a VehicleYear instance")

    @classmethod
    def create(
        cls,
        *,
        currency: str,
        make: str,
        minimum_year: int,
        model: str,
        value: Decimal | float | int | str,
        year: int,
    ) -> VehicleSnapshot:
        """Build a :class:`VehicleSnapshot` from primitive input values."""

        return cls(
            make=make,
            model=model,
            value=Money.of(amount=value, currency=currency),
            year=VehicleYear.create(minimum=minimum_year, value=year),
        )
