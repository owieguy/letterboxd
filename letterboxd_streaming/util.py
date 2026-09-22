"""Small shared helpers."""
from __future__ import annotations

import re
import time
from typing import Callable, TypeVar

import requests

T = TypeVar("T")


def slugify(text: str) -> str:
    """'Letterboxd's Top 500 Films' -> 'letterboxds-top-500-films'"""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "list"


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        status = exc.response.status_code if exc.response is not None else None
        return status is None or status == 429 or status >= 500
    return False


def retry_request(fn: Callable[[], T], attempts: int = 4, base_delay: float = 1.5) -> T:
    """Calls `fn` (a zero-arg callable making one HTTP request), retrying
    with exponential backoff on connection drops, timeouts, 429s, and 5xx
    responses -- the kind of transient hiccup that shows up sooner or later
    over hundreds of sequential requests (e.g. a 500-film list). A real
    client error (404, 401, ...) is raised immediately, no retry."""
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return fn()
        except requests.exceptions.RequestException as e:
            if not _is_retryable(e) or attempt == attempts - 1:
                raise
            last_exc = e
            time.sleep(base_delay * (2**attempt))
    raise last_exc  # pragma: no cover -- unreachable, satisfies type checkers
