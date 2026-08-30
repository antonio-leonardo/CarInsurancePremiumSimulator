"""``Address`` value object — the minimal registration location the domain knows."""

from __future__ import annotations

from dataclasses import dataclass

from car_insurance.domain.errors import AddressError

MAX_TEXT_LENGTH = 180


@dataclass(frozen=True, slots=True)
class Address:
    """A registration location.

    Only ``country`` is mandatory (ISO-3166-1 alpha-2).  The domain never stores
    or forwards anything richer than this.

    PRODUCT-DECISION: minimal address VO for the GIS bonus (ADR 0010 / spec item
    14.4).  If a real provider needs more fields, open an ADR before Phase 8.
    """

    country: str
    city: str | None = None
    line1: str | None = None
    postal_code: str | None = None
    region: str | None = None

    def __post_init__(self) -> None:
        country = self.country.upper() if isinstance(self.country, str) else ""
        if len(country) != 2 or not country.isalpha():
            raise AddressError("country must be an ISO-3166-1 alpha-2 code")
        object.__setattr__(self, "country", country)
        for field_name in ("city", "line1", "postal_code", "region"):
            text = getattr(self, field_name)
            if text is None:
                continue
            if not isinstance(text, str) or len(text) > MAX_TEXT_LENGTH:
                raise AddressError(
                    f"{field_name} must be a string of at most {MAX_TEXT_LENGTH} characters"
                )
