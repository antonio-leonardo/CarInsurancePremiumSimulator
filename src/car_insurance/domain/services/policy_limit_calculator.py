"""``PolicyLimitCalculator`` — coverage limit and deductible value."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from car_insurance.domain.calculation_context import high_precision
from car_insurance.domain.value_objects.percentage import Percentage
from car_insurance.domain.value_objects.rating_rules import RatingRules
from car_insurance.domain.value_objects.vehicle_snapshot import VehicleSnapshot


@dataclass(frozen=True, slots=True)
class PolicyLimitBreakdown:
    """Intermediate and final policy-limit figures."""

    base_policy_limit: Decimal
    deductible_value: Decimal
    policy_limit: Decimal


class PolicyLimitCalculator:
    """Pure function object for the coverage leg of the calculation."""

    @staticmethod
    def calculate(
        *,
        deductible_percentage: Percentage,
        rules: RatingRules,
        vehicle: VehicleSnapshot,
    ) -> PolicyLimitBreakdown:
        """Compute ``base_policy_limit``, ``deductible_value`` and ``policy_limit``."""

        with high_precision():
            base_policy_limit = vehicle.value.amount * rules.coverage_percentage
            deductible_amount = base_policy_limit * deductible_percentage.value
            return PolicyLimitBreakdown(
                base_policy_limit=base_policy_limit,
                deductible_value=rules.quantize_money(amount=deductible_amount),
                policy_limit=rules.quantize_money(amount=base_policy_limit - deductible_amount),
            )
