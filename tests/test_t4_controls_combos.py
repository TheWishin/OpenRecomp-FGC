"""Tekken 4 Pad bindings page: combo slots (1+3+4 on one button). The file has no combo syntax: a source listed under
several attack targets presses them all, and the page shows that as one combo slot."""
import os
import tempfile
import unittest

from openrecomp import t4_controls_ini as ini
from test_t4_controls import T4Editable

OWNER = """[player1]
device = auto
[player1.pad]
1 = X LT
3 = A LT
4 = B LT
L2 = none
"""


class Combos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.adapter = T4Editable(self.tmp.name)

    def bound(self):
        return ini.Controls.load(self.adapter._t4c_path())

    def write(self, text):
        os.makedirs(os.path.dirname(self.adapter._t4c_path()), exist_ok=True)
        with open(self.adapter._t4c_path(), "w", encoding="utf-8") as stream:
            stream.write(text)

    def test_owners_hand_written_file_shows_as_one_combo(self):
        self.write(OWNER)
        row = self.adapter.row("t4:xinput:0")
        shown = {s["id"]: s["sources"] for s in row["slots"]}
        self.assertEqual(shown["1+3+4"], ["LT"])
        self.assertEqual((shown["1"], shown["3"], shown["4"], shown["2"]), (["X"], ["A"], ["B"], ["Y"]))
        self.assertEqual(shown["L2"], [])
        for other in ini.COMBO_IDS:
            if other != "1+3+4":
                self.assertEqual(shown[other], [], other)
        self.assertEqual([s["id"] for s in row["slots"] if s["group"] == "macro"], list(ini.COMBO_IDS))
        c = self.bound()
        c.save()
        again = ini.Controls.load(c.path)
        self.assertEqual(again.effective(0, "pad"), c.effective(0, "pad"))
        self.assertEqual(again.combo_sources(0, "pad", "1+3+4"), ["LT"])
        self.assertIn("1 = X LT", again.text())
        self.assertIn("L2 = NONE", again.text())

    def test_binding_a_combo_writes_every_target_and_frees_the_source(self):
        state = self.adapter.capture("t4:xinput:0", "1+3+4", {"LT"})
        self.assertEqual(state["state"], "conflict")           # LT is L2 now
        self.adapter.accept_binding()
        text = self.adapter.file()
        for line in ("1 = X LT", "3 = A LT", "4 = B LT", "L2 = NONE"):
            self.assertIn(line, text)
        self.assertNotIn("\n2 = ", text)
        self.assertEqual(self.bound().combo_sources(0, "pad", "1+3+4"), ["LT"])

    def test_a_free_source_binds_without_a_conflict(self):
        state = self.adapter.capture("t4:xinput:0", "1+2", {"DUP"})
        self.assertEqual(state["state"], "conflict")           # DUP is UP
        self.adapter.accept_binding()
        self.assertEqual(self.bound().sources(0, "pad", "UP"), ["LUP"])

    def test_every_combo_round_trips_on_pad_and_keyboard(self):
        for kind, source in (("pad", "RS"), ("keys", "O")):
            for combo in ini.COMBO_IDS:
                c = ini.Controls()
                before = {s: c.sources(0, kind, s) for s in "1234"}
                c.bind_combo(0, kind, combo, [source])
                c2 = ini.Controls().parse(c.text())
                self.assertEqual(c2.combo_sources(0, kind, combo), [source], combo)
                targets = ini.COMBO_TARGETS[combo]
                for t in targets:
                    self.assertEqual(c2.sources(0, kind, t), before[t] + [source])
                    self.assertEqual(c2.plain_sources(0, kind, t), before[t])
                for t in set("1234") - set(targets):
                    self.assertEqual(c2.sources(0, kind, t), before[t])
                self.assertTrue(all(c2.combo_sources(0, kind, o) == [] for o in ini.COMBO_IDS if o != combo))

    def test_keyboard_combo(self):
        state = self.adapter.capture("t4:keyboard", "1+2", {"O"})
        self.assertEqual(state["state"], "ready")
        self.adapter.accept_binding()
        c = self.bound()
        self.assertEqual(c.sources(0, "keys", "1"), ["LEFT", "Z", "NUM0", "O"])
        self.assertEqual(c.sources(0, "keys", "2"), ["UP", "V", "NUM1", "O"])
        self.assertEqual(self.adapter.slot("t4:keyboard", "1+2")["sources"], ["O"])
        self.assertEqual(self.adapter.slot("t4:keyboard", "1")["sources"], ["LEFT", "Z", "NUM0"])

    def test_keyboard_file_loads_as_combo(self):
        self.write("[player1.keys]\n1 = U O\n2 = I O\n")
        self.assertEqual(self.adapter.slot("t4:keyboard", "1+2")["sources"], ["O"])
        self.assertEqual(self.adapter.slot("t4:keyboard", "1")["sources"], ["U"])

    def test_clearing_a_combo_only_takes_the_source_off_those_attacks(self):
        self.write(OWNER)
        self.adapter.clear_binding("t4:xinput:0", "1+3+4")
        c = self.bound()
        self.assertEqual((c.sources(0, "pad", "1"), c.sources(0, "pad", "3"), c.sources(0, "pad", "4")),
                         (["X"], ["A"], ["B"]))
        self.assertEqual(c.sources(0, "pad", "L2"), [])
        self.assertEqual(c.combo_sources(0, "pad", "1+3+4"), [])

    def test_clearing_a_plain_attack_keeps_its_combo(self):
        self.write(OWNER)
        self.adapter.clear_binding("t4:xinput:0", "1")
        c = self.bound()
        self.assertEqual(c.sources(0, "pad", "1"), ["LT"])
        self.assertEqual(c.combo_sources(0, "pad", "1+3+4"), ["LT"])
        self.assertEqual(self.adapter.slot("t4:xinput:0", "1")["sources"], [])

    def test_rebinding_a_plain_attack_keeps_its_combo(self):
        self.write(OWNER)
        state = self.adapter.capture("t4:xinput:0", "1", {"RS"})
        self.assertEqual(state["state"], "conflict")           # RS is R3
        self.adapter.accept_binding(swap=False)
        c = self.bound()
        self.assertEqual(c.sources(0, "pad", "1"), ["RS", "LT"])
        self.assertEqual(c.combo_sources(0, "pad", "1+3+4"), ["LT"])
        self.assertEqual(c.sources(0, "pad", "R3"), [])

    def test_a_source_in_another_combo_is_a_conflict_with_that_combo_and_moves(self):
        self.write(OWNER)
        state = self.adapter.capture("t4:xinput:0", "1+2", {"LT"})
        self.assertEqual(state["state"], "conflict")
        self.assertEqual(state["conflicts"], [self.adapter._t4c_label("1+3+4")])
        self.assertNotIn("swap", state)
        self.adapter.accept_binding()
        c = self.bound()
        self.assertEqual(c.combo_sources(0, "pad", "1+2"), ["LT"])
        self.assertEqual(c.combo_sources(0, "pad", "1+3+4"), [])
        self.assertEqual((c.sources(0, "pad", "3"), c.sources(0, "pad", "4")), (["A"], ["B"]))

    def test_a_plain_source_taken_for_a_combo_names_the_action_and_frees_it(self):
        state = self.adapter.capture("t4:xinput:0", "3+4", {"RT"})
        self.assertEqual(state["conflicts"], [self.adapter._t4c_label("R2")])
        self.adapter.accept_binding()
        c = self.bound()
        self.assertEqual(c.sources(0, "pad", "R2"), [])
        self.assertEqual(c.sources(0, "pad", "3"), ["A", "RT"])

    def test_preset_with_combos(self):
        self.adapter.apply_preset("t4:xinput:0", "t4_combos")
        c = self.bound()
        self.assertEqual(self.adapter.row("t4:xinput:0")["preset"], "t4_combos")
        self.assertEqual((c.combo_sources(0, "pad", "1+2"), c.combo_sources(0, "pad", "3+4")), (["RB"], ["RT"]))
        self.assertEqual((c.sources(0, "pad", "R1"), c.sources(0, "pad", "R2")), ([], []))
        self.assertEqual(c.combo_sources(0, "pad", "1+3+4"), [])
        self.adapter.apply_preset("t4:keyboard", "t4_combos")
        c = self.bound()
        self.assertEqual((c.combo_sources(0, "keys", "1+2"), c.combo_sources(0, "keys", "3+4")), (["O"], ["L"]))
        self.assertEqual(self.adapter.row("t4:keyboard")["preset"], "t4_combos")

    def test_input_test_lights_the_combo_and_its_attacks(self):
        self.write(OWNER)
        self.adapter.begin_input_test("t4:xinput:0")
        self.adapter.reader.pads[0] = {"LT"}
        self.assertEqual(set(self.adapter.controls_input("t4:xinput:0")["lit"]), {"1", "3", "4", "1+3+4"})


class PageShape(unittest.TestCase):
    """The page like Tekken 8's button config: the owner's row order, per-player tabs, live strip, glyph style."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.adapter = T4Editable(self.tmp.name)

    def test_rows_come_in_the_owners_order(self):
        ids = [s["id"] for s in self.adapter.row("t4:xinput:0")["slots"]]
        self.assertEqual(ids, ["1", "2", "3", "4", "1+2", "3+4", "1+3", "2+4", "1+2+3+4", "1+4", "2+3", "1+2+3",
                               "1+3+4", "2+3+4", "1+2+4", "START", "SELECT", "L1", "R1", "L2", "R2", "L3", "R3",
                               "UP", "DOWN", "LEFT", "RIGHT"])
        groups = [s["group"] for s in self.adapter.row("t4:xinput:0")["slots"]]
        self.assertEqual(groups[:4], ["attack"] * 4)
        self.assertEqual(set(groups[4:15]), {"macro"})

    def test_player_two_has_a_tab_before_the_second_pad_is_plugged_in(self):
        rows = self.adapter.controls()
        self.assertEqual([(r["id"], r["port"]) for r in rows],
                         [("t4:keyboard", 0), ("t4:xinput:0", 0), ("t4:player:2", 1)])
        self.adapter.clear_binding("t4:player:2", "1")
        self.adapter.apply_preset("t4:player:2", "t4_combos")
        c = ini.Controls.load(self.adapter._t4c_path())
        self.assertEqual(c.combo_sources(1, "pad", "1+2"), ["RB"])
        self.assertEqual(c.sources(0, "pad", "1"), ["X"])
        with self.assertRaises(RuntimeError):
            self.adapter.begin_binding("t4:player:2", "1")
        with self.assertRaises(RuntimeError):
            self.adapter.begin_input_test("t4:player:2")
        # the second pad arrives: the placeholder is gone, the pad shows the same bindings
        self.adapter.reader.connected.add(1)
        self.adapter.poll_binding()
        self.assertEqual([r["id"] for r in self.adapter.controls()], ["t4:keyboard", "t4:xinput:0", "t4:xinput:1"])
        self.assertEqual(self.adapter.slot("t4:xinput:1", "1+2")["sources"], ["RB"])

    def test_reset_is_per_player(self):
        self.adapter.reader.connected.add(1)
        self.adapter.apply_preset("t4:xinput:0", "t4_combos")
        self.adapter.apply_preset("t4:xinput:1", "t4_combos")
        self.adapter.reset_controls("t4:xinput:1")
        c = ini.Controls.load(self.adapter._t4c_path())
        self.assertEqual(c.combo_sources(0, "pad", "1+2"), ["RB"])
        self.assertEqual(c.players[1].maps["pad"], {})

    def test_the_strip_is_live_for_a_pad_without_an_input_test_and_not_for_the_keyboard(self):
        self.adapter.controls()
        self.adapter.reader.pads[0] = {"X", "A", "DDOWN"}
        live = self.adapter.controls_input("t4:xinput:0")
        self.assertEqual(set(live["lit"]), {"1", "3", "DOWN"})
        self.assertEqual(live["notation"], "d+1+3")
        self.adapter.reader.keys = {"Z"}
        self.assertEqual(self.adapter.controls_input("t4:keyboard"), dict(lit=[], notation=""))
        self.adapter.reader.pads[0] = {"X", "A"}
        self.assertEqual(self.adapter.controls_input("t4:player:2"), dict(lit=[], notation=""))

    def test_a_combo_lights_with_the_buttons_that_trigger_it(self):
        self.adapter.apply_preset("t4:xinput:0", "t4_combos")
        self.adapter.reader.pads[0] = {"RB"}
        self.assertEqual(set(self.adapter.controls_input("t4:xinput:0")["lit"]), {"1", "2", "1+2"})


class GlyphStyle(unittest.TestCase):
    def test_restyle_maps_the_same_physical_button(self):
        from openrecomp import pad_glyphs as pg
        self.assertEqual(pg.restyle("xbox", "A", "ps")["text"], "cross")
        self.assertEqual(pg.restyle("xbox", "LT", "ps")["text"], "L2")
        self.assertEqual(pg.restyle("xbox", "DUP", "ps")["shape"], "dpad")
        self.assertEqual(pg.restyle("ps", "B1", "xbox")["text"], "X")
        self.assertEqual(pg.restyle("ps", "B2", "xbox")["text"], "A")
        self.assertEqual(pg.restyle("xbox", "A", "xbox"), pg.glyph("xbox", "A"))
        self.assertEqual(pg.restyle("xbox", "A", "kb"), pg.glyph("xbox", "A"))
        self.assertEqual(pg.restyle("keyboard", "Z", "ps"), pg.glyph("keyboard", "Z"))

    def test_the_page_draws_the_launchers_button_prompt_style(self):
        from openrecomp.nav import Game, Nav
        from test_nav import manifest
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        adapter = T4Editable(tmp.name)
        nav = Nav([Game(manifest(), adapter)])
        nav.screen = "hub"
        nav.sec[nav.game.id] = "controls"
        nav._ctl_select(nav.game, "t4:xinput:0")
        shapes = {}
        for style in ("auto", "ps", "xbox"):
            nav.prompt_style = style
            item = next(it for it in nav.items() if it.get("slot") == "3" and it.get("ctl") == "slot")
            shapes[style] = item["glyphs"][0]["text"]
        self.assertEqual(shapes, {"auto": "A", "ps": "cross", "xbox": "A"})


if __name__ == "__main__":
    unittest.main()
