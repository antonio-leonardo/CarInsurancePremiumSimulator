"""``SystemClock`` — the production :class:`Clock` adapter."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


class SystemClock:
    """Returns the wall-clock time in a fixed business timezone."""

    def __init__(self, *, timezone: ZoneInfo) -> None:
        self._timezone = timezone

    def now(self) -> datetime:
        """Current timezone-aware time in the configured business timezone."""

        return datetime.now(tz=self._timezone)
