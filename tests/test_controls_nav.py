"""Controller-only bindings with fake installed input and no hardware."""
import unittest

from openrecomp.nav import Game, Nav
from openrecomp.pad import Pads
from openrecomp.pad import PlayStationReader
from test_nav import Fake, manifest


class ControlsFake(Fake):
    def __init__(self):
        super().__init__(manifest())
        self.result = dict(state="waiting")

    def controls_supported(self):
        return True

    def controls(self):
        return [dict(id="pad1", label="Fake pad", port=1,
                     slots=[dict(id="cross", label="Cross", value="A"),
                            dict(id="circle", label="Circle", value="B")])]

    def begin_binding(self, pad, slot):
        self.calls.append(("bind", pad, slot))

    def poll_binding(self, active=True):
        self.calls.append(("poll", active))
        return self.result

    def accept_binding(self):
        self.calls.append(("accept",))

    def cancel_binding(self):
        self.calls.append(("cancel",))

    def controls_close(self):
        self.calls.append(("close",))


class ControlsNavigation(unittest.TestCase):
    def setUp(self):
        self.a = ControlsFake()
        self.nav = Nav([Game(self.a.m, self.a)], language="en")
        self.nav.screen = "hub"
        self.nav.sec[self.nav.game.id] = "controls"

    def begin(self):
        self.nav.view()
        self.nav.act("confirm", device="xbox")
        self.assertTrue(self.nav.binding_active())

    def test_optional_section_and_per_pad_slots(self):
        self.assertIn("controls", self.nav.sections())
        view = self.nav.view()
        self.assertEqual([r["label"] for r in view["rows"] if not r["heading"]], ["Cross", "Circle"])
        other = Fake(manifest())
        self.assertNotIn("controls", Nav([Game(other.m, other)]).sections())

    def test_pad_navigation_is_captured_and_plain_view_shows_waiting(self):
        self.begin()
        for action in ("back", "confirm", "next", "social", "play", "switchGame", "down"):
            self.nav.act(action, device="xbox")
        self.assertTrue(self.nav.binding_active())
        self.assertEqual(self.a.calls, [("bind", "pad1", "cross")])
        self.assertEqual(self.nav.view()["overlay"], "bindcapture")
        self.assertEqual(self.nav.view()["bindCapture"]["options"], [])
        self.assertTrue(self.nav.view()["bindCapture"]["waiting"])

    def test_conflict_requires_explicit_yes_and_default_is_cancel(self):
        self.begin()
        self.a.result = dict(state="conflict", source="B", conflicts=["Circle"])
        self.assertTrue(self.nav.poll_tools())
        self.assertIn("Circle", self.nav.view()["dialog"]["text"])
        self.assertNotIn(("accept",), self.a.calls)
        self.nav.act("confirm", device="xbox")
        self.assertIn(("cancel",), self.a.calls)
        self.begin()
        self.nav.poll_tools()
        self.nav.act("right", device="xbox")
        self.nav.act("confirm", device="xbox")
        self.assertIn(("accept",), self.a.calls)
        self.assertIsNone(self.nav.overlay)

    def test_success_and_timeout_return_to_controller_navigation(self):
        self.begin()
        self.a.result = dict(state="ready")
        self.nav.poll_tools()
        self.assertIn(("accept",), self.a.calls)
        self.assertIsNone(self.nav.overlay)
        self.begin()
        self.a.result = dict(state="timeout")
        self.nav.poll_tools()
        self.assertIsNone(self.nav.overlay)
        self.nav.act("down", device="xbox")
        self.assertEqual(self.nav.focus_index(self.nav.items()), 2)

    def test_idle_polling_and_leaving_release_runtime_reader(self):
        self.nav.view()
        self.nav.poll_tools()
        self.assertIn(("poll", True), self.a.calls)
        self.nav.act("next")
        self.nav.poll_tools()
        self.assertEqual(self.a.calls[-1], ("close",))

    def test_replacing_games_releases_old_runtime_reader(self):
        self.nav.view()
        self.nav.set_games([Game(self.a.m, ControlsFake())])
        self.assertEqual(self.a.calls[-1], ("close",))
        self.assertIsNone(self.nav.controls_game)

    def test_losing_foreground_cancels_capture_and_requests_redraw(self):
        self.begin()
        self.assertTrue(self.nav.poll_tools(active=False))
        self.assertIsNone(self.nav.overlay)
        self.assertIsNone(self.nav.controls_game)
        self.assertIsNone(self.nav.binding_game)
        self.assertEqual(self.nav.view()["overlay"], "")

    def test_dry_run_never_opens_capture(self):
        self.nav.dry = True
        self.nav.act("confirm")
        self.assertNotIn(("bind", "pad1", "cross"), self.a.calls)

    def test_navigation_requires_release_after_capture(self):
        class Reader:
            kind = "xbox"
            held = {"B"}

            def read(self):
                return self.held

        reader = Reader()
        pads = Pads([reader])
        pads.suppress()
        self.assertFalse(any(edge == "down" for _action, edge in pads.poll()))
        reader.held = set()
        pads.poll()
        reader.held = {"B"}
        self.assertEqual(pads.poll(), [("back", "down")])

    def test_capture_retains_hid_snapshot_instead_of_reopening_with_empty_warmup(self):
        class Reader:
            kind = "ps"
            held = {"B"}
            warming = False

            def read(self):
                if self.warming:
                    self.warming = False
                    return set()
                return self.held

            def pause(self):
                self.warming = True

        reader = Reader()
        pads = Pads([reader])
        pads.suppress()
        self.assertFalse(reader.warming)
        for _tick in range(3):
            self.assertFalse(any(edge == "down" for _action, edge in pads.poll()))
        reader.held = set()
        pads.poll()
        reader.held = {"B"}
        self.assertEqual(pads.poll(), [("back", "down")])

    def test_background_pause_requests_immediate_scan_on_resume(self):
        class Source:
            def pause(self):
                pass

        reader = PlayStationReader()
        reader.source = Source()
        reader.next_scan = float("inf")
        reader.pause()
        self.assertEqual(reader.next_scan, 0)


if __name__ == "__main__":
    unittest.main()
