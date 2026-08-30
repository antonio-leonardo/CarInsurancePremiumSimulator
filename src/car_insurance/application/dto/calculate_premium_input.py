"""Input DTO for the *calculate premium* use case (framework-free primitives)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CarInput:
    """The vehicle facts as supplied by the caller."""

    make: str
    model: str
    value: Decimal
    year: int


@dataclass(frozen=True, slots=True)
class RegistrationLocationInput:
    """The optional registration location as supplied by the caller."""

    country: str
    city: str | None = None
    line1: str | None = None
    postal_code: str | None = None
    region: str | None = None


@dataclass(frozen=True, slots=True)
class CalculatePremiumInput:
    """Everything the use case needs to produce a quote."""

    broker_fee: Decimal
    car: CarInput
    deductible_percentage: Decimal
    registration_location: RegistrationLocationInput | None = None
