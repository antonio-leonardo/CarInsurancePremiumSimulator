"""``RateCalculator`` — the applied-rate pipeline (item 4 of the spec)."""

from __future__ import annotations

from decimal import Decimal

from car_insurance.domain.calculation_context import high_precision
from car_insurance.domain.value_objects.geographic_rate_adjustment import GeographicRateAdjustment
from car_insurance.domain.value_objects.percentage import Percentage
from car_insurance.domain.value_objects.rating_rules import RatingRules
from car_insurance.domain.value_objects.vehicle_snapshot import VehicleSnapshot


class RateCalculator:
    """Pure function object that produces the quantised ``applied_rate``."""

    @staticmethod
    def calculate(
        *,
        calculation_year: int,
        geographic_adjustment: GeographicRateAdjustment,
        rules: RatingRules,
        vehicle: VehicleSnapshot,
    ) -> Percentage:
        """Run age-rate + value-rate + base-rate + GIS, clamp, then quantise."""

        with high_precision():
            car_age = Decimal(calculation_year - vehicle.year.value)
            age_rate = car_age * rules.age_rate_increment
            # Decimal `//` truncates toward zero; both operands are validated > 0
            # (value > 0, band > 0), so this equals floor(value / band).
            value_units = vehicle.value.amount // rules.value_band_amount
            value_rate = value_units * rules.value_rate_increment
            raw_rate = age_rate + value_rate + rules.base_rate + geographic_adjustment.value
            clamped_rate = max(raw_rate, rules.minimum_applied_rate)
            if rules.maximum_applied_rate is not None:
                clamped_rate = min(clamped_rate, rules.maximum_applied_rate)
            return Percentage(rules.quantize_rate(rate=clamped_rate))
