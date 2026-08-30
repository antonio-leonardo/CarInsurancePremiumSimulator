"""Structured logging configuration (``structlog`` with a JSON renderer)."""

from __future__ import annotations

import logging
from typing import Any

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

from car_insurance.infrastructure.observability.request_context import current_request_id

_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "DEBUG": logging.DEBUG,
    "ERROR": logging.ERROR,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
}


def _add_request_id(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    request_id = current_request_id()
    if request_id is not None:
        event_dict.setdefault("request_id", request_id)
    return event_dict


def _static_binder(*, rules_version: str) -> Processor:
    def processor(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
        event_dict.setdefault("rules_version", rules_version)
        return event_dict

    return processor


def configure_logging(*, log_format: str, log_level: str, rules_version: str) -> None:
    """Install a process-wide ``structlog`` pipeline. Safe to call more than once."""

    level = _LEVELS.get(log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", level=level)
    # httpx/httpcore log the full request URL at INFO — that would leak the GIS
    # location query string. Keep them at WARNING regardless of LOG_LEVEL.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    renderer: Any = (
        structlog.processors.JSONRenderer()
        if log_format == "json"
        else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        # Not cached: the app is not logging-bound, and this keeps the pipeline
        # reconfigurable (tests, a live LOG_LEVEL change).
        cache_logger_on_first_use=False,
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            _add_request_id,
            _static_binder(rules_version=rules_version),
            structlog.processors.TimeStamper(fmt="iso", key="timestamp", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
    )
