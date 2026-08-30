"""``StructlogLogger`` — binds the application ``Logger`` port to ``structlog``."""

from __future__ import annotations

import structlog


class StructlogLogger:
    """Thin pass-through to a bound ``structlog`` logger."""

    def __init__(self, *, name: str) -> None:
        self._logger = structlog.get_logger(name)

    def error(self, event: str, /, **fields: object) -> None:
        self._logger.error(event, **fields)

    def info(self, event: str, /, **fields: object) -> None:
        self._logger.info(event, **fields)

    def warning(self, event: str, /, **fields: object) -> None:
        self._logger.warning(event, **fields)
