"""``Logger`` port — structured, key/value logging without a concrete library.

The application layer records a couple of audit lines per calculation but must
not depend on a logging framework (only on the domain).  Infrastructure binds
this to ``structlog``.
"""

from __future__ import annotations

from typing import Protocol


class Logger(Protocol):
    """A minimal structured logger: an event name plus keyword fields."""

    def bind(self, /, **fields: object) -> Logger:
        """Return a logger that carries ``fields`` on every subsequent line."""

    def error(self, event: str, /, **fields: object) -> None: ...

    def info(self, event: str, /, **fields: object) -> None: ...

    def warning(self, event: str, /, **fields: object) -> None: ...
