"""In-memory sliding-window rate limiter.

Adequate for a single-process MVP. A multi-instance deployment would need a
shared store; that is listed in docs/LIMITATIONS.md rather than added now.
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import Request

from app.config import get_settings
from app.core.errors import TooManyRequests


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: float) -> tuple[bool, int]:
        """Record a hit. Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                return False, max(1, math.ceil(window_seconds - (now - hits[0])))
            hits.append(now)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


def rate_limit(scope: str, limit: Callable[[], int], window_seconds: float = 60.0):
    """FastAPI dependency factory. `limit` is read at request time so settings changes apply."""

    def dependency(request: Request) -> None:
        if not get_settings().rate_limit_enabled:
            return
        client = request.client.host if request.client else "unknown"
        allowed, retry_after = limiter.hit(f"{scope}:{client}", limit(), window_seconds)
        if not allowed:
            raise TooManyRequests(
                "Too many requests. Please wait and try again.",
                details={"retry_after_seconds": retry_after},
                headers={"Retry-After": str(retry_after)},
            )

    return dependency
