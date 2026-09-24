"""Sliding window log rate limiting, same strict-by-default semantics as TokenBucket.

Where TokenBucket approximates a rate with a continuously refilling
pool, SlidingWindowLog keeps the timestamp and cost of every accepted
request and forgets only the ones older than window_seconds. That
makes it exact - no burst at the boundary between two fixed windows -
at the cost of memory proportional to the request rate, which is the
usual tradeoff between the two algorithms.
"""

from __future__ import annotations

import threading
import time
from collections import deque

from .limiter import ClockWentBackwards, ImpossibleRequest


class SlidingWindowLog:
    """A thread-safe sliding window log rate limiter.

    limit: maximum total cost allowed within any trailing window of
        length window_seconds.
    window_seconds: length of the trailing window, in seconds.
    lenient: if False (default), clock rollbacks and impossible
        requests raise. If True, they are handled quietly instead.
    """

    def __init__(self, limit: float, window_seconds: float, *, lenient: bool = False):
        if limit <= 0:
            raise ValueError("limit must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.limit = float(limit)
        self.window_seconds = float(window_seconds)
        self.lenient = lenient
        self._log: deque = deque()
        self._total = 0.0
        self._last_seen = time.monotonic()
        self._lock = threading.Lock()

    def _purge(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._log and self._log[0][0] <= cutoff:
            _, cost = self._log.popleft()
            self._total -= cost

    def allow(self, cost: float = 1) -> bool:
        """Try to record `cost` against the window. Returns True if allowed."""
        if cost <= 0:
            raise ValueError("cost must be positive")
        if cost > self.limit:
            if self.lenient:
                return False
            raise ImpossibleRequest(
                f"cost {cost} exceeds window limit {self.limit}; "
                "this request can never succeed - pass lenient=True to "
                "deny it instead of raising"
            )
        with self._lock:
            now = time.monotonic()
            if now < self._last_seen:
                if self.lenient:
                    now = self._last_seen
                else:
                    raise ClockWentBackwards(
                        f"clock moved backwards by {self._last_seen - now:.6f}s; "
                        "pass lenient=True to clamp instead of raising"
                    )
            self._last_seen = now
            self._purge(now)
            if self._total + cost <= self.limit:
                self._log.append((now, cost))
                self._total += cost
                return True
            return False

    def remaining(self) -> float:
        """Capacity left in the current window, after purging expired entries."""
        with self._lock:
            self._purge(time.monotonic())
            return self.limit - self._total

    def __repr__(self) -> str:
        return (
            f"SlidingWindowLog(limit={self.limit}, window_seconds={self.window_seconds}, "
            f"lenient={self.lenient}, used={self._total:.2f})"
        )
