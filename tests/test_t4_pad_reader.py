"""The XInput / keyboard reader of Tekken 4's Pad bindings page: the names it reports are controls.ini's, and it never
fails without a pad or on a machine without XInput."""
import unittest

from openrecomp import t4_controls_ini as ini
from openrecomp import t4_pad_reader as reader


class Held(unittest.TestCase):
    def test_buttons_triggers_and_sticks_in_the_runtimes_names(self):
        self.assertEqual(reader.held_sources(0, 0, 0, 0, 0, 0, 0), set())
        self.assertEqual(reader.held_sources(0x4000 | 0x0100, 0, 0, 0, 0, 0, 0), {"X", "LB"})
        self.assertEqual(reader.held_sources(0x0001 | 0x0010 | 0x0020, 0, 0, 0, 0, 0, 0), {"DUP", "START", "BACK"})
        self.assertEqual(reader.held_sources(0, 31, 30, 0, 0, 0, 0), {"LT"})            # past 30, not at 30
        self.assertEqual(reader.held_sources(0, 0, 200, 0, 0, 0, 0), {"RT"})
        self.assertEqual(reader.held_sources(0, 0, 0, 20000, 20000, 0, 0), {"LRIGHT", "LUP"})
        self.assertEqual(reader.held_sources(0, 0, 0, -20000, -20000, 0, 0), {"LLEFT", "LDOWN"})
        self.assertEqual(reader.held_sources(0, 0, 0, 0, 0, 0, 30000), {"RUP"})
        self.assertEqual(reader.held_sources(0, 0, 0, 10000, 10000, 0, 0), set())        # under half way
        every = reader.held_sources(0xF3FF, 255, 255, 32767, 32767, -32768, -32768)
        self.assertTrue(every <= set(ini.PAD_SOURCES))
        self.assertEqual(every & {"A", "B", "X", "Y", "LB", "RB", "LT", "RT", "BACK", "START", "LS", "RS"},
                         {"A", "B", "X", "Y", "LB", "RB", "LT", "RT", "BACK", "START", "LS", "RS"})

    def test_reader_without_a_pad_reports_nothing_and_does_not_fail(self):
        r = reader.Reader()
        self.assertIsInstance(r.step(), set)
        self.assertIsInstance(r.slots(), set)
        self.assertIsInstance(r.keys_held(), set)
        self.assertTrue(all(name in ini.KEY_VK for name in r.keys_held()))
        self.assertEqual(r.pad_held(3) if 3 not in r.slots() else set(), set())

    def test_every_key_name_the_reader_can_report_is_one_the_file_accepts(self):
        calls = []

        class Down(reader.Reader):
            def __init__(self):
                super().__init__()
                self.key_state = lambda vk: calls.append(vk) or (0x8000 if vk in (0x0D, 0x41, 0xA0) else 0)

        held = Down().keys_held()
        self.assertEqual(held, {"ENTER", "A", "LSHIFT"})
        self.assertEqual(len(calls), len(set(calls)))        # one query per key, RETURN / ESCAPE / QUOTE not asked twice


if __name__ == "__main__":
    unittest.main()
