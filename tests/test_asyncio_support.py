import unittest

from strictlimit import AsyncLimiter, ImpossibleRequest, TokenBucket


class AsyncLimiterTests(unittest.IsolatedAsyncioTestCase):
    async def test_allow_delegates_to_wrapped_limiter(self):
        bucket = TokenBucket(capacity=2, refill_rate=1)
        wrapped = AsyncLimiter(bucket)
        self.assertTrue(await wrapped.allow(cost=2))
        self.assertFalse(await wrapped.allow(cost=1))

    async def test_wait_returns_once_capacity_refills(self):
        bucket = TokenBucket(capacity=1, refill_rate=100)
        wrapped = AsyncLimiter(bucket, poll_interval=0.005)
        bucket.allow(cost=1)
        await wrapped.wait(cost=1, timeout=1.0)

    async def test_wait_times_out_when_capacity_never_arrives(self):
        bucket = TokenBucket(capacity=1, refill_rate=1)
        wrapped = AsyncLimiter(bucket, poll_interval=0.01)
        bucket.allow(cost=1)
        with self.assertRaises(TimeoutError):
            await wrapped.wait(cost=1, timeout=0.05)

    async def test_wait_propagates_impossible_request_immediately(self):
        bucket = TokenBucket(capacity=5, refill_rate=1)
        wrapped = AsyncLimiter(bucket, poll_interval=5)
        with self.assertRaises(ImpossibleRequest):
            await wrapped.wait(cost=10, timeout=0.01)

    async def test_remaining_delegates_to_wrapped_limiter(self):
        bucket = TokenBucket(capacity=3, refill_rate=1)
        wrapped = AsyncLimiter(bucket)
        self.assertEqual(wrapped.remaining(), 3)

    def test_rejects_bad_poll_interval(self):
        bucket = TokenBucket(capacity=1, refill_rate=1)
        with self.assertRaises(ValueError):
            AsyncLimiter(bucket, poll_interval=0)


if __name__ == "__main__":
    unittest.main()
