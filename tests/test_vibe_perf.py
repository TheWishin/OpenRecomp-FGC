"""Statistics used by the optional synthetic render diagnostic."""
import unittest

from tools.vibe_perf import distribution


class VibePerfStatistics(unittest.TestCase):
    def test_spikes_and_empty_samples_are_reported_explicitly(self):
        self.assertEqual(distribution([]), dict(count=0, p50=None, p95=None, maximum=None))
        result = distribution(list(range(1, 20)) + [180])
        self.assertEqual(result, dict(count=20, p50=10, p95=19, maximum=180))
