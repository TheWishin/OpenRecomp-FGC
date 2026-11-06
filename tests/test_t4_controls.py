"""Tekken 4's Pad bindings page: the runtime's fixed layout, shown read only (player report 2026-11-06: the T4 page did
not say where the bindings are; T4 has no mapping file the game could read yet)."""
import unittest

from openrecomp.adapters.base import Adapter
from openrecomp.adapters.t4_controls import LAYOUT, T4Controls
from openrecomp.nav import Game, Nav
from test_nav import Fake, manifest


class T4Fixed(T4Controls, Fake):
    def __init__(self):
        Fake.__init__(self, manifest())


class FixedLayout(unittest.TestCase):
    def test_keyboard_and_controller_tabs_with_the_runtimes_layout(self):
        rows = T4Fixed().controls()
        self.assertEqual([r["id"] for r in rows], ["t4:keyboard", "t4:pad"])
        keyboard = {s["id"]: s["sources"] for s in rows[0]["slots"]}
        pad = {s["id"]: s["sources"] for s in rows[1]["slots"]}
        # ps2_input_latency.cpp sampleKeyboard: Square = Left arrow / Z, Triangle = Up / V, Cross = Down / X, Circle = Right / C
        self.assertEqual(keyboard["1"], ["LEFT", "Z"])
        self.assertEqual(keyboard["2"], ["UP", "V"])
        self.assertEqual(keyboard["3"], ["DOWN", "X"])
        self.assertEqual(keyboard["4"], ["RIGHT", "C"])
        self.assertEqual(keyboard["UP"], ["W"])
        self.assertEqual((keyboard["START"], keyboard["SELECT"]), (["ENTER"], ["TAB"]))
        # a controller by position: X/Y/A/B = Square/Triangle/Cross/Circle
        self.assertEqual((pad["1"], pad["2"], pad["3"], pad["4"]), (["X"], ["Y"], ["A"], ["B"]))
        for row in rows:
            self.assertTrue(row["fixed"])
            self.assertEqual(row["features"], {})
            self.assertEqual(len(row["slots"]), len(LAYOUT))
            self.assertTrue(all(s["glyphs"] for s in row["slots"]))

    def test_edits_stay_unsupported(self):
        adapter = T4Fixed()
        for call in (lambda: adapter.begin_binding("t4:pad", "1"), lambda: adapter.clear_binding("t4:pad", "1"),
                     lambda: adapter.reset_controls("t4:pad")):
            with self.assertRaises(RuntimeError):
                call()

    def test_the_page_shows_the_layout_and_binds_nothing(self):
        adapter = T4Fixed()
        nav = Nav([Game(adapter.m, adapter)], language="en")
        nav.screen = "hub"
        self.assertIn("controls", nav.sections())
        nav.sec[nav.game.id] = "controls"
        items = nav.items()
        self.assertEqual(items[1]["id"], "ctl:fixed")      # after the Keyboard / Controller switch
        slots = [it for it in items if it.get("ctl") == "slot"]
        self.assertEqual(len(slots), len(LAYOUT))
        self.assertTrue(all(it["run"] is None and not it["clear"] and not it["disabled"] for it in slots))
        self.assertTrue(all(it["hint"] == "@controls.fixed_hint" for it in slots))
        view = nav.view()
        text = repr(view)
        self.assertIn("Fixed buttons", text)
        self.assertIn("Keyboard", text)
        self.assertNotIn("@controls.", text)
        nav.act("confirm", device="xbox")                   # nothing to capture
        self.assertFalse(nav.binding_active())

    def test_the_real_t4_adapter_has_the_page(self):
        from openrecomp.adapters.t4 import T4
        self.assertTrue(issubclass(T4, T4Controls))
        self.assertIs(T4.controls_supported, T4Controls.controls_supported)
        self.assertIsNot(T4.controls, Adapter.controls)


if __name__ == "__main__":
    unittest.main()
