"""The Pad bindings page: glyphs and notation, the adapter's presets / capture rules, and the page by pad and mouse.

Fake controllers and a fake editor only: no device, no installed game, no file is written."""
import os
import unittest
from collections import namedtuple
from types import SimpleNamespace
from unittest import mock

from openrecomp import i18n, pad_glyphs, pad_presets
from openrecomp.nav import Game, Nav
from pad_fakes import PadsFake
from test_controls_adapter import Capture, Device, Editor, PortMap, Poller, Ref, Subject

Slot = namedtuple("Slot", "key mask group")
Recipe = namedtuple("Recipe", "specs")


class Glyphs(unittest.TestCase):
    def test_device_types(self):
        self.assertEqual(pad_glyphs.device_type("xinput"), "xbox")
        self.assertEqual(pad_glyphs.device_type("dinput", 0x054C, 0x0CE6), "ps")
        self.assertEqual(pad_glyphs.device_type("dinput", 0x0F0D, 0x00EE), "generic")
        self.assertEqual(pad_glyphs.device_type("keys2"), "keyboard")

    def test_each_controller_draws_its_own_buttons(self):
        g = pad_glyphs.glyph
        self.assertEqual(g("xbox", "A"), dict(shape="face", text="A", tone="green", dir=""))
        self.assertEqual(g("xbox", "LT")["shape"], "trigger")
        self.assertEqual(g("xbox", "DUP"), dict(shape="dpad", text="", tone="", dir="up"))
        self.assertEqual(g("xbox", "RLEFT"), dict(shape="stick", text="R", tone="", dir="left"))
        self.assertEqual(g("ps", "B1")["text"], "square")
        self.assertEqual(g("ps", "B2")["text"], "cross")
        self.assertEqual(g("ps", "B3")["text"], "circle")
        self.assertEqual(g("ps", "B4")["text"], "triangle")
        self.assertEqual((g("ps", "B6")["shape"], g("ps", "B6")["text"]), ("bumper", "R1"))
        self.assertEqual((g("ps", "RY+")["shape"], g("ps", "RY+")["text"]), ("trigger", "R2"))
        self.assertEqual(g("ps", "B14")["shape"], "touch")
        self.assertEqual(g("ps", "HAT_LEFT")["dir"], "left")
        self.assertEqual(g("ps", "Y-"), dict(shape="stick", text="L", tone="", dir="up"))
        self.assertEqual(g("generic", "B7"), dict(shape="num", text="7", tone="", dir=""))
        self.assertEqual(g("keyboard", "NUM4")["text"], "Num 4")
        self.assertEqual(g("keyboard", "SEMICOLON")["text"], ";")
        self.assertEqual(g("keyboard", "LSHIFT")["text"], "L Shift")
        self.assertEqual(g("keyboard", "Q"), dict(shape="key", text="Q", tone="", dir=""))

    def test_tekken_notation(self):
        n = pad_glyphs.notation
        self.assertEqual(n(["DOWN", "RIGHT", "SQUARE", "TRIANGLE"]), "d/f+1+2")
        self.assertEqual(n(["LEFT"]), "b")
        self.assertEqual(n(["UP", "LEFT", "CIRCLE"]), "u/b+4")
        self.assertEqual(n(["LEFT", "RIGHT", "CROSS"]), "3")           # opposite directions cancel
        self.assertEqual(n(["START"]), "START")
        self.assertEqual(n([]), "")


class Recipes:
    """The installed editor's preset surface, recorded."""


class FullEditor(Editor):
    def __init__(self):
        super().__init__()
        self.ports = {0: dict(socd="neutral", stick="analog")}
        self.pins = {}

    def bind(self, dev, scope, key, sources):
        if key.isdigit():
            return super().bind(dev, scope, key, sources)
        self.calls.append((dev, scope, key, sources))

    def reset(self, dev, shared=False):
        self.calls.append(("reset", dev))

    def apply_recipe(self, dev, scope, recipe):
        self.calls.append(("recipe", dev, scope, recipe))

    def clear(self, dev, scope, key):
        self.calls.append(("clear", dev, scope, key))

    def socd_of(self, port):
        return self.ports.setdefault(port, dict(socd="neutral", stick="analog"))["socd"]

    def stick_of(self, port):
        return self.ports.setdefault(port, dict(socd="neutral", stick="analog"))["stick"]

    def set_port_option(self, port, key, value):
        self.calls.append(("option", port, key, value))

    def assign_port(self, spec, port):
        self.calls.append(("pin", spec, port))

    def assign_keyboard(self, kind, port):
        self.calls.append(("keyboard", kind, port))

    def pinned(self, port):
        return self.pins.get(port, "auto")

    def detect_recipe(self, dev):
        return "vewlix"


class Adapter(unittest.TestCase):
    def setUp(self):
        Editor.loaded = []
        Editor.fail_save = False
        self.pad = Device("xinput", "pad-one", "Pad One", 0, 0, 0, frozenset())
        self.keys = Device("keys1", "keys1", "Keyboard", 0, 0, None, frozenset())
        self.bus = SimpleNamespace(devices=[self.pad, self.keys], edges=[], paused=0)
        recipes = {name: Recipe({"xinput": 1, "dinput": 1}) for name in ("default", "astro", "vewlix", "hitbox")}
        recipes.update({name: Recipe({"keys1": 1, "keys2": 1}) for name in ("keys_tekken", "keys_numpad")})
        self.ce = SimpleNamespace(ControlsEditor=FullEditor, DeviceRef=Ref, SCOPE_PORT="port", SCOPE_KIND="kind",
                                  SLOTS=[Slot("1", 1, "attack"), Slot("2", 2, "attack")], mask_text=str,
                                  RECIPE_BY_ID=recipes, GAME_KEYS={"ESC": "", "F11": "", "F2": ""},
                                  controls_path=mock.Mock(return_value="custom-controls"))
        FullEditor.loaded = Editor.loaded

        class Ports(PortMap):
            def update(self, devices, controls):
                self.port = {dev.key: 0 for dev in devices}

        self.pm = SimpleNamespace(PortMap=Ports, PS3_BIT={"SQUARE": 1, "TRIANGLE": 2})
        self.adapter = Subject((self.ce, SimpleNamespace(DevicePoller=Poller, Capture=Capture), self.pm,
                                SimpleNamespace(default_sources=lambda: [self.bus])))
        self.adapter.poll_binding()
        self.editor = self.adapter._controls_session["editor"]

    def held(self, key, sources):
        dev = next(d for d in self.bus.devices if d.key == key)
        self.bus.devices = [d._replace(pressed=frozenset(sources)) if d.key == key else d for d in self.bus.devices]
        del dev

    def test_rows_carry_type_glyphs_presets_and_options(self):
        rows = {r["id"]: r for r in self.adapter.controls()}
        pad, keys = rows["pad-one"], rows["keys1"]
        self.assertEqual((pad["type"], keys["type"]), ("xbox", "keyboard"))
        self.assertEqual(pad["slots"][0]["glyphs"], [pad_glyphs.glyph("xbox", "A")])
        self.assertEqual([p for p, _l in pad["presets"]], ["default", "tekken", "arcade", "hitbox", "lefty"])
        self.assertEqual([p for p, _l in keys["presets"]], ["default", "tekken", "numpad"])
        self.assertEqual(pad["preset"], "arcade")
        self.assertEqual(pad["options"], dict(socd="neutral", stick="analog"))
        self.assertNotIn("options", keys)
        self.assertTrue(pad["features"]["test"])

    def test_presets_are_the_installed_editors_own_steps(self):
        ref = Ref("xinput", 0, 0, 0)
        self.adapter.apply_preset("pad-one", "hitbox")
        self.adapter.apply_preset("pad-one", "default")
        self.adapter.apply_preset("pad-one", "lefty")
        self.adapter.apply_preset("keys1", "tekken")
        calls = [c for c in self.editor.calls if c != "saved"]
        self.assertEqual(calls[:3], [("recipe", ref, "port", "hitbox"), ("reset", ref), ("reset", ref)])
        lefty = [c for c in calls[3:] if c[0] != "recipe"]
        self.assertEqual(lefty[0], (ref, "port", "1", ["DLEFT"]))
        self.assertEqual(len(lefty), len(pad_presets.LINES["lefty_xinput"]))
        self.assertEqual(calls[-1], ("recipe", Ref("keys1", 0, 0, 0), "kind", "keys_tekken"))
        with self.assertRaisesRegex(ValueError, "unsupported"):
            self.adapter.apply_preset("keys1", "hitbox")

    def test_clear_reset_options_and_player(self):
        ref = Ref("xinput", 0, 0, 0)
        self.adapter.clear_binding("pad-one", "2")
        self.adapter.reset_controls("pad-one")
        self.adapter.set_control_option("pad-one", "socd", "last")
        self.adapter.set_control_player("pad-one", 1)
        self.adapter.set_control_player("keys1", None)
        self.assertEqual([c for c in self.editor.calls if c != "saved"],
                         [("clear", ref, "port", "2"), ("reset", ref), ("option", 0, "socd", "last"),
                          ("pin", "xinput:0", 1), ("keyboard", "keys1", None)])
        self.assertEqual(self.editor.calls.count("saved"), 5)
        with self.assertRaisesRegex(ValueError, "unsupported"):
            self.adapter.set_control_option("keys1", "socd", "up")

    def test_game_running_blocks_every_edit(self):
        self.adapter.busy = True
        for call in (lambda: self.adapter.apply_preset("pad-one", "default"),
                     lambda: self.adapter.reset_controls("pad-one"),
                     lambda: self.adapter.clear_binding("pad-one", "1")):
            with self.assertRaisesRegex(RuntimeError, "controls.running"):
                call()
        self.assertEqual(self.editor.calls, [])

    def test_failed_preset_save_keeps_the_file(self):
        Editor.fail_save = True
        with self.assertRaisesRegex(RuntimeError, "changed on disk"):
            self.adapter.apply_preset("pad-one", "arcade")
        self.assertIsNot(self.adapter._controls_session["editor"], self.editor)

    def test_tap_back_binds_it_and_holding_back_cancels(self):
        with mock.patch("openrecomp.adapters.t5_controls.time.monotonic", return_value=10.0):
            self.adapter.begin_binding("pad-one", "2")
        session = self.adapter._controls_session
        session["capture"].result = ("ok", "B")
        session["capture"].first = 10.2
        self.held("pad-one", {"B"})
        with mock.patch("openrecomp.adapters.t5_controls.time.monotonic", return_value=10.3):
            self.assertEqual(self.adapter.poll_binding(), dict(state="waiting", left=0.0, holding=True))
        with mock.patch("openrecomp.adapters.t5_controls.time.monotonic", return_value=11.25):
            self.assertEqual(self.adapter.poll_binding(), dict(state="cancelled"))
        self.assertIsNone(session["pending"])
        # a short tap: let go before the second is up -> B is the new button
        with mock.patch("openrecomp.adapters.t5_controls.time.monotonic", return_value=20.0):
            self.held("pad-one", ())
            self.adapter.begin_binding("pad-one", "1")
        session["capture"].result = ("ok", "B")
        self.held("pad-one", {"B"})
        with mock.patch("openrecomp.adapters.t5_controls.time.monotonic", return_value=20.2):
            self.assertTrue(self.adapter.poll_binding()["holding"])
        self.held("pad-one", ())
        with mock.patch("openrecomp.adapters.t5_controls.time.monotonic", return_value=20.4):
            self.assertEqual(self.adapter.poll_binding()["state"], "conflict")
        self.adapter.accept_binding()
        self.assertIn((Ref("xinput", 0, 0, 0), "port", "1", ["B"]), self.editor.calls)

    def test_countdown_and_keyboard_game_keys(self):
        with mock.patch("openrecomp.adapters.t5_controls.time.monotonic", return_value=50.0):
            self.adapter.begin_binding("keys1", "1")
        with mock.patch("openrecomp.adapters.t5_controls.time.monotonic", return_value=52.0):
            self.assertEqual(self.adapter.poll_binding(), dict(state="waiting", left=3.0))
        self.adapter._controls_session["capture"].result = ("ok", "F11")
        with mock.patch("openrecomp.adapters.t5_controls.time.monotonic", return_value=52.5):
            self.assertEqual(self.adapter.poll_binding(), dict(state="game_key", source="F11"))
        self.assertEqual(self.editor.calls, [])

    def test_input_test_lights_actions_and_holding_back_ends_it(self):
        self.held("pad-one", {"A", "X"})
        self.editor.binds[(0, "X")] = 2
        with mock.patch("openrecomp.adapters.t5_controls.time.monotonic", return_value=1.0):
            self.adapter.begin_input_test("pad-one")
            self.assertEqual(self.adapter.poll_binding()["state"], "test")
        self.assertEqual(self.adapter.controls_input("pad-one"), dict(lit=["1", "2"], notation="1+2"))
        self.held("pad-one", {"B"})
        with mock.patch("openrecomp.adapters.t5_controls.time.monotonic", return_value=2.0):
            self.assertEqual(self.adapter.poll_binding(), dict(state="test", back=True))
        with mock.patch("openrecomp.adapters.t5_controls.time.monotonic", return_value=3.05):
            self.assertEqual(self.adapter.poll_binding(), dict(state="cancelled"))
        self.assertEqual(self.editor.calls, [])

    def test_keyboard_is_read_where_the_installed_reader_can(self):
        pn = SimpleNamespace(default_sources=mock.Mock(return_value=[]))
        self.assertEqual(self.adapter._controls_sources(pn), [])
        pn.default_sources.assert_called_once_with()

        def sources(env=None, keyboard=False):
            return ["keyboard"] if keyboard else []
        self.assertEqual(self.adapter._controls_sources(SimpleNamespace(default_sources=sources)), ["keyboard"])


class Page(unittest.TestCase):
    def setUp(self):
        self.a = PadsFake()
        self.nav = Nav([Game(self.a.m, self.a)], language="en")
        self.nav.screen = "hub"
        self.nav.sec[self.nav.game.id] = "controls"

    def items(self):
        return self.nav.items()

    def focus(self, match):
        items = self.items()
        self.nav.focus[self.nav.key()] = next(i for i, it in enumerate(items) if match(it))

    def page(self):
        return self.nav.view()["bindingsPage"]

    def test_tabs_lines_and_glyphs(self):
        page = self.page()
        self.assertEqual(page["layout"], "bindings")
        self.assertEqual([t["label"] for t in page["tabs"]], ["P1 · Xbox pad", "P2 · DualSense", "P1 · Keyboard"])
        self.assertEqual([t["typeLabel"] for t in page["tabs"]], ["Xbox controller", "PlayStation controller", "Keyboard"])
        self.focus(lambda it: it.get("slot") == "1")
        line = next(l for l in self.page()["lines"] if l.get("notation") == "1")
        self.assertEqual((line["label"], line["glyphs"]), ("Left punch", [pad_glyphs.glyph("xbox", "X")]))
        combo = next(it for it in self.items() if it.get("slot") == "1+2")
        self.assertEqual(i18n.localize(combo["label"], "en"), "Left punch + Right punch")
        self.assertEqual(i18n.localize(combo["label"], "de"), "Linker Schlag + Rechter Schlag")

    def test_triggers_switch_controller_and_keep_the_action(self):
        self.focus(lambda it: it.get("slot") == "3")
        self.nav.act("chapterNext", device="xbox")
        self.assertEqual(self.nav.ctl_pad[self.nav.game.id], "dinput:054C:0CE6")
        it = self.items()[self.nav.focus_index(self.items())]
        self.assertEqual((it["slot"], it["glyphs"]), ("3", [pad_glyphs.glyph("ps", "B2")]))
        self.nav.act("chapterPrev", device="xbox")
        self.nav.act("chapterPrev", device="xbox")
        self.assertEqual(self.nav.ctl_pad[self.nav.game.id], "keys1")
        self.nav.click_chapter("xinput:0")
        self.assertEqual(self.nav.ctl_pad[self.nav.game.id], "xinput:0")

    def test_confirm_binds_and_x_clears(self):
        self.focus(lambda it: it.get("slot") == "2")
        self.nav.act("x", device="xbox")
        self.assertIn(("clear", "xinput:0", "2"), self.a.calls)
        self.nav.act("x", device="xbox")         # nothing left to clear: refused, nothing written
        self.assertEqual(self.a.calls.count(("clear", "xinput:0", "2")), 1)
        self.nav.act("confirm", device="xbox")
        self.assertIn(("bind", "xinput:0", "2"), self.a.calls)
        capture = self.nav.view()["bindCapture"]
        self.assertEqual((capture["notation"], capture["left"], capture["waiting"]), ("2", 5, True))
        self.a.result = dict(state="waiting", left=2.2)
        self.nav.poll_tools()
        self.assertEqual(self.nav.view()["bindCapture"]["left"], 3)

    def test_conflict_offers_a_swap_and_no_is_preselected(self):
        self.focus(lambda it: it.get("slot") == "1")
        self.nav.act("confirm", device="xbox")
        self.a.result = dict(state="conflict", source="Y", conflicts=["@controls.slot.2"],
                             swap=dict(slot="@controls.slot.2", sources=["X"]))
        self.nav.poll_tools()
        view = self.nav.view()
        self.assertIn("Right punch gets X", view["bindCapture"]["text"])
        self.assertEqual([o["label"] for o in view["bindCapture"]["options"]], ["No", "Swap"])
        self.nav.act("confirm", device="xbox")
        self.assertNotIn(("accept", True), self.a.calls)
        self.nav.act("confirm", device="xbox")
        self.nav.poll_tools()
        self.nav.act("right", device="xbox")
        self.nav.act("confirm", device="xbox")
        self.assertIn(("accept", True), self.a.calls)

    def test_preset_chooser_reset_and_options(self):
        self.focus(lambda it: it.get("id") == "ctl:preset")
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.nav.overlay, "ctlpreset")
        rows = self.nav.view()["ctlPreset"]["rows"]
        self.assertEqual([r["label"] for r in rows], ["Default", "Tekken Classic", "Arcade stick", "Hitbox / Leverless", "Left-handed"])
        self.nav.act("down", device="xbox")
        self.nav.act("back", device="xbox")
        self.assertNotIn(("preset", "xinput:0", "tekken"), self.a.calls)
        self.nav.act("confirm", device="xbox")
        self.nav.click_entry(3)
        self.assertIn(("preset", "xinput:0", "hitbox"), self.a.calls)
        self.focus(lambda it: it.get("id") == "ctl:reset")
        self.nav.act("confirm", device="xbox")
        self.nav.act("right", device="xbox")
        self.nav.act("confirm", device="xbox")
        self.assertIn(("reset", "xinput:0"), self.a.calls)
        self.focus(lambda it: it.get("id") == "ctl:socd")
        self.nav.act("right", device="xbox")
        self.assertIn(("option", "xinput:0", "socd", "up"), self.a.calls)

    def test_input_test_takes_every_pad_button_until_it_ends(self):
        self.focus(lambda it: it.get("id") == "ctl:test")
        self.nav.act("confirm", device="xbox")
        self.assertTrue(self.nav.binding_active())
        self.a.result = dict(state="test")
        self.a.held["xinput:0"] = {"A", "B", "DDOWN"}
        self.assertTrue(self.nav.poll_tools())
        view = self.nav.view()
        self.assertEqual(view["overlay"], "")
        page = view["bindingsPage"]
        self.assertEqual((page["test"]["active"], page["test"]["notation"]), (True, "d+3+4"))
        lit = {l["notation"] for l in page["lines"] if l.get("lit")}
        self.assertTrue({"3", "4"} <= lit)
        before = list(self.a.calls)
        for action in ("confirm", "x", "next", "down", "back"):
            self.nav.act(action, device="xbox")
        self.assertEqual(self.a.calls, before)
        self.a.result = dict(state="cancelled")
        self.nav.poll_tools()
        self.assertIsNone(self.nav.overlay)
        self.nav.act("confirm", device="xbox")            # Esc ends a test at once
        self.a.result = dict(state="test")
        self.nav.act("back", device="kb")
        self.assertIsNone(self.nav.overlay)

    def test_dry_run_changes_nothing(self):
        self.nav.dry = True
        self.focus(lambda it: it.get("id") == "ctl:socd")
        self.nav.act("right", device="xbox")
        self.focus(lambda it: it.get("slot") == "1")
        self.nav.act("x", device="xbox")
        self.nav.act("chapterNext", device="xbox")        # switching controllers is not a change
        self.assertEqual(self.nav.ctl_pad[self.nav.game.id], "dinput:054C:0CE6")
        self.assertEqual([c for c in self.a.calls if c[0] != "close"], [])

    def test_older_adapter_without_page_features_keeps_plain_rows(self):
        self.a.controls = lambda: [dict(id="pad1", label="Fake pad", port=0,
                                        slots=[dict(id="1", label="Cross", value="A")])]
        items = self.items()
        self.assertEqual([it["label"] for it in items if it["kind"] != "heading"], ["Cross"])


@unittest.skipUnless(os.path.isfile(os.path.join(os.environ.get("OPENRECOMP_T5DR_ROOT", ""), "launcher", "controls_edit.py")),
                     "set OPENRECOMP_T5DR_ROOT to an installed T5DR Online to check against its own editor")
class InstalledEditor(unittest.TestCase):
    """Against an installed T5DR Online's own controls editor and parser, with fake device sources."""

    def setUp(self):
        import sys
        before = set(sys.modules)
        # the installed modules must not stay loaded for other tests (they import t5lobby from there)
        self.addCleanup(lambda: [sys.modules.pop(name) for name in set(sys.modules) - before])

    def test_bindings_read_back_exactly_and_presets_write_what_the_game_parses(self):
        import tempfile
        from openrecomp.adapters.base import Adapter as Base
        from openrecomp.adapters.t5_controls import Controls

        out = tempfile.mkdtemp()

        class Real(Controls, Base):
            def __init__(self):
                super().__init__({"id": "t5dr", "short": "T5"})
                self.root = os.environ["OPENRECOMP_T5DR_ROOT"]
                self.s = SimpleNamespace(out_dir=out, env_overrides=lambda: {})

            def running(self):
                return False

        a = Real()
        self.assertTrue(a.controls_supported())
        ce, _ui, pm, pn = a._controls_modules

        class Source(pn.PadSource):
            def read(self):
                return [pn.Device("xinput", "xinput:0", "Xbox pad", 0, 0, 0, frozenset()),
                        pn.Device("dinput", "ds", "DualSense", 0x054C, 0x0CE6, None, frozenset()),
                        pn.Device("keys1", "keys1", "Keyboard", 0, 0, None, frozenset())]

        with mock.patch.object(pn, "default_sources", lambda env=None, keyboard=False: [Source()]):
            try:
                a.poll_binding()
                for pad_id, kind, vid, pid in (("xinput:0", "xinput", 0, 0), ("ds", "dinput", 0x054C, 0x0CE6),
                                               ("keys1", "keys1", 0, 0)):
                    row = next(r for r in a.controls() if r["id"] == pad_id)
                    for preset, _label in row["presets"]:
                        a.apply_preset(pad_id, preset)
                        a.poll_binding()
                        row = next(r for r in a.controls() if r["id"] == pad_id)
                        self.assertEqual(row["preset"], preset)
                        with open(os.path.join(out, "controls.ini"), encoding="latin-1") as f:
                            table = pm.Controls(f.read()).table(kind, row["port"], vid, pid)
                        for slot in row["slots"]:
                            self.assertEqual(slot["sources"], list(table.sources_exactly(pm.target_mask(slot["id"]))))
            finally:
                a.controls_close()


if __name__ == "__main__":
    unittest.main()
