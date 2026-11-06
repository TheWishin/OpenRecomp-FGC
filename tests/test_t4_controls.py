"""Tekken 4's Pad bindings page, editable: a fake XInput pad and keyboard, a temporary controls.ini, no game, no device.
The file is the one the T4 runtime reads (t4_controls_ini.py; PS2Recomp patch 99-ps2xRuntime-pad-bindings)."""
import os
import tempfile
import unittest

from openrecomp import t4_controls_ini as ini
from openrecomp.adapters.base import Adapter
from openrecomp.adapters.t4_controls import T4Controls
from openrecomp.nav import Game, Nav
from test_nav import Fake, manifest


class FakeReader:
    """Connected XInput slots and what is held, scripted by the test."""

    def __init__(self, slots=(0,)):
        self.connected = set(slots)
        self.pads = {}
        self.keys = set()

    def step(self):
        return set(self.connected)

    def slots(self):
        return set(self.connected)

    def pad_held(self, slot):
        return set(self.pads.get(slot, ())) if slot in self.connected else set()

    def keys_held(self):
        return set(self.keys)


class T4Editable(T4Controls, Fake):
    def __init__(self, folder, slots=(0,)):
        Fake.__init__(self, manifest())
        self.folder = folder
        self.reader = FakeReader(slots)
        self.now = 100.0

    def _t4c_path(self):
        return os.path.join(self.folder, "save", "controls.ini")

    def _t4c_reader(self):
        return self.reader

    def _t4c_clock(self):
        return self.now

    # tests
    def row(self, pad_id):
        return next(r for r in self.controls() if r["id"] == pad_id)

    def slot(self, pad_id, slot_id):
        return next(s for s in self.row(pad_id)["slots"] if s["id"] == slot_id)

    def file(self):
        try:
            with open(self._t4c_path(), encoding="utf-8") as stream:
                return stream.read()
        except OSError:
            return None

    def capture(self, pad_id, slot_id, press, hold_first=()):
        """Begins a capture, presses `press` (a set of sources on the device) and returns the state."""
        device = self.reader.keys if pad_id == "t4:keyboard" else self.reader.pads.setdefault(0, set())
        device.clear()
        device.update(hold_first)
        self.begin_binding(pad_id, slot_id)
        self.now += 0.1
        device.clear()
        device.update(press)
        self.now += 0.1
        return self.poll_binding()


class Rows(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.adapter = T4Editable(self.tmp.name)

    def test_keyboard_and_the_connected_pad_are_rows_with_the_fixed_layouts_as_defaults(self):
        rows = self.adapter.controls()
        self.assertEqual([r["id"] for r in rows], ["t4:keyboard", "t4:xinput:0"])
        keyboard = {s["id"]: s["sources"] for s in rows[0]["slots"]}
        pad = {s["id"]: s["sources"] for s in rows[1]["slots"]}
        # patch 31 asyncPadMask: Square = Left / Z / Num0, Triangle = Up / V / Num1, Cross = Down / X / Space, Circle = Right / C / Esc
        self.assertEqual(keyboard["1"], ["LEFT", "Z", "NUM0"])
        self.assertEqual(keyboard["2"], ["UP", "V", "NUM1"])
        self.assertEqual(keyboard["3"], ["DOWN", "X", "SPACE"])
        self.assertEqual(keyboard["4"], ["RIGHT", "C", "ESC"])
        self.assertEqual(keyboard["UP"], ["W"])
        self.assertEqual((keyboard["START"], keyboard["SELECT"], keyboard["L2"], keyboard["R2"]),
                         (["ENTER"], ["TAB"], ["LSHIFT"], ["RSHIFT"]))
        # patch 60: a controller by position
        self.assertEqual((pad["1"], pad["2"], pad["3"], pad["4"]), (["X"], ["Y"], ["A"], ["B"]))
        self.assertEqual(pad["UP"], ["DUP", "LUP"])
        self.assertEqual((pad["L3"], pad["R3"]), (["LS"], ["RS"]))
        for row in rows:
            self.assertFalse(row.get("fixed"))
            self.assertFalse(row["disabled"])
            self.assertEqual(len(row["slots"]), 16)
            self.assertTrue(all(s["glyphs"] for s in row["slots"] if s["sources"]))
            self.assertEqual(row["preset"], "default")
        self.assertEqual((rows[0]["port"], rows[1]["port"]), (0, 0))
        self.assertTrue(rows[0]["features"]["clear"] and rows[1]["features"]["player"])
        self.assertEqual([p for p, _ in rows[0]["presets"]], ["default", "t4_arcade", "numpad"])
        self.assertEqual([p for p, _ in rows[1]["presets"]], ["default", "t4_arcade"])
        self.assertIsNone(self.adapter.file())            # looking at the page writes nothing

    def test_two_pads_and_none(self):
        adapter = T4Editable(self.tmp.name, slots=(0, 2))
        rows = adapter.controls()
        self.assertEqual([(r["id"], r["port"]) for r in rows], [("t4:keyboard", 0), ("t4:xinput:0", 0), ("t4:xinput:2", 1)])
        adapter = T4Editable(self.tmp.name, slots=())
        rows = adapter.controls()
        self.assertEqual([r["id"] for r in rows], ["t4:keyboard", "t4:pad"])
        self.assertTrue(rows[1]["disabled"] and rows[1]["features"] == {})
        with self.assertRaises(RuntimeError):
            adapter.begin_binding("t4:pad", "1")

    def test_the_real_t4_adapter_has_the_page(self):
        from openrecomp.adapters.t4 import T4
        self.assertTrue(issubclass(T4, T4Controls))
        self.assertIs(T4.controls_supported, T4Controls.controls_supported)
        self.assertIs(T4.begin_binding, T4Controls.begin_binding)
        self.assertIsNot(T4.controls, Adapter.controls)


class Capture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.adapter = T4Editable(self.tmp.name)

    def bound(self):
        return ini.Controls.load(self.adapter._t4c_path())

    def test_a_key_is_captured_saved_and_read_back_by_the_runtimes_format(self):
        state = self.adapter.capture("t4:keyboard", "1", {"U"})
        self.assertEqual((state["state"], state["source"]), ("ready", "U"))
        self.adapter.accept_binding()
        self.assertEqual(self.adapter.poll_binding()["state"], "done")
        self.assertIn("[player1.keys]\n1 = U\n", self.adapter.file())
        self.assertEqual(self.bound().sources(0, "keys", "1"), ["U"])
        self.assertEqual(self.adapter.slot("t4:keyboard", "1")["sources"], ["U"])
        self.assertEqual(self.adapter.row("t4:keyboard")["preset"], "custom")
        self.assertEqual(self.adapter.slot("t4:xinput:0", "1")["sources"], ["X"])    # the pad is untouched
        self.assertEqual(self.adapter.slot("t4:keyboard", "2")["sources"], ["UP", "V", "NUM1"])

    def test_a_free_pad_source_is_ready_at_once(self):
        for slot, source in (("4", "RUP"), ("L3", "RLEFT")):
            state = self.adapter.capture("t4:xinput:0", slot, {source})
            self.assertEqual((state["state"], state["source"]), ("ready", source), slot)

    def test_pad_conflict_names_the_owner_and_offers_a_swap(self):
        state = self.adapter.capture("t4:xinput:0", "3", {"RB"})                        # RB is R1's
        self.assertEqual(state["state"], "conflict")
        self.assertEqual(state["conflicts"], [self.adapter._t4c_label("R1")])
        self.assertEqual(state["swap"]["sources"], ["A"])                                 # R1 would get Cross's A
        self.adapter.accept_binding(swap=True)
        c = self.bound()
        self.assertEqual(c.sources(0, "pad", "3"), ["RB"])
        self.assertEqual(c.sources(0, "pad", "R1"), ["A"])

    def test_without_swap_the_button_just_moves(self):
        self.adapter.capture("t4:xinput:0", "3", {"RB"})
        self.adapter.accept_binding(swap=False)
        c = self.bound()
        self.assertEqual(c.sources(0, "pad", "3"), ["RB"])
        self.assertEqual(c.sources(0, "pad", "R1"), [])

    def test_the_default_stick_direction_conflicts_with_up(self):
        state = self.adapter.capture("t4:xinput:0", "1", {"LUP"})
        self.assertEqual(state["state"], "conflict")
        self.assertEqual(state["conflicts"], [self.adapter._t4c_label("UP")])
        self.adapter.accept_binding(swap=False)
        self.assertEqual(self.bound().sources(0, "pad", "UP"), ["DUP"])

    def test_a_button_held_when_the_capture_begins_counts_after_it_is_let_go(self):
        self.adapter.reader.keys.update({"ENTER"})                                       # the confirm that opened the capture
        self.adapter.begin_binding("t4:keyboard", "1")
        self.adapter.now += 0.1
        self.assertEqual(self.adapter.poll_binding()["state"], "waiting")                # still held
        self.adapter.reader.keys.clear()
        self.adapter.now += 0.1
        self.assertEqual(self.adapter.poll_binding()["state"], "waiting")                # let go
        self.adapter.reader.keys.update({"ENTER"})
        self.adapter.now += 0.1
        self.assertEqual(self.adapter.poll_binding()["state"], "conflict")               # now it is a press (ENTER = Start)

    def test_two_at_once_timeout_game_key_and_escape(self):
        self.assertEqual(self.adapter.capture("t4:keyboard", "1", {"U", "I"})["state"], "multi")
        self.adapter.now += 0.1
        self.adapter.reader.keys.clear()
        self.adapter.reader.keys.add("J")
        self.assertEqual(self.adapter.poll_binding()["state"], "ready")                  # it goes on with a single key
        self.adapter.cancel_binding()
        self.adapter.begin_binding("t4:keyboard", "1")
        self.adapter.now += 6.0
        self.assertEqual(self.adapter.poll_binding()["state"], "timeout")
        self.assertEqual(self.adapter.capture("t4:keyboard", "1", {"F11"})["state"], "game_key")
        self.assertEqual(self.adapter.capture("t4:keyboard", "1", {"ESC"})["state"], "cancelled")
        self.assertIsNone(self.adapter.file())

    def test_b_on_the_pad_is_back_a_tap_binds_it_one_second_cancels(self):
        state = self.adapter.capture("t4:xinput:0", "L1", {"B"})
        self.assertEqual((state["state"], state.get("holding")), ("waiting", True))
        self.adapter.reader.pads[0] = set()
        self.adapter.now += 0.2
        state = self.adapter.poll_binding()
        self.assertEqual((state["state"], state["source"]), ("conflict", "B"))           # B is Circle's
        self.adapter.cancel_binding()
        self.adapter.capture("t4:xinput:0", "L1", {"B"})
        self.adapter.now += 1.2
        self.assertEqual(self.adapter.poll_binding()["state"], "cancelled")

    def test_the_game_must_be_closed(self):
        self.adapter.is_running = True
        for call in (lambda: self.adapter.begin_binding("t4:keyboard", "1"),
                     lambda: self.adapter.clear_binding("t4:keyboard", "1"),
                     lambda: self.adapter.reset_controls("t4:keyboard"),
                     lambda: self.adapter.apply_preset("t4:keyboard", "t4_arcade"),
                     lambda: self.adapter.set_control_player("t4:keyboard", 1)):
            with self.assertRaises(RuntimeError) as caught:
                call()
            self.assertEqual(caught.exception.args[0], "@controls.running")
        self.assertIsNone(self.adapter.file())

    def test_a_pad_that_goes_away_ends_the_capture(self):
        self.adapter.begin_binding("t4:xinput:0", "1")
        self.adapter.reader.connected.clear()
        self.assertEqual(self.adapter.poll_binding()["state"], "disconnected")

    def test_input_test_lights_the_bound_actions(self):
        self.adapter.begin_input_test("t4:keyboard")
        self.assertEqual(self.adapter.poll_binding()["state"], "test")
        self.adapter.reader.keys.update({"A", "W", "LEFT"})                              # left, up, and 1 (Square)
        live = self.adapter.controls_input("t4:keyboard")
        self.assertEqual(set(live["lit"]), {"LEFT", "UP", "1"})
        self.assertEqual(live["notation"], "u/b+1")
        self.assertEqual(self.adapter.controls_input("t4:xinput:0"), dict(lit=[], notation=""))
        self.adapter.cancel_binding()
        self.assertEqual(self.adapter.controls_input("t4:keyboard"), dict(lit=[], notation=""))

    def test_pad_input_test_ends_when_b_is_held(self):
        self.adapter.begin_input_test("t4:xinput:0")
        self.adapter.reader.pads[0] = {"B"}
        self.assertEqual(self.adapter.poll_binding()["state"], "test")
        self.adapter.now += 1.1
        self.assertEqual(self.adapter.poll_binding()["state"], "cancelled")


class WholeDevice(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.adapter = T4Editable(self.tmp.name, slots=(0, 1))

    def bound(self):
        return ini.Controls.load(self.adapter._t4c_path())

    def test_clear_reset_and_presets_write_the_runtimes_lines(self):
        self.adapter.clear_binding("t4:keyboard", "SELECT")
        self.assertIn("SELECT = NONE", self.adapter.file())
        self.assertEqual(self.adapter.slot("t4:keyboard", "SELECT")["value"], "@controls.unbound")
        self.adapter.apply_preset("t4:xinput:0", "t4_arcade")
        self.assertEqual(self.adapter.row("t4:xinput:0")["preset"], "t4_arcade")
        self.assertEqual(self.bound().sources(0, "pad", "4"), ["RT"])
        self.adapter.apply_preset("t4:keyboard", "numpad")
        self.assertEqual(self.bound().sources(0, "keys", "1"), ["NUM4"])
        self.adapter.reset_controls("t4:xinput:0")
        self.adapter.reset_controls("t4:keyboard")
        self.assertTrue(self.bound().is_default())
        self.assertIn("device = auto", self.adapter.file())
        with self.assertRaises(ValueError):
            self.adapter.apply_preset("t4:xinput:0", "numpad")

    def test_pad_bindings_belong_to_the_player_the_pad_plays_as(self):
        rows = {r["id"]: r for r in self.adapter.controls()}
        self.assertEqual((rows["t4:xinput:0"]["port"], rows["t4:xinput:1"]["port"]), (0, 1))
        self.adapter.clear_binding("t4:xinput:1", "1")
        c = self.bound()
        self.assertEqual(c.sources(1, "pad", "1"), [])
        self.assertEqual(c.sources(0, "pad", "1"), ["X"])
        # slot 1 becomes player 1: its row now shows player 1's bindings and the other pad is player 2's
        self.adapter.set_control_player("t4:xinput:1", 0)
        rows = {r["id"]: r for r in self.adapter.controls()}
        self.assertEqual((rows["t4:xinput:0"]["port"], rows["t4:xinput:1"]["port"]), (1, 0))
        self.assertEqual(rows["t4:xinput:1"]["player"], 0)
        self.assertIsNone(rows["t4:xinput:0"]["player"])
        self.assertIn("device = keyboard+xinput:1", self.adapter.file())
        self.adapter.set_control_player("t4:xinput:1", None)
        self.assertTrue(self.bound().players[0].default_device())

    def test_the_keyboard_can_play_as_player_two(self):
        self.adapter.set_control_player("t4:keyboard", 1)
        rows = {r["id"]: r for r in self.adapter.controls()}
        self.assertEqual((rows["t4:keyboard"]["port"], rows["t4:keyboard"]["player"]), (1, 1))
        self.assertEqual(self.adapter.slot("t4:keyboard", "1")["sources"], [])           # player 2 has no keys of its own yet
        self.adapter.apply_preset("t4:keyboard", "numpad")
        c = self.bound()
        self.assertEqual(c.sources(1, "keys", "1"), ["NUM4"])
        self.assertEqual((c.players[0].keyboard, c.players[1].keyboard), (False, True))
        self.assertIn("device = keyboard+xinput", self.adapter.file())
        self.adapter.set_control_player("t4:keyboard", None)
        self.assertEqual(self.adapter.row("t4:keyboard")["port"], 0)

    def test_a_failed_write_keeps_the_old_bindings(self):
        self.adapter.clear_binding("t4:keyboard", "SELECT")
        before = self.adapter.file()
        original = ini.Controls.save

        def broken(self_, path=None):
            raise OSError("disk full")

        ini.Controls.save = broken
        try:
            with self.assertRaises(OSError):
                self.adapter.clear_binding("t4:keyboard", "START")
        finally:
            ini.Controls.save = original
        self.assertEqual(self.adapter.file(), before)
        self.assertEqual(self.adapter.slot("t4:keyboard", "START")["sources"], ["ENTER"])


class Page(unittest.TestCase):
    def test_the_page_binds_with_the_usual_flow(self):
        with tempfile.TemporaryDirectory() as folder:
            adapter = T4Editable(folder)
            nav = Nav([Game(adapter.m, adapter)], language="en")
            nav.screen = "hub"
            self.assertIn("controls", nav.sections())
            nav.sec[nav.game.id] = "controls"
            items = nav.items()
            self.assertNotIn("ctl:fixed", [it.get("id") for it in items])
            slots = [it for it in items if it.get("ctl") == "slot"]
            self.assertEqual(len(slots), 16)
            self.assertTrue(all(it["run"] is not None and not it["disabled"] for it in slots))
            self.assertIn("ctl:preset", [it.get("id") for it in items])
            self.assertIn("ctl:reset", [it.get("id") for it in items])
            self.assertIn("ctl:player", [it.get("id") for it in items])
            self.assertNotIn("@controls.", repr(nav.view()))
            first = next(i for i, it in enumerate(items) if it.get("ctl") == "slot")
            nav.focus[nav.game.id + ":controls"] = first
            nav.act("confirm", device="kb")
            self.assertTrue(nav.binding_active())


if __name__ == "__main__":
    unittest.main()
