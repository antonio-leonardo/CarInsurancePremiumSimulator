"""Use-case tests with fakes for every port."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from car_insurance.application.dto.calculate_premium_input import (
    CalculatePremiumInput,
    CarInput,
    RegistrationLocationInput,
)
from car_insurance.application.ports.simulation_repository import (
    SimulationRepositoryError,
)
from car_insurance.application.use_cases.calculate_premium import CalculatePremium
from car_insurance.domain.errors import DomainError
from car_insurance.domain.value_objects.geographic_rate_adjustment import (
    GeographicRateAdjustment,
)
from tests.conftest import (
    FakeEventPublisher,
    FakeGeographicRateProvider,
    FakeLogger,
    FakeRepository,
    FixedClock,
)


def _use_case(
    *,
    clock: FixedClock,
    failure_mode: str = "fail_closed",
    provider: FakeGeographicRateProvider | None = None,
    publisher: FakeEventPublisher | None = None,
    repository: FakeRepository | None = None,
    rules,
) -> CalculatePremium:
    return CalculatePremium(
        clock=clock,
        event_publisher=publisher or FakeEventPublisher(),
        geographic_rate_provider=provider or FakeGeographicRateProvider(),
        logger=FakeLogger(),
        persistence_failure_mode=failure_mode,
        repository=repository or FakeRepository(),
        rules=rules,
    )


def _request(*, value: float = 100000.0, year: int = 2012, location=None) -> CalculatePremiumInput:
    return CalculatePremiumInput(
        broker_fee=Decimal(50),
        car=CarInput(make="Toyota", model="Corolla", value=Decimal(str(value)), year=year),
        deductible_percentage=Decimal("0.10"),
        registration_location=location,
    )


def test_happy_path_matches_example_b(clock_2026, rules) -> None:
    publisher = FakeEventPublisher()
    repository = FakeRepository()
    use_case = _use_case(clock=clock_2026, publisher=publisher, repository=repository, rules=rules)

    result = use_case.execute(request=_request(year=2012))

    assert result.applied_rate == Decimal("0.120000")
    assert result.calculated_premium == Decimal("10850.00")
    assert result.car.year == 2012
    assert len(publisher.published) == 1
    assert repository.saved


def test_future_year_rejected(clock_2026, rules) -> None:
    use_case = _use_case(clock=clock_2026, rules=rules)
    with pytest.raises(DomainError):
        use_case.execute(request=_request(year=2030))


def test_gis_provider_called_only_with_location(clock_2026, rules) -> None:
    provider = FakeGeographicRateProvider(adjustment=GeographicRateAdjustment(Decimal("0.01")))
    use_case = _use_case(clock=clock_2026, provider=provider, rules=rules)

    use_case.execute(request=_request(location=None))
    assert provider.calls == []

    use_case.execute(
        request=_request(location=RegistrationLocationInput(country="US", region="CA"))
    )
    assert len(provider.calls) == 1


def test_gis_adjustment_changes_rate(clock_2026, rules) -> None:
    provider = FakeGeographicRateProvider(adjustment=GeographicRateAdjustment(Decimal("0.01")))
    use_case = _use_case(clock=clock_2026, provider=provider, rules=rules)

    result = use_case.execute(
        request=_request(year=2012, location=RegistrationLocationInput(country="US"))
    )
    assert result.applied_rate == Decimal("0.130000")


def test_persistence_fail_closed_propagates(clock_2026, rules) -> None:
    class BrokenRepository(FakeRepository):
        def save(self, *, simulation) -> None:
            raise SimulationRepositoryError("db down")

    use_case = _use_case(
        clock=clock_2026,
        failure_mode="fail_closed",
        repository=BrokenRepository(),
        rules=rules,
    )
    with pytest.raises(SimulationRepositoryError):
        use_case.execute(request=_request())


def test_persistence_fail_open_swallows(clock_2026, rules) -> None:
    class BrokenRepository(FakeRepository):
        def save(self, *, simulation) -> None:
            raise SimulationRepositoryError("db down")

    use_case = _use_case(
        clock=clock_2026,
        failure_mode="fail_open",
        repository=BrokenRepository(),
        rules=rules,
    )
    result = use_case.execute(request=_request())
    assert result.calculated_premium == Decimal("10850.00")


def test_unparseable_number_becomes_domain_error(clock_2026, rules) -> None:
    use_case = _use_case(clock=clock_2026, rules=rules)
    bad = CalculatePremiumInput(
        broker_fee="not-a-number",  # type: ignore[arg-type]
        car=CarInput(make="Toyota", model="Corolla", value=Decimal(100000), year=2012),
        deductible_percentage=Decimal("0.10"),
    )
    with pytest.raises(DomainError):
        use_case.execute(request=bad)


def test_non_finite_number_becomes_domain_error(clock_2026, rules) -> None:
    use_case = _use_case(clock=clock_2026, rules=rules)
    bad = CalculatePremiumInput(
        broker_fee=Decimal("Infinity"),
        car=CarInput(make="Toyota", model="Corolla", value=Decimal(100000), year=2012),
        deductible_percentage=Decimal("0.10"),
    )
    with pytest.raises(DomainError):
        use_case.execute(request=bad)


def test_clock_year_drives_age(rules) -> None:
    clock = FixedClock(moment=datetime(2030, 1, 1, tzinfo=UTC))
    use_case = _use_case(clock=clock, rules=rules)
    result = use_case.execute(request=_request(year=2020))
    # car_age = 10 -> age_rate 0.05; value_rate 0.05 -> 0.10
    assert result.applied_rate == Decimal("0.100000")
