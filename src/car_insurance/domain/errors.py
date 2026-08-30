"""Domain-level exceptions.

Every invariant violation in the domain raises a :class:`DomainError` (or a
subclass).  Outer layers translate these into transport-specific responses
(the HTTP layer maps them to ``422``).  The domain itself never imports a
framework to do so.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for every domain invariant violation."""


class AddressError(DomainError):
    """Raised when an :class:`~car_insurance.domain.value_objects.address.Address` is invalid."""


class BrokerFeeError(DomainError):
    """Raised when the broker fee is negative."""


class CurrencyMismatchError(DomainError):
    """Raised when an operation mixes two different currencies."""


class DeductibleOutOfRangeError(DomainError):
    """Raised when the deductible percentage is negative or above the configured maximum."""


class GeographicRateAdjustmentError(DomainError):
    """Raised when a geographic rate adjustment falls outside its allowed range."""


class MoneyError(DomainError):
    """Raised when a monetary amount is not a finite ``Decimal`` or the currency is malformed."""


class PercentageError(DomainError):
    """Raised when a percentage is not a finite, non-negative ``Decimal``."""


class RatingRulesError(DomainError):
    """Raised when the numeric rating parameters are inconsistent."""


class VehicleSnapshotError(DomainError):
    """Raised when a vehicle snapshot breaks a string or value invariant."""


class VehicleYearError(DomainError):
    """Raised when a vehicle model year is out of range or in the future."""
