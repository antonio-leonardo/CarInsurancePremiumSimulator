"""``RatingRules`` value object — every numeric parameter the calculation needs."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from car_insurance.domain.errors import RatingRulesError

VALID_ROUNDING_MODES = frozenset(
    {
        "ROUND_CEILING",
        "ROUND_DOWN",
        "ROUND_FLOOR",
        "ROUND_HALF_DOWN",
        "ROUND_HALF_EVEN",
        "ROUND_HALF_UP",
        "ROUND_UP",
    }
)


@dataclass(frozen=True, slots=True)
class RatingRules:
    """The full, self-consistent set of rating parameters loaded from config."""

    age_rate_increment: Decimal
    base_rate: Decimal
    coverage_percentage: Decimal
    currency_code: str
    gis_max_adjustment: Decimal
    gis_min_adjustment: Decimal
    max_deductible_percentage: Decimal
    maximum_applied_rate: Decimal | None
    min_vehicle_year: int
    minimum_applied_rate: Decimal
    money_decimal_places: int
    money_rounding_mode: str
    rate_decimal_places: int
    rate_rounding_mode: str
    rules_version: str
    value_band_amount: Decimal
    value_rate_increment: Decimal

    def __post_init__(self) -> None:
        decimals = {
            "age_rate_increment": self.age_rate_increment,
            "base_rate": self.base_rate,
            "coverage_percentage": self.coverage_percentage,
            "gis_max_adjustment": self.gis_max_adjustment,
            "gis_min_adjustment": self.gis_min_adjustment,
            "max_deductible_percentage": self.max_deductible_percentage,
            "minimum_applied_rate": self.minimum_applied_rate,
            "value_band_amount": self.value_band_amount,
            "value_rate_increment": self.value_rate_increment,
        }
        for name, number in decimals.items():
            if not isinstance(number, Decimal) or not number.is_finite():
                raise RatingRulesError(f"{name} must be a finite Decimal")
        if self.maximum_applied_rate is not None and (
            not isinstance(self.maximum_applied_rate, Decimal)
            or not self.maximum_applied_rate.is_finite()
        ):
            raise RatingRulesError("maximum_applied_rate must be a finite Decimal or None")
        if self.age_rate_increment < 0:
            raise RatingRulesError("age_rate_increment must be greater than or equal to zero")
        if self.value_rate_increment < 0:
            raise RatingRulesError("value_rate_increment must be greater than or equal to zero")
        if self.value_band_amount <= 0:
            raise RatingRulesError("value_band_amount must be greater than zero")
        if self.gis_min_adjustment > self.gis_max_adjustment:
            raise RatingRulesError("gis_min_adjustment must not exceed gis_max_adjustment")
        if self.coverage_percentage <= 0:
            raise RatingRulesError("coverage_percentage must be greater than zero")
        # PRODUCT-DECISION: a deductible of at most 100% (ADR 0003 amendment / spec item 14.1).
        # A configured maximum above 1 would let the premium and the policy limit
        # go negative, which is economically meaningless — reject it.
        if not (0 <= self.max_deductible_percentage <= 1):
            raise RatingRulesError("max_deductible_percentage must be between 0 and 1")
        if self.minimum_applied_rate < 0:
            raise RatingRulesError("minimum_applied_rate must be greater than or equal to zero")
        if self.money_decimal_places < 0:
            raise RatingRulesError("money_decimal_places must be greater than or equal to zero")
        if self.rate_decimal_places < 0:
            raise RatingRulesError("rate_decimal_places must be greater than or equal to zero")
        if (
            self.maximum_applied_rate is not None
            and self.maximum_applied_rate < self.minimum_applied_rate
        ):
            raise RatingRulesError("maximum_applied_rate must not be below minimum_applied_rate")
        if self.money_rounding_mode not in VALID_ROUNDING_MODES:
            raise RatingRulesError(f"invalid money_rounding_mode: {self.money_rounding_mode}")
        if self.rate_rounding_mode not in VALID_ROUNDING_MODES:
            raise RatingRulesError(f"invalid rate_rounding_mode: {self.rate_rounding_mode}")
        code = self.currency_code.upper() if isinstance(self.currency_code, str) else ""
        if len(code) != 3 or not code.isalpha():
            raise RatingRulesError("currency_code must be a 3-letter ISO-4217 alphabetic code")
        object.__setattr__(self, "currency_code", code)
        if not self.rules_version:
            raise RatingRulesError("rules_version must not be empty")
        rate_exponent = Decimal(1).scaleb(-self.rate_decimal_places)
        if self.minimum_applied_rate != self.minimum_applied_rate.quantize(rate_exponent):
            raise RatingRulesError(
                "minimum_applied_rate is not representable in rate_decimal_places"
            )
        # PRODUCT-DECISION: no rate ceiling by default (ADR 0002 / spec item 14.2).
        # If one IS configured it must be representable at rate_decimal_places, or
        # the post-quantisation applied_rate could exceed it by up to half a ULP.
        if (
            self.maximum_applied_rate is not None
            and self.maximum_applied_rate != self.maximum_applied_rate.quantize(rate_exponent)
        ):
            raise RatingRulesError(
                "maximum_applied_rate is not representable in rate_decimal_places"
            )

    @staticmethod
    def _quantize(*, mode: str, places: int, value: Decimal) -> Decimal:
        return value.quantize(Decimal(1).scaleb(-places), rounding=mode)

    def quantize_money(self, *, amount: Decimal) -> Decimal:
        """Round a monetary amount to the configured money scale."""

        return self._quantize(
            mode=self.money_rounding_mode,
            places=self.money_decimal_places,
            value=amount,
        )

    def quantize_rate(self, *, rate: Decimal) -> Decimal:
        """Round a rate to the configured rate scale."""

        return self._quantize(
            mode=self.rate_rounding_mode,
            places=self.rate_decimal_places,
            value=rate,
        )
