import unittest
from unittest.mock import patch

from strictlimit import ClockWentBackwards, ImpossibleRequest, TokenBucket


class TokenBucketTests(unittest.TestCase):
    def test_starts_full(self):
        bucket = TokenBucket(capacity=5, refill_rate=1)
        self.assertEqual(bucket.remaining(), 5)

    def test_spends_tokens(self):
        bucket = TokenBucket(capacity=5, refill_rate=1)
        self.assertTrue(bucket.allow(cost=3))
        self.assertAlmostEqual(bucket.remaining(), 2)

    def test_denies_when_empty(self):
        bucket = TokenBucket(capacity=2, refill_rate=1)
        self.assertTrue(bucket.allow(cost=2))
        self.assertFalse(bucket.allow(cost=1))

    def test_refills_over_time(self):
        with patch("strictlimit.limiter.time.monotonic", return_value=100.0):
            bucket = TokenBucket(capacity=5, refill_rate=2)
            bucket.allow(cost=5)
        with patch("strictlimit.limiter.time.monotonic", return_value=101.0):
            self.assertAlmostEqual(bucket.remaining(), 2)

    def test_strict_mode_raises_on_clock_rollback(self):
        with patch("strictlimit.limiter.time.monotonic", return_value=100.0):
            bucket = TokenBucket(capacity=5, refill_rate=1)
        with patch("strictlimit.limiter.time.monotonic", return_value=90.0):
            with self.assertRaises(ClockWentBackwards):
                bucket.allow()

    def test_lenient_mode_clamps_clock_rollback(self):
        with patch("strictlimit.limiter.time.monotonic", return_value=100.0):
            bucket = TokenBucket(capacity=5, refill_rate=1, lenient=True)
            bucket.allow(cost=5)
        with patch("strictlimit.limiter.time.monotonic", return_value=90.0):
            self.assertFalse(bucket.allow())

    def test_strict_mode_raises_on_impossible_cost(self):
        bucket = TokenBucket(capacity=5, refill_rate=1)
        with self.assertRaises(ImpossibleRequest):
            bucket.allow(cost=10)

    def test_lenient_mode_denies_impossible_cost(self):
        bucket = TokenBucket(capacity=5, refill_rate=1, lenient=True)
        self.assertFalse(bucket.allow(cost=10))

    def test_rejects_bad_construction(self):
        with self.assertRaises(ValueError):
            TokenBucket(capacity=0, refill_rate=1)
        with self.assertRaises(ValueError):
            TokenBucket(capacity=5, refill_rate=0)


if __name__ == "__main__":
    unittest.main()
