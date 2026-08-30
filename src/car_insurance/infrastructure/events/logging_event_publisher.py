"""``LoggingEventPublisher`` — writes each domain event to the structured log."""

from __future__ import annotations

from collections.abc import Sequence

import structlog

from car_insurance.domain.events.premium_simulation_calculated import PremiumSimulationCalculated

_logger = structlog.get_logger(__name__)


class LoggingEventPublisher:
    """The default publisher used when persistence (and the outbox) is disabled."""

    def publish(self, *, events: Sequence[PremiumSimulationCalculated]) -> None:
        """Emit one ``premium.event`` log line per event (no PII beyond country)."""

        for event in events:
            _logger.info(
                "premium.event",
                applied_rate=str(event.applied_rate),
                calculated_premium=str(event.calculated_premium),
                country=event.location_country,
                event_type="PremiumSimulationCalculated",
                occurred_at=event.occurred_at.isoformat(),
                rules_version=event.rules_version,
                simulation_id=str(event.simulation_id),
            )
