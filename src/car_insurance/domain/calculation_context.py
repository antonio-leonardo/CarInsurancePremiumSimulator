"""Working precision for the calculation pipeline.

The spec says intermediates are kept at *full* precision and only the explicit
quantisation steps round.  The default ``decimal`` context is 28 significant
digits, which silently rounds (or raises ``InvalidOperation`` on ``quantize``)
once ``vehicle.value`` grows past ~1e24.  Running the arithmetic inside a
wide-precision context removes that ceiling for any realistic monetary
magnitude, so the only rounding that ever happens is the configured
``quantize_money`` / ``quantize_rate``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Context, localcontext

CALCULATION_PRECISION = 80


@contextmanager
def high_precision() -> Iterator[None]:
    """Run a block with enough significant digits that only quantisation rounds."""

    with localcontext(Context(prec=CALCULATION_PRECISION)):
        yield
