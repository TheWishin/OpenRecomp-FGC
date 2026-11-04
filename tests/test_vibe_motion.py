"""Finite menu motion and countdowns, using fake adapters and no captured art."""
import unittest

from test_ui_loads import spin
import test_ui_versus_art as versus_art


class VibeMotion(unittest.TestCase):
    setUpClass = classmethod(versus_art.VersusArt.setUpClass.__func__)
    setUp = versus_art.VersusArt.setUp
    tearDown = versus_art.VersusArt.tearDown
    named = versus_art.VersusArt.named
    publish = versus_art.VersusArt.publish

    def test_match_entry_and_flash_finish_without_idle_animation(self):
        spin(240)
        card = self.named("matchPresentation")[0]
        self.assertEqual(card.property("entryOffset"), 0)
        self.assertEqual(card.opacity(), 1)
        flash = self.named("versusFlash")
        self.assertTrue(flash)
        self.assertEqual(flash[0].opacity(), 0)

    def test_reduced_motion_snaps_ring_and_entry_to_final_state(self):
        self.backend._v["reducedMotion"] = True
        self.backend._v["matchVersus"]["seconds"] = 10
        self.publish()
        arc = self.named("countdownArc")
        self.assertTrue(arc)
        first = arc[0].property("displayProgress")
        self.backend._v["matchVersus"]["seconds"] = 5
        self.publish()
        self.assertAlmostEqual(arc[0].property("displayProgress"), first / 2)
        presentation = self.named("matchPresentation")[0]
        self.assertEqual(presentation.property("entryOffset"), 0)
        self.assertEqual(presentation.opacity(), 1)
        self.assertEqual(self.named("versusFlash")[0].opacity(), 0)

    def test_countdown_interpolates_only_between_real_deadline_updates(self):
        self.backend._v["reducedMotion"] = False
        self.backend._v["matchVersus"]["seconds"] = 10
        self.publish()
        spin(1100)
        arc = self.named("countdownArc")
        self.assertTrue(arc)
        before = arc[0].property("displayProgress")
        self.backend._v["matchVersus"]["seconds"] = 5
        self.publish()
        during = arc[0].property("displayProgress")
        self.assertLess(during, before)
        self.assertGreater(during, before / 2)
        spin(1100)
        self.assertAlmostEqual(arc[0].property("displayProgress"), before / 2)


if __name__ == "__main__":
    unittest.main()
