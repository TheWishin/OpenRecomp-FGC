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


if __name__ == "__main__":
    unittest.main()
