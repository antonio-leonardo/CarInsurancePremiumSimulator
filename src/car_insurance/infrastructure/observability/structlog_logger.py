"""``StructlogLogger`` — binds the application ``Logger`` port to ``structlog``."""

from __future__ import annotations

import structlog
from structlog.typing import FilteringBoundLogger


class StructlogLogger:
    """Thin pass-through to a bound ``structlog`` logger."""

    def __init__(self, *, logger: FilteringBoundLogger | None = None, name: str) -> None:
        self._logger = logger if logger is not None else structlog.get_logger(name)
        self._name = name

    def bind(self, /, **fields: object) -> StructlogLogger:
        """Return a logger carrying ``fields`` on every subsequent line."""

        return StructlogLogger(name=self._name, logger=self._logger.bind(**fields))

    def error(self, event: str, /, **fields: object) -> None:
        self._logger.error(event, **fields)

    def info(self, event: str, /, **fields: object) -> None:
        self._logger.info(event, **fields)

    def warning(self, event: str, /, **fields: object) -> None:
        self._logger.warning(event, **fields)
