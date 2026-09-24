import unittest
from unittest.mock import patch

from strictlimit import ClockWentBackwards, ImpossibleRequest, SlidingWindowLog


class SlidingWindowLogTests(unittest.TestCase):
    def test_starts_empty(self):
        window = SlidingWindowLog(limit=5, window_seconds=10)
        self.assertEqual(window.remaining(), 5)

    def test_spends_against_limit(self):
        window = SlidingWindowLog(limit=5, window_seconds=10)
        self.assertTrue(window.allow(cost=3))
        self.assertAlmostEqual(window.remaining(), 2)

    def test_denies_when_limit_reached(self):
        window = SlidingWindowLog(limit=2, window_seconds=10)
        self.assertTrue(window.allow(cost=2))
        self.assertFalse(window.allow(cost=1))

    def test_old_entries_expire_out_of_the_window(self):
        with patch("strictlimit.sliding_window.time.monotonic", return_value=100.0):
            window = SlidingWindowLog(limit=5, window_seconds=10)
            window.allow(cost=5)
        with patch("strictlimit.sliding_window.time.monotonic", return_value=109.0):
            self.assertFalse(window.allow(cost=1))
        with patch("strictlimit.sliding_window.time.monotonic", return_value=111.0):
            self.assertTrue(window.allow(cost=1))

    def test_strict_mode_raises_on_clock_rollback(self):
        with patch("strictlimit.sliding_window.time.monotonic", return_value=100.0):
            window = SlidingWindowLog(limit=5, window_seconds=10)
            window.allow()
        with patch("strictlimit.sliding_window.time.monotonic", return_value=90.0):
            with self.assertRaises(ClockWentBackwards):
                window.allow()

    def test_lenient_mode_clamps_clock_rollback(self):
        with patch("strictlimit.sliding_window.time.monotonic", return_value=100.0):
            window = SlidingWindowLog(limit=5, window_seconds=10, lenient=True)
            window.allow(cost=5)
        with patch("strictlimit.sliding_window.time.monotonic", return_value=90.0):
            self.assertFalse(window.allow())

    def test_strict_mode_raises_on_impossible_cost(self):
        window = SlidingWindowLog(limit=5, window_seconds=10)
        with self.assertRaises(ImpossibleRequest):
            window.allow(cost=10)

    def test_lenient_mode_denies_impossible_cost(self):
        window = SlidingWindowLog(limit=5, window_seconds=10, lenient=True)
        self.assertFalse(window.allow(cost=10))

    def test_rejects_bad_construction(self):
        with self.assertRaises(ValueError):
            SlidingWindowLog(limit=0, window_seconds=10)
        with self.assertRaises(ValueError):
            SlidingWindowLog(limit=5, window_seconds=0)


if __name__ == "__main__":
    unittest.main()
