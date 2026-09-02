"""``configure_logging`` pipeline behaviour."""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
import structlog

from car_insurance.infrastructure.observability.logging import (
    _add_request_id,
    configure_logging,
)
from car_insurance.infrastructure.observability.request_context import (
    _REQUEST_ID,
    bind_request_id,
)


@pytest.fixture(autouse=True)
def _restore_structlog() -> Iterator[None]:
    yield
    structlog.reset_defaults()
    configure_logging(log_format="json", log_level="INFO", rules_version="test")


def test_add_request_id_is_a_noop_without_a_bound_context() -> None:
    _REQUEST_ID.set(None)
    assert _add_request_id(None, "info", {"event": "x"}) == {"event": "x"}  # type: ignore[arg-type]


def test_add_request_id_injects_the_bound_id() -> None:
    bind_request_id(request_id="abc-123")
    injected = _add_request_id(None, "info", {"event": "x"})  # type: ignore[arg-type]
    assert injected["request_id"] == "abc-123"


def test_httpx_and_httpcore_are_pinned_to_warning() -> None:
    logging.getLogger("httpx").setLevel(logging.DEBUG)
    logging.getLogger("httpcore").setLevel(logging.DEBUG)
    configure_logging(log_format="json", log_level="DEBUG", rules_version="t")
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


def test_console_renderer_branch_is_supported() -> None:
    configure_logging(log_format="console", log_level="INFO", rules_version="t")
    structlog.get_logger("t").info("hello")
