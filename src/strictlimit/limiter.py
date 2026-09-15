"""Token bucket rate limiting with strict-by-default semantics.

A rate limiter that fails open is worse than useless, because nobody
notices until the thing it was supposed to protect falls over. Two
specific failure modes are easy to hit by accident:

  1. The clock source moves backwards (NTP correction, container
     migration, a mocked clock in a test). A naive bucket treats this
     as "no time passed" and quietly under-refills, or worse, treats
     the negative delta as a huge elapsed time and over-refills.
  2. Someone asks for a cost larger than the bucket's own capacity.
     That request can never succeed. A naive bucket just returns
     False forever, and the caller has no way to tell "rate limited"
     apart from "misconfigured".

By default this module raises on both so the bug surfaces where it
happened instead of downstream. Pass lenient=True to get the quieter,
best-effort behavior instead: clock rollbacks are clamped to zero
elapsed time, and impossible requests are simply denied.
"""

from __future__ import annotations

import threading
import time


class RateLimitError(Exception):
    """Base class for errors raised by this package."""


class ClockWentBackwards(RateLimitError):
    """Raised in strict mode when the clock source moves backwards."""


class ImpossibleRequest(RateLimitError):
    """Raised in strict mode when a request cost exceeds bucket capacity."""


class TokenBucket:
    """A thread-safe token bucket.

    capacity: maximum number of tokens the bucket can hold.
    refill_rate: tokens added per second.
    lenient: if False (default), clock rollbacks and impossible
        requests raise. If True, they are handled quietly instead.
    """

    def __init__(self, capacity: float, refill_rate: float, *, lenient: bool = False):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if refill_rate <= 0:
            raise ValueError("refill_rate must be positive")
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)
        self.lenient = lenient
        self._tokens = self.capacity
        self._last_check = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self, now: float) -> None:
        elapsed = now - self._last_check
        if elapsed < 0:
            if self.lenient:
                elapsed = 0.0
            else:
                raise ClockWentBackwards(
                    f"clock moved backwards by {-elapsed:.6f}s; "
                    "pass lenient=True to clamp instead of raising"
                )
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_rate)
        self._last_check = now

    def allow(self, cost: float = 1) -> bool:
        """Try to spend `cost` tokens. Returns True if allowed."""
        if cost <= 0:
            raise ValueError("cost must be positive")
        if cost > self.capacity:
            if self.lenient:
                return False
            raise ImpossibleRequest(
                f"cost {cost} exceeds bucket capacity {self.capacity}; "
                "this request can never succeed - pass lenient=True to "
                "deny it instead of raising"
            )
        with self._lock:
            self._refill(time.monotonic())
            if self._tokens >= cost:
                self._tokens -= cost
                return True
            return False

    def remaining(self) -> float:
        """Current token count, after applying any pending refill."""
        with self._lock:
            self._refill(time.monotonic())
            return self._tokens

    def __repr__(self) -> str:
        return (
            f"TokenBucket(capacity={self.capacity}, refill_rate={self.refill_rate}, "
            f"lenient={self.lenient}, tokens={self._tokens:.2f})"
        )
