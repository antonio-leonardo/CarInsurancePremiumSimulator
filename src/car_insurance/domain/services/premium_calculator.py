"""``PremiumCalculator`` — base premium, deductible discount and final premium."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from car_insurance.domain.calculation_context import high_precision
from car_insurance.domain.value_objects.money import Money
from car_insurance.domain.value_objects.percentage import Percentage
from car_insurance.domain.value_objects.rating_rules import RatingRules
from car_insurance.domain.value_objects.vehicle_snapshot import VehicleSnapshot


@dataclass(frozen=True, slots=True)
class PremiumBreakdown:
    """Intermediate and final premium figures (full precision except the last)."""

    base_premium: Decimal
    calculated_premium: Decimal
    deductible_discount: Decimal


class PremiumCalculator:
    """Pure function object for the premium leg of the calculation."""

    @staticmethod
    def calculate(
        *,
        applied_rate: Percentage,
        broker_fee: Money,
        deductible_percentage: Percentage,
        rules: RatingRules,
        vehicle: VehicleSnapshot,
    ) -> PremiumBreakdown:
        """Compute ``base_premium``, ``deductible_discount`` and ``calculated_premium``."""

        with high_precision():
            base_premium = vehicle.value.amount * applied_rate.value
            deductible_discount = base_premium * deductible_percentage.value
            calculated_premium = rules.quantize_money(
                amount=base_premium - deductible_discount + broker_fee.amount
            )
        return PremiumBreakdown(
            base_premium=base_premium,
            calculated_premium=calculated_premium,
            deductible_discount=deductible_discount,
        )
