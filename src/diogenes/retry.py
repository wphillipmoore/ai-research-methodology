"""Exponential-backoff retry for transient API and network failures.

Retriable failures are those where the correct response is 'wait and try
again': model-overload responses (Anthropic 529), rate limiting (429),
5xx gateway errors, and transport-level timeouts or connection errors.
Non-retriable failures — 4xx authentication/authorization/bad-request
errors, JSON validation failures, missing resources — are raised
immediately because retrying them would just burn tokens on the same
broken call.

Callers supply a domain-specific ``is_retriable`` predicate so the core
loop stays agnostic to which library's exceptions it's handling.
"""

from __future__ import annotations

import logging
import random
import time
from typing import TYPE_CHECKING

import anthropic
import requests

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3
_BASE_DELAY_SECONDS = 1.0
_MAX_DELAY_SECONDS = 30.0
_JITTER_FRACTION = 0.1


def retry_with_backoff[T](
    call: Callable[[], T],
    *,
    is_retriable: Callable[[BaseException], bool],
    max_attempts: int = _MAX_ATTEMPTS,
    base_delay: float = _BASE_DELAY_SECONDS,
    max_delay: float = _MAX_DELAY_SECONDS,
) -> T:
    """Execute ``call``, retrying on transient failures.

    Retries are bounded by ``max_attempts`` (total attempts, including the
    first). Delay doubles on each failure — 1s, 2s, 4s, … — capped at
    ``max_delay``, with up to 10% jitter added to avoid thundering-herd
    lockstep with other callers hitting the same overloaded backend.

    The ``is_retriable`` predicate is consulted for every raised
    exception. Non-retriable exceptions propagate immediately on the
    first hit; retriable ones propagate only after ``max_attempts``
    have been exhausted.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return call()
        except BaseException as exc:
            if attempt == max_attempts or not is_retriable(exc):
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            jitter = random.uniform(0, delay * _JITTER_FRACTION)  # noqa: S311
            logger.warning(
                "retry %d/%d after %.2fs: %s",
                attempt,
                max_attempts,
                delay + jitter,
                exc,
            )
            time.sleep(delay + jitter)
    # Unreachable: the loop either returns (success path) or raises
    # (either a non-retriable exception immediately, or the last
    # retriable exception on the final attempt). This line exists
    # only so the type checker can conclude the function always returns
    # or raises, and is excluded from coverage accordingly.
    msg = "retry_with_backoff exhausted without returning or raising"  # pragma: no cover
    raise RuntimeError(msg)  # pragma: no cover


_RETRIABLE_HTTP_STATUS = {429, 502, 503, 504, 529}


def is_retriable_anthropic(exc: BaseException) -> bool:
    """Return True if an anthropic SDK exception is a transient failure."""
    if isinstance(exc, (anthropic.APIConnectionError, anthropic.APITimeoutError)):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        return exc.status_code in _RETRIABLE_HTTP_STATUS
    return False


def is_retriable_http(exc: BaseException) -> bool:
    """Return True if a requests-library exception is a transient failure."""
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code in _RETRIABLE_HTTP_STATUS
    return False
