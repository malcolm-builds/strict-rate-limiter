"""Async-friendly wrapper around the synchronous limiters.

TokenBucket and SlidingWindowLog are plain objects guarded by a
threading.Lock; every call does bounded arithmetic and returns, so
calling them directly from a coroutine never blocks an event loop for
long enough to matter. What asyncio callers actually miss is a way to
wait until capacity frees up instead of polling by hand - without it
every caller reimplements the same sleep-and-retry loop, usually with
no protection against spinning forever on a request that can never
succeed.
"""

from __future__ import annotations

import asyncio
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class _Limiter(Protocol):
    def allow(self, cost: float = 1) -> bool: ...
    def remaining(self) -> float: ...


class AsyncLimiter:
    """Wraps a TokenBucket or SlidingWindowLog for use from asyncio code.

    limiter: an existing TokenBucket or SlidingWindowLog instance.
    poll_interval: how often, in seconds, `wait()` re-checks the
        wrapped limiter while it has no capacity to grant.
    """

    def __init__(self, limiter: _Limiter, *, poll_interval: float = 0.05):
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        self._limiter = limiter
        self._poll_interval = poll_interval

    async def allow(self, cost: float = 1) -> bool:
        """Non-blocking check, same semantics as the wrapped limiter's allow()."""
        return self._limiter.allow(cost)

    async def wait(self, cost: float = 1, *, timeout: Optional[float] = None) -> None:
        """Wait until `cost` capacity is available, or raise on timeout.

        Polls the wrapped limiter and sleeps between attempts instead
        of busy-looping, so other coroutines get to run in the
        meantime. Any exception the wrapped limiter raises - such as
        ImpossibleRequest in strict mode - propagates immediately
        rather than being retried, since a request that can never
        succeed should not wait forever for capacity that will never
        appear.
        """
        loop = asyncio.get_running_loop()
        deadline = None if timeout is None else loop.time() + timeout
        while True:
            if self._limiter.allow(cost):
                return
            now = loop.time()
            if deadline is not None and now >= deadline:
                raise TimeoutError(
                    f"timed out after {timeout}s waiting for {cost} units of capacity"
                )
            sleep_for = self._poll_interval
            if deadline is not None:
                sleep_for = min(sleep_for, deadline - now)
            await asyncio.sleep(sleep_for)

    def remaining(self) -> float:
        """Current capacity, delegating to the wrapped limiter."""
        return self._limiter.remaining()

    def __repr__(self) -> str:
        return f"AsyncLimiter({self._limiter!r}, poll_interval={self._poll_interval})"
