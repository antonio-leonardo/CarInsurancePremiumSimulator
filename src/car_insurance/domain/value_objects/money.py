"""``Money`` value object — a finite ``Decimal`` amount tied to a currency."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from car_insurance.domain.errors import CurrencyMismatchError, MoneyError


@dataclass(frozen=True, slots=True)
class Money:
    """An immutable monetary amount.

    Arithmetic is only defined between two :class:`Money` values that share the
    same currency.  Scale/rounding of external outputs is the responsibility of
    :class:`~car_insurance.domain.value_objects.rating_rules.RatingRules`, not of
    this type.
    """

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise MoneyError("amount must be a Decimal")
        if not self.amount.is_finite():
            raise MoneyError("amount must be finite")
        currency = self.currency.upper() if isinstance(self.currency, str) else ""
        if len(currency) != 3 or not currency.isalpha():
            raise MoneyError("currency must be a 3-letter ISO-4217 alphabetic code")
        object.__setattr__(self, "currency", currency)

    def __add__(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def _assert_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(f"cannot combine {self.currency} with {other.currency}")

    @classmethod
    def of(cls, *, amount: Decimal | float | int | str, currency: str) -> Money:
        """Build a :class:`Money` coercing ``amount`` through ``Decimal(str(...))``."""

        return cls(Decimal(str(amount)), currency)

    def with_amount(self, *, amount: Decimal) -> Money:
        """Return a copy of this value with ``amount`` replaced."""

        return Money(amount, self.currency)
