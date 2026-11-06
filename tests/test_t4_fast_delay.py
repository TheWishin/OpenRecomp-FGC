"""Lobby matches without a chosen delay: 1 frame up to 100 ms round trip, else the game's auto rule."""
import unittest

from openrecomp.adapters import t4_online


class FastDelayTest(unittest.TestCase):
    def test_rule(self):
        self.assertEqual(t4_online.fast_delay(65.4), "1")
        self.assertEqual(t4_online.fast_delay(100), "1")
        self.assertEqual(t4_online.fast_delay(100.5), "auto")
        self.assertEqual(t4_online.fast_delay(0), "auto")
        self.assertEqual(t4_online.fast_delay(None), "auto")
        self.assertEqual(t4_online.fast_delay("x"), "auto")


if __name__ == "__main__":
    unittest.main()
