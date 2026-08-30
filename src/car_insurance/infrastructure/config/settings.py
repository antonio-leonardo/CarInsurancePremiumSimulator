"""Application settings — validated once, at process startup."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_FAILURE_MODES = frozenset({"fail_closed", "fail_open"})
_LOG_FORMATS = frozenset({"console", "json"})
_ROUNDING_MODES = frozenset(
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


class Settings(BaseSettings):
    """Every knob the service exposes, sourced from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    age_rate_increment: Decimal = Decimal("0.005")
    base_rate: Decimal = Decimal("0")
    business_timezone: str = "UTC"
    coverage_percentage: Decimal = Decimal("1.00")
    # PRODUCT-DECISION: default currency USD (ADR 0005 / spec item 14.3).
    currency_code: str = "USD"
    database_url: str = "postgresql+psycopg://insurance:insurance@db:5432/insurance"
    db_max_overflow: int = 10
    db_pool_size: int = 5
    gis_api_key: str | None = None
    gis_base_url: str | None = None
    gis_enabled: bool = False
    gis_failure_mode: str = "fail_closed"
    gis_max_adjustment: Decimal = Decimal("0.02")
    gis_min_adjustment: Decimal = Decimal("-0.02")
    gis_timeout_seconds: float = 1.5
    log_format: str = "json"
    log_level: str = "INFO"
    max_deductible_percentage: Decimal = Decimal("1.0")
    maximum_applied_rate: Decimal | None = None
    min_vehicle_year: int = 1900
    minimum_applied_rate: Decimal = Decimal("0")
    money_decimal_places: int = Field(default=2, ge=0)
    money_rounding_mode: str = "ROUND_HALF_UP"
    persistence_enabled: bool = False
    persistence_failure_mode: str = "fail_closed"
    rate_decimal_places: int = Field(default=6, ge=0)
    rate_rounding_mode: str = "ROUND_HALF_UP"
    rules_version: str = "2026.08.0"
    value_band_amount: Decimal = Decimal("10000")
    value_rate_increment: Decimal = Decimal("0.005")

    @field_validator("gis_api_key", "gis_base_url", "maximum_applied_rate", mode="before")
    @classmethod
    def _blank_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @model_validator(mode="after")
    def _check_consistency(self) -> Settings:
        if self.gis_failure_mode not in _FAILURE_MODES:
            raise ValueError(f"GIS_FAILURE_MODE must be one of {sorted(_FAILURE_MODES)}")
        if self.persistence_failure_mode not in _FAILURE_MODES:
            raise ValueError(f"PERSISTENCE_FAILURE_MODE must be one of {sorted(_FAILURE_MODES)}")
        if self.log_format not in _LOG_FORMATS:
            raise ValueError(f"LOG_FORMAT must be one of {sorted(_LOG_FORMATS)}")
        if self.money_rounding_mode not in _ROUNDING_MODES:
            raise ValueError("MONEY_ROUNDING_MODE is not a valid decimal rounding mode")
        if self.rate_rounding_mode not in _ROUNDING_MODES:
            raise ValueError("RATE_ROUNDING_MODE is not a valid decimal rounding mode")
        if self.gis_min_adjustment > self.gis_max_adjustment:
            raise ValueError("GIS_MIN_ADJUSTMENT must not exceed GIS_MAX_ADJUSTMENT")
        if self.gis_enabled and not self.gis_base_url:
            raise ValueError("GIS_BASE_URL is required when GIS_ENABLED is true")
        if self.persistence_enabled and "://" not in self.database_url:
            raise ValueError("DATABASE_URL must be a valid DSN when PERSISTENCE_ENABLED is true")
        if self.db_max_overflow < 0 or self.db_pool_size < 1:
            raise ValueError("DB_POOL_SIZE must be >= 1 and DB_MAX_OVERFLOW must be >= 0")
        if self.gis_timeout_seconds <= 0:
            raise ValueError("GIS_TIMEOUT_SECONDS must be greater than zero")
        try:
            ZoneInfo(self.business_timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"BUSINESS_TIMEZONE is not a valid IANA name: {exc}") from exc
        return self

    @property
    def business_tzinfo(self) -> ZoneInfo:
        """The resolved timezone used for calendar-year calculations."""

        return ZoneInfo(self.business_timezone)
