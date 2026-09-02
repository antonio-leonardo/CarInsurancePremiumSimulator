"""``/api/v1/premiums`` routes: calculate, get one, list history."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from car_insurance.application.dto.calculate_premium_input import (
    CalculatePremiumInput,
    CarInput,
    RegistrationLocationInput,
)
from car_insurance.application.use_cases.calculate_premium import CalculatePremium
from car_insurance.application.use_cases.get_simulation import GetSimulation
from car_insurance.application.use_cases.list_simulations import ListSimulations
from car_insurance.domain.value_objects.simulation_id import SimulationId
from car_insurance.presentation.api.dependencies import (
    get_calculate_premium,
    get_get_simulation,
    get_list_simulations,
)
from car_insurance.presentation.api.schemas import (
    CalculatePremiumRequest,
    CalculatePremiumResponse,
    CarResponse,
    InternalErrorResponse,
    MessageResponse,
    PaginationParams,
    SimulationPageResponse,
    SimulationRecordResponse,
    ValidationErrorResponse,
)

router = APIRouter(prefix="/api/v1/premiums", tags=["Premiums"])

_REQUEST_EXAMPLE_A = {
    "broker_fee": 50.0,
    "car": {"make": "Toyota", "model": "Corolla", "value": 100000.0, "year": 2012},
    "deductible_percentage": 0.10,
    "registration_location": {"country": "US", "postal_code": "90001", "region": "CA"},
}
_REQUEST_EXAMPLES: dict[str, dict[str, Any]] = {
    "exampleA": {
        "summary": "Example A — full request with a registration location",
        "value": _REQUEST_EXAMPLE_A,
    },
    "noLocation": {
        "summary": "Minimal request — no location (geographic adjustment is zero)",
        "value": {
            "broker_fee": 50.0,
            "car": {"make": "Toyota", "model": "Corolla", "value": 100000.0, "year": 2012},
            "deductible_percentage": 0.10,
        },
    },
}
_CALCULATE_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "content": {
            "application/json": {
                "examples": {
                    "success": {
                        "summary": "Example A — a successful quote",
                        "value": {
                            "applied_rate": 0.12,
                            "calculated_premium": 10850.00,
                            "car": {
                                "make": "Toyota",
                                "model": "Corolla",
                                "value": 100000.0,
                                "year": 2012,
                            },
                            "deductible_value": 10000.00,
                            "policy_limit": 90000.00,
                        },
                    }
                }
            }
        }
    },
    422: {
        "model": ValidationErrorResponse,
        "description": "Invalid schema or a violated domain input invariant",
        "content": {
            "application/json": {
                "examples": {
                    "schema": {
                        "summary": "A schema violation",
                        "value": {
                            "detail": [
                                {
                                    "loc": ["body", "deductible_percentage"],
                                    "msg": "Input should be less than or equal to 1",
                                    "type": "less_than_equal",
                                }
                            ]
                        },
                    },
                    "domain": {
                        "summary": "A domain invariant violation",
                        "value": {
                            "detail": [
                                {
                                    "loc": [],
                                    "msg": "car.year must not be in the future",
                                    "type": "domain_error",
                                }
                            ]
                        },
                    },
                }
            }
        },
    },
    503: {
        "model": MessageResponse,
        "description": "GIS unavailable (fail-closed) with a location supplied",
        "content": {
            "application/json": {
                "examples": {
                    "unavailable": {
                        "summary": "Geographic risk service down (fail-closed)",
                        "value": {"detail": "geographic risk service unavailable"},
                    }
                }
            }
        },
    },
    500: {
        "model": InternalErrorResponse,
        "description": "Sanitised unexpected error",
        "content": {
            "application/json": {
                "examples": {
                    "internal": {
                        "summary": "A sanitised internal error",
                        "value": {
                            "detail": "internal error",
                            "request_id": "1b9d6bcd-bbfd-4b2d-9b5d-ab8dfbbd4bed",
                        },
                    }
                }
            }
        },
    },
}
_NOT_FOUND_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": MessageResponse, "description": "Not found or persistence disabled"},
}


def _to_record_response(output: object) -> SimulationRecordResponse:
    return SimulationRecordResponse.model_validate(output, from_attributes=True)


@router.post(
    "/calculate",
    operation_id="calculatePremium",
    response_model=CalculatePremiumResponse,
    responses=_CALCULATE_RESPONSES,
    status_code=status.HTTP_200_OK,
    summary="Calculate a car insurance premium",
)
def calculate_premium(
    payload: Annotated[CalculatePremiumRequest, Body(openapi_examples=_REQUEST_EXAMPLES)],
    use_case: Annotated[CalculatePremium, Depends(get_calculate_premium)],
) -> CalculatePremiumResponse:
    """Run the full premium calculation and return exactly the five contract fields."""

    location = payload.registration_location
    result = use_case.execute(
        request=CalculatePremiumInput(
            broker_fee=payload.broker_fee,
            car=CarInput(
                make=payload.car.make,
                model=payload.car.model,
                value=payload.car.value,
                year=payload.car.year,
            ),
            deductible_percentage=payload.deductible_percentage,
            registration_location=(
                RegistrationLocationInput(
                    city=location.city,
                    country=location.country,
                    line1=location.line1,
                    postal_code=location.postal_code,
                    region=location.region,
                )
                if location is not None
                else None
            ),
        )
    )
    return CalculatePremiumResponse(
        applied_rate=result.applied_rate,
        calculated_premium=result.calculated_premium,
        car=CarResponse(
            make=result.car.make,
            model=result.car.model,
            value=result.car.value,
            year=result.car.year,
        ),
        deductible_value=result.deductible_value,
        policy_limit=result.policy_limit,
    )


@router.get(
    "/{simulation_id}",
    operation_id="getSimulation",
    response_model=SimulationRecordResponse,
    responses=_NOT_FOUND_RESPONSES,
    summary="Fetch one persisted simulation",
)
def get_simulation(
    simulation_id: UUID,
    use_case: Annotated[GetSimulation, Depends(get_get_simulation)],
) -> SimulationRecordResponse:
    """Return the stored record, or 404 when it does not exist / persistence is off."""

    result = use_case.execute(simulation_id=SimulationId(simulation_id))
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="simulation not found",
        )
    return _to_record_response(result)


@router.get(
    "",
    operation_id="listSimulations",
    response_model=SimulationPageResponse,
    summary="List simulation history (empty when persistence is disabled)",
)
def list_simulations(
    pagination: Annotated[PaginationParams, Query()],
    use_case: Annotated[ListSimulations, Depends(get_list_simulations)],
) -> SimulationPageResponse:
    """Return a cursor-paginated page of past simulations."""

    page = use_case.execute(cursor=pagination.cursor, limit=pagination.limit)
    return SimulationPageResponse(
        items=[_to_record_response(item) for item in page.items],
        next_cursor=page.next_cursor,
    )
