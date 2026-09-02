"""Pydantic v2 request/response models for the HTTP API."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

# Inputs are capped here (see CarRequest / CalculatePremiumRequest) so that this
# ``Decimal -> JSON number`` projection is always exact: an integral value is
# emitted as an ``int``, everything else as a ``float`` within its lossless range.
_MAX_INPUT_AMOUNT = Decimal("100000000000")  # 1e11 — absurdly generous for a vehicle / fee


def _as_json_number(value: Decimal) -> float | int:
    return int(value) if value == value.to_integral_value() else float(value)


NumberOut = Annotated[
    Decimal,
    PlainSerializer(_as_json_number, return_type=float, when_used="json"),
]
"""A ``Decimal`` that is emitted as a JSON number (``0.12`` means 12%)."""

_Text = Annotated[str, Field(max_length=180)]


class CarRequest(BaseModel):
    """The vehicle to be insured."""

    model_config = ConfigDict(extra="forbid")

    make: str = Field(
        min_length=1, max_length=120, description="Vehicle manufacturer.", examples=["Toyota"]
    )
    model: str = Field(
        min_length=1, max_length=120, description="Vehicle model name.", examples=["Corolla"]
    )
    value: Decimal = Field(
        gt=0,
        le=_MAX_INPUT_AMOUNT,
        allow_inf_nan=False,
        description="Insured value of the vehicle, in the configured currency (> 0).",
        examples=[100000.0],
    )
    year: int = Field(
        ge=1, le=9999, description="Model year. Must not be in the future.", examples=[2012]
    )


class CarResponse(BaseModel):
    """The echoed vehicle facts — exactly ``make``, ``model``, ``value``, ``year``."""

    model_config = ConfigDict(extra="forbid")

    make: str = Field(description="Vehicle manufacturer, echoed unchanged.", examples=["Toyota"])
    model: str = Field(description="Vehicle model name, echoed unchanged.", examples=["Corolla"])
    value: NumberOut = Field(
        description="Insured value, echoed exactly (integral values emit as JSON integers).",
        examples=[100000.0],
    )
    year: int = Field(description="Model year, echoed unchanged.", examples=[2012])


class RegistrationLocationRequest(BaseModel):
    """Optional registration location.

    Only ``country`` is required when present. When GIS is disabled the location
    is accepted and applied as a **zero** rate adjustment.
    """

    model_config = ConfigDict(extra="forbid")

    country: str = Field(
        min_length=2, max_length=2, description="ISO-3166-1 alpha-2 country code.", examples=["US"]
    )
    city: _Text | None = Field(
        default=None, description="City / locality.", examples=["Los Angeles"]
    )
    line1: _Text | None = Field(
        default=None, description="Street address line.", examples=["1 Main St"]
    )
    postal_code: _Text | None = Field(
        default=None, description="Postal / ZIP code.", examples=["90001"]
    )
    region: _Text | None = Field(
        default=None, description="State / province / region.", examples=["CA"]
    )


class CalculatePremiumRequest(BaseModel):
    """Body of ``POST /api/v1/premiums/calculate``."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "broker_fee": 50.0,
                    "car": {
                        "make": "Toyota",
                        "model": "Corolla",
                        "value": 100000.0,
                        "year": 2012,
                    },
                    "deductible_percentage": 0.10,
                    "registration_location": {
                        "country": "US",
                        "postal_code": "90001",
                        "region": "CA",
                    },
                }
            ]
        },
    )

    broker_fee: Decimal = Field(
        ge=0,
        le=_MAX_INPUT_AMOUNT,
        allow_inf_nan=False,
        description="Flat broker fee added to the premium.",
        examples=[50.0],
    )
    car: CarRequest
    deductible_percentage: Decimal = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
        description="Deductible as a fraction: use 0.10 for 10%. At most 1.0 (100%).",
        examples=[0.10],
    )
    registration_location: RegistrationLocationRequest | None = None


class CalculatePremiumResponse(BaseModel):
    """Body of a successful ``calculate`` response — exactly five top-level fields."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "applied_rate": 0.12,
                    "calculated_premium": 10850.00,
                    "car": {"make": "Toyota", "model": "Corolla", "value": 100000.0, "year": 2012},
                    "deductible_value": 10000.00,
                    "policy_limit": 90000.00,
                }
            ]
        },
    )

    applied_rate: NumberOut = Field(
        description="Final rate as a fraction (0.12 means 12%).", examples=[0.12]
    )
    calculated_premium: NumberOut = Field(
        description="Premium after the deductible discount and fee.", examples=[10850.00]
    )
    car: CarResponse = Field(description="The insured vehicle, echoed unchanged.")
    deductible_value: NumberOut = Field(
        description="Absolute deductible amount.", examples=[10000.00]
    )
    policy_limit: NumberOut = Field(
        description="Coverage limit after the deductible.", examples=[90000.00]
    )


class SimulationRecordResponse(BaseModel):
    """A persisted simulation as returned by the history endpoints (additive schema)."""

    model_config = ConfigDict(extra="forbid")

    applied_rate: NumberOut = Field(description="Final rate as a fraction.", examples=[0.12])
    calculated_premium: NumberOut = Field(description="Stored premium.", examples=[10850.00])
    car: CarResponse = Field(description="The insured vehicle.")
    created_at: datetime = Field(
        description="When the simulation was calculated.",
        examples=["2026-08-30T12:00:00+00:00"],
    )
    deductible_value: NumberOut = Field(description="Absolute deductible.", examples=[10000.00])
    policy_limit: NumberOut = Field(description="Coverage limit.", examples=[90000.00])
    rules_version: str = Field(description="Rating rules version in force.", examples=["2026.08.0"])
    simulation_id: UUID = Field(
        description="Identifier of the persisted simulation.",
        examples=["1b9d6bcd-bbfd-4b2d-9b5d-ab8dfbbd4bed"],
    )


class PaginationParams(BaseModel):
    """Query parameters for the history listing."""

    model_config = ConfigDict(extra="forbid")

    cursor: str | None = Field(default=None, description="Opaque cursor from a previous page.")
    limit: int = Field(default=20, ge=1, le=100, description="Maximum records to return.")


class SimulationPageResponse(BaseModel):
    """A cursor-paginated page of simulation history."""

    model_config = ConfigDict(extra="forbid")

    items: list[SimulationRecordResponse]
    next_cursor: str | None = None


class ErrorItem(BaseModel):
    """One validation error entry — exactly ``loc`` / ``msg`` / ``type``.

    The ``RequestValidationError`` handler normalises Pydantic's raw entries
    (which also carry ``input`` and ``ctx``) down to these three keys, so the
    422 body is identical whether the failure is a schema or a domain invariant
    (ADR 0008).
    """

    model_config = ConfigDict(extra="forbid")

    loc: list[str | int] = Field(default_factory=list, examples=[["body", "deductible_percentage"]])
    msg: str = Field(examples=["Input should be less than or equal to 1"])
    type: str = Field(examples=["less_than_equal"])


class ValidationErrorResponse(BaseModel):
    """Body shape for ``422`` responses (schema errors and domain-invariant errors)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "detail": [
                        {
                            "loc": [],
                            "msg": "car.year must not be in the future",
                            "type": "domain_error",
                        }
                    ]
                }
            ]
        }
    )

    detail: list[ErrorItem]


class MessageResponse(BaseModel):
    """Body shape for ``503`` and simple error responses."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"detail": "geographic risk service unavailable"}]}
    )

    detail: str


class InternalErrorResponse(BaseModel):
    """Body shape for sanitized ``500`` responses."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"detail": "internal error", "request_id": "1b9d6bcd-bbfd-4b2d-9b5d-ab8dfbbd4bed"}
            ]
        }
    )

    detail: str
    request_id: str
