# strictlimit

A token bucket rate limiter for Python. No dependencies, no async
runtime opinions, no config file - just a class you instantiate and
call.

## The problem

Most rate limiter implementations are lenient by default, which is
fine right up until it isn't. Two things go wrong in practice:

- **The clock moves backwards.** NTP corrections, container
  migrations, and mocked clocks in tests all produce a negative time
  delta at some point. A limiter that treats "elapsed < 0" as "elapsed
  = 0" silently under-refills. One that treats it as a large positive
  number over-refills and lets a burst through right when you can
  least afford it.
- **A request costs more than the bucket can ever hold.** This is
  almost always a misconfiguration - a cost passed in the wrong unit,
  or a capacity set an order of magnitude too low. A limiter that just
  returns `False` forever makes this indistinguishable from normal
  rate limiting, so it goes unnoticed until someone asks why a feature
  never works.

`strictlimit` raises on both by default. You find out immediately,
at the call site, instead of debugging a starved queue three weeks
later.

## Usage

```python
from strictlimit import TokenBucket

# 10 tokens capacity, refilling at 2 tokens per second
limiter = TokenBucket(capacity=10, refill_rate=2)

if limiter.allow(cost=1):
    handle_request()
else:
    reject_request()
```

Checking remaining capacity without spending anything:

```python
limiter.remaining()  # -> 7.5
```

### Strict by default

```python
from strictlimit import TokenBucket, ImpossibleRequest

limiter = TokenBucket(capacity=10, refill_rate=2)

# capacity is 10, so this can never succeed - raises instead of
# quietly returning False forever
limiter.allow(cost=50)  # raises ImpossibleRequest
```

If your process clock ever moves backwards, `allow()` raises
`ClockWentBackwards` rather than guessing what you meant.

### The lenient escape hatch

If you'd rather have best-effort behavior - deny instead of raise,
clamp instead of raise - opt in explicitly:

```python
limiter = TokenBucket(capacity=10, refill_rate=2, lenient=True)

limiter.allow(cost=50)  # returns False instead of raising
```

There is no global setting for this. Each `TokenBucket` you construct
is strict unless you say otherwise, so lenience is always a visible,
local decision in the code that reviewers can see.

## Sliding window log

`TokenBucket` approximates a rate with a continuously refilling pool.
`SlidingWindowLog` is the exact alternative: it keeps the timestamp
and cost of every accepted request and forgets only the ones older
than `window_seconds`. That avoids the burst a fixed-window counter
lets through right at the window boundary, at the cost of memory
proportional to the request rate. Same constructor shape, same
strict-by-default behavior:

```python
from strictlimit import SlidingWindowLog

# at most 100 units of cost in any trailing 60-second window
limiter = SlidingWindowLog(limit=100, window_seconds=60)

if limiter.allow(cost=1):
    handle_request()
else:
    reject_request()
```

It raises the same `ClockWentBackwards` and `ImpossibleRequest`
errors as `TokenBucket`, and accepts the same `lenient=True` escape
hatch.

## Using it from asyncio code

`TokenBucket.allow()` and `SlidingWindowLog.allow()` are plain,
non-blocking calls guarded by a `threading.Lock`, so you can call them
directly from a coroutine without wrapping them in an executor. What
you can't do with the raw limiter is wait for capacity to free up
without writing your own poll loop. `AsyncLimiter` wraps either
limiter and adds that:

```python
from strictlimit import AsyncLimiter, TokenBucket

bucket = TokenBucket(capacity=10, refill_rate=2)
limiter = AsyncLimiter(bucket)

if await limiter.allow(cost=1):
    handle_request()

# or block the current coroutine until capacity is available,
# instead of checking and giving up
await limiter.wait(cost=1, timeout=5)
handle_request()
```

`wait()` raises `TimeoutError` if the timeout elapses first, and
propagates `ImpossibleRequest` immediately rather than polling forever
for capacity that can never exist.

## Thread safety

Each `TokenBucket` or `SlidingWindowLog` guards its own state with a
lock, so a single instance can be shared across threads. Neither
coordinates across processes or machines - for that you need a
shared store, which is out of scope for this library.

## Installing

There's no package published yet. Copy `src/strictlimit` into your
project, or add this repo as a path dependency, until a release goes
out.

## License

MIT, see LICENSE.
