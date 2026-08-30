"""``Clock`` port — the only source of "now" the application trusts."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """Returns a timezone-aware ``datetime`` in the configured business timezone."""

    def now(self) -> datetime: ...
