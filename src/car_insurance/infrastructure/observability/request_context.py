"""Request-scoped ``request_id`` propagation via a context variable."""

from __future__ import annotations

import re
from contextvars import ContextVar
from uuid import uuid4

_REQUEST_ID: ContextVar[str | None] = ContextVar("request_id", default=None)
# A conservative token: what a well-behaved tracing client sends. Anything else
# (spaces, control chars, over-long values, header-injection attempts) is
# dropped in favour of a fresh id so it can never reach a log line or a
# response header verbatim.
_SAFE_REQUEST_ID = re.compile(r"\A[A-Za-z0-9._~-]{1,128}\Z")

REQUEST_ID_HEADER = "X-Request-ID"


def bind_request_id(*, request_id: str | None) -> str:
    """Store a safe ``request_id`` for the current context and return it.

    Uses the caller's value only when it matches :data:`_SAFE_REQUEST_ID`;
    otherwise a fresh UUID is generated.
    """

    resolved = request_id if request_id and _SAFE_REQUEST_ID.match(request_id) else str(uuid4())
    _REQUEST_ID.set(resolved)
    return resolved


def current_request_id() -> str | None:
    """Return the ``request_id`` bound to the current context, if any."""

    return _REQUEST_ID.get()
