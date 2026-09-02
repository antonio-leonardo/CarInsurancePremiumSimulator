"""Builds the domain :class:`RatingRules` value object from :class:`Settings`."""

from __future__ import annotations

from car_insurance.domain.value_objects.rating_rules import RatingRules
from car_insurance.infrastructure.config.settings import Settings


def build_rating_rules(*, settings: Settings) -> RatingRules:
    """Translate validated settings into an immutable, domain-validated rule set."""

    return RatingRules(
        age_rate_increment=settings.age_rate_increment,
        base_rate=settings.base_rate,
        coverage_percentage=settings.coverage_percentage,
        currency_code=settings.currency_code,
        gis_max_adjustment=settings.gis_max_adjustment,
        gis_min_adjustment=settings.gis_min_adjustment,
        max_deductible_percentage=settings.max_deductible_percentage,
        maximum_applied_rate=settings.maximum_applied_rate,
        min_vehicle_year=settings.min_vehicle_year,
        minimum_applied_rate=settings.minimum_applied_rate,
        money_decimal_places=settings.money_decimal_places,
        money_rounding_mode=settings.money_rounding_mode,
        rate_decimal_places=settings.rate_decimal_places,
        rate_rounding_mode=settings.rate_rounding_mode,
        rules_version=settings.rules_version,
        value_band_amount=settings.value_band_amount,
        value_rate_increment=settings.value_rate_increment,
    )
