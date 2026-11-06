"""Tekken 4's controls.ini: parse, write, devices, presets (openrecomp/t4_controls_ini.py). The same golden text and the same
expectations are checked by the T4 runtime's own test (tools/pad_bindings_test.cpp, ps2_pad_bindings.h), so the two parsers
agree on the format."""
import os
import tempfile
import unittest

from openrecomp import t4_controls_ini as ini

GOLDEN = """; a comment
[player1]
device = keyboard+xinput:2
[player1.pad]
1 = x lb
CROSS = NONE
L2 = RT
UP = DUP, LUP RUP
[player1.keys]
SQUARE = left z
RP = F5
[player2]
device = xinput:0
[player2.keys]
1 = NUM4
"""


class Parse(unittest.TestCase):
    def test_default_files(self):
        for text in ("", "; only a comment\r\n# another\r\n", "[player1]\ndevice = auto\n[player2]\ndevice = AUTO\n",
                     "﻿[player1]\r\ndevice = auto ; the usual\r\n", "[player1.pad]\n[player1.keys]\n"):
            self.assertTrue(ini.Controls().parse(text).is_default(), text)
        for text in ("[player1.pad]\nSQUARE = A\n", "[player2.keys]\n1 = U\n", "[player1]\ndevice = keyboard\n"):
            self.assertFalse(ini.Controls().parse(text).is_default(), text)

    def test_golden_file_means_what_the_runtime_test_says(self):
        c = ini.Controls().parse(GOLDEN)
        p1, p2 = c.players
        self.assertEqual((p1.keyboard, p1.pad, p2.keyboard, p2.pad), (True, 2, False, 0))
        self.assertEqual(c.sources(0, "pad", "1"), ["X", "LB"])
        self.assertEqual(c.sources(0, "pad", "3"), [])                      # NONE
        self.assertEqual(c.sources(0, "pad", "L2"), ["RT"])
        self.assertEqual(c.sources(0, "pad", "UP"), ["DUP", "LUP", "RUP"])
        self.assertEqual(c.sources(0, "pad", "2"), ["Y"])                   # unlisted: default
        self.assertEqual(c.sources(0, "keys", "1"), ["LEFT", "Z"])          # Square replaced, Num0 gone
        self.assertEqual(c.sources(0, "keys", "2"), ["F5"])                 # RP is Tekken's 2
        self.assertEqual(c.sources(0, "keys", "L1"), ["Q"])
        self.assertEqual(c.sources(1, "keys", "1"), ["NUM4"])
        self.assertEqual(c.sources(1, "keys", "L1"), [])                    # player 2 has no default keys
        self.assertEqual(c.warnings, [])

    def test_mistakes_are_skipped_and_reported(self):
        c = ini.Controls().parse("[player1]\ndevice = banana\nfoo\n[player1.pad]\nBOGUS = A\nSQUARE = ZZ\n"
                                 "[player1.keys]\n1 = left numpad z\n")
        self.assertTrue(c.players[0].default_device())
        self.assertEqual(len(c.warnings), 5)                                  # device, foo, BOGUS, ZZ, numpad
        self.assertEqual(c.sources(0, "keys", "1"), ["LEFT", "Z"])

    def test_devices(self):
        c = ini.Controls().parse("[player1]\ndevice = none\n[player2]\ndevice = auto + keyboard\n")
        self.assertEqual((c.players[0].keyboard, c.players[0].pad), (False, None))
        self.assertTrue(c.players[1].default_device())                         # auto swallows the rest
        c = ini.Controls().parse("[PLAYER2]\nDevice=Keyboard , XInput:3\n")
        self.assertEqual((c.players[1].keyboard, c.players[1].pad), (True, 3))
        c = ini.Controls().parse("[player1]\ndevice = xinput:9\n")
        self.assertTrue(c.players[0].default_device())

    def test_names(self):
        self.assertEqual(ini.canonical_key("return"), "ENTER")
        self.assertEqual(ini.canonical_key("quote"), "APOSTROPHE")
        self.assertEqual(ini.canonical_key("a"), "A")
        self.assertEqual(ini.KEY_VK["NUMADD"], 0x6B)
        self.assertEqual(ini.VK_NAME[0x1B], "ESC")
        self.assertEqual(len(ini.SLOTS), 16)
        for slot, sources in ini.PAD_DEFAULT.items():
            self.assertTrue(all(s in ini.PAD_SOURCES for s in sources), slot)
        for sources in ini.KEYS_DEFAULT[0].values():
            self.assertTrue(all(ini.key_ok(s) for s in sources))

    def test_defaults_are_the_runtimes_fixed_layout(self):
        c = ini.Controls()
        self.assertEqual(c.sources(0, "keys", "3"), ["DOWN", "X", "SPACE"])
        self.assertEqual(c.sources(0, "keys", "4"), ["RIGHT", "C", "ESC"])
        self.assertEqual((c.sources(0, "keys", "L2"), c.sources(0, "keys", "R2")), (["LSHIFT"], ["RSHIFT"]))
        self.assertEqual(c.sources(0, "pad", "DOWN"), ["DDOWN", "LDOWN"])
        self.assertEqual(c.sources(0, "pad", "SELECT"), ["BACK"])
        self.assertEqual(c.sources(1, "keys", "1"), [])


class Write(unittest.TestCase):
    def test_round_trip_keeps_only_the_overrides(self):
        c = ini.Controls().parse(GOLDEN)
        again = ini.Controls().parse(c.text())
        self.assertEqual(again.text(), c.text())
        for player in range(2):
            for kind in ini.KINDS:
                self.assertEqual(again.effective(player, kind), c.effective(player, kind))
        self.assertEqual((again.players[0].keyboard, again.players[0].pad), (True, 2))
        self.assertIn("1 = X LB", c.text())
        self.assertIn("3 = NONE", c.text())
        self.assertNotIn("2 = Y", c.text())                    # unchanged buttons are not written

    def test_a_default_model_writes_a_default_file(self):
        text = ini.Controls().text()
        self.assertIn("device = auto", text)
        self.assertTrue(ini.Controls().parse(text).is_default())

    def test_unknown_sections_survive(self):
        text = "[player1]\ndevice = auto\n[future]\nthing = 1\n; note\n"
        c = ini.Controls().parse(text)
        self.assertIn("[future]", c.text())
        self.assertIn("thing = 1", c.text())

    def test_save_is_atomic_and_crlf(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "save", "controls.ini")
            c = ini.Controls.load(path)
            self.assertTrue(c.is_default())                     # a missing file is the default layout
            c.bind(0, "keys", "1", ["U"])
            c.save()
            self.assertEqual(os.listdir(os.path.join(folder, "save")), ["controls.ini"])
            with open(path, "rb") as stream:
                raw = stream.read()
            self.assertIn(b"\r\n", raw)
            self.assertEqual(ini.Controls.load(path).sources(0, "keys", "1"), ["U"])


class Edit(unittest.TestCase):
    def test_bind_clear_release_reset(self):
        c = ini.Controls()
        c.bind(0, "pad", "1", ["LB", "LB"])
        self.assertEqual(c.sources(0, "pad", "1"), ["LB"])
        self.assertEqual(c.users(0, "pad", "LB", exclude="1"), ["L1"])
        c.release(0, "pad", "LB", keep="1")
        self.assertEqual(c.sources(0, "pad", "L1"), [])
        self.assertTrue(c.overridden(0, "pad", "L1"))
        c.clear(0, "pad", "2")
        self.assertEqual(c.sources(0, "pad", "2"), [])
        c.reset(0, "pad")
        self.assertTrue(c.is_default())
        self.assertEqual(c.sources(0, "pad", "1"), ["X"])

    def test_presets(self):
        c = ini.Controls()
        self.assertEqual(c.current_preset(0, "pad"), "default")
        self.assertEqual(c.current_preset(0, "keys"), "default")
        c.apply_preset(0, "pad", "t4_arcade")
        self.assertEqual(c.sources(0, "pad", "3"), ["RB"])
        self.assertEqual(c.sources(0, "pad", "4"), ["RT"])
        self.assertEqual(c.sources(0, "pad", "R1"), ["A"])
        self.assertEqual(c.current_preset(0, "pad"), "t4_arcade")
        self.assertEqual(c.current_preset(0, "keys"), "default")
        c.bind(0, "pad", "START", ["Y"])
        self.assertEqual(c.current_preset(0, "pad"), "custom")
        c.apply_preset(0, "pad", "default")
        self.assertTrue(c.is_default())
        c.apply_preset(1, "keys", "numpad")
        self.assertEqual(c.sources(1, "keys", "1"), ["NUM4"])
        self.assertEqual(c.current_preset(1, "keys"), "numpad")
        self.assertEqual([p for p, _l in ini.presets_for("pad")], ["default", "t4_arcade", "t4_combos"])
        self.assertEqual([p for p, _l in ini.presets_for("keys")], ["default", "t4_arcade", "t4_combos", "numpad"])
        with self.assertRaises(KeyError):
            c.apply_preset(0, "pad", "numpad")
        # a preset's bindings are all valid names
        for _pid, _label, _hint, plans in ini.PRESETS:
            for kind, plan in plans.items():
                for slot, sources in plan.items():
                    self.assertIn(slot, ini.PAGE_SLOT_IDS)
                    for source in sources:
                        self.assertTrue(source in ini.PAD_SOURCES if kind == "pad" else ini.key_ok(source), source)

    def test_the_runtimes_device_order(self):
        c = ini.Controls()
        self.assertEqual(c.resolve({0, 1}), {0: 0, 1: 1})
        self.assertEqual(c.resolve({2}), {2: 0})
        self.assertEqual(c.resolve({1, 3}), {1: 0, 3: 1})
        c.assign_pad(1, 1)                                            # slot 1 is player 2's; player 1 takes the next free
        self.assertEqual(c.resolve({0, 1}), {0: 0, 1: 1})
        self.assertEqual(c.resolve({1, 2}), {2: 0, 1: 1})
        self.assertEqual(c.resolve({2}), {2: 0})
        c.assign_pad(1, None)
        self.assertEqual((c.players[1].pad), ini.AUTO_PAD)
        c.assign_pad(0, 0)
        c.assign_pad(0, 1)                                            # moved: player 1 loses its pin
        self.assertEqual(c.players[0].pad, ini.AUTO_PAD)
        self.assertEqual(c.players[1].pad, 0)
        self.assertEqual(c.resolve({0, 1}), {0: 1, 1: 0})
        self.assertEqual(c.resolve({1}), {1: 0})                      # pinned slot absent: player 2 has no pad

    def test_keyboard_assignment(self):
        c = ini.Controls()
        self.assertEqual(c.keyboard_player(), 0)
        c.assign_keyboard(1)
        self.assertEqual((c.players[0].keyboard, c.players[1].keyboard, c.keyboard_player()), (False, True, 1))
        self.assertEqual(c.players[0].device_text(), "xinput")
        self.assertEqual(c.players[1].device_text(), "keyboard+xinput")
        c.assign_keyboard(None)
        self.assertTrue(c.is_default())


if __name__ == "__main__":
    unittest.main()
