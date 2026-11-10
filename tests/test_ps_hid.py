"""PlayStation pads read directly as HID devices (every report mode) for the T4 and T5DR pad pages and launcher
navigation: fake reports only, no device."""
import os
import tempfile
import unittest
import zlib
from pathlib import Path

from openrecomp import ps_hid
from openrecomp import t4_controls_ini as ini
from openrecomp.adapters.t4_controls import T4Controls
from openrecomp.pad import HidPlayStationReader
from openrecomp.t4_pad_reader import HID_FIRST, Reader, pad_name
from test_nav import Fake, manifest

CENTRE = (128, 128, 128, 128)
HATS = {None: 8, "UP": 0, "RIGHT": 2, "DOWN": 4, "LEFT": 6}


def buttons(square=0, cross=0, circle=0, triangle=0, l1=0, r1=0, l2=0, r2=0, share=0, options=0, l3=0, r3=0, hat=None):
    """The two button bytes every report has (hat nibble, face buttons, shoulders, share/options, sticks)."""
    b0 = HATS[hat] | square << 4 | cross << 5 | circle << 6 | triangle << 7
    b1 = l1 | r1 << 1 | l2 << 2 | r2 << 3 | share << 4 | options << 5 | l3 << 6 | r3 << 7
    return b0, b1


def with_crc(report, n):
    body = bytearray(report[:n - 4])
    crc = zlib.crc32(bytes(body), zlib.crc32(b"\xA1")) & 0xFFFFFFFF
    return bytes(body) + crc.to_bytes(4, "little")


def pad(report, size):
    return bytes(report) + bytes(max(0, size - len(report)))


def dualsense_usb(sticks=CENTRE, l2=0, r2=0, **kw):
    b0, b1 = buttons(**kw)
    return pad(bytes([1, *sticks, l2, r2, 0, b0, b1, 0]), 64)


def dualsense_bt_simple(sticks=CENTRE, l2=0, r2=0, **kw):
    b0, b1 = buttons(**kw)
    return pad(bytes([1, *sticks, b0, b1, 0, l2, r2]), 78)


def dualsense_bt_ext(sticks=CENTRE, l2=0, r2=0, **kw):
    b0, b1 = buttons(**kw)
    return with_crc(pad(bytes([0x31, 0x02, *sticks, l2, r2, 0, b0, b1, 0]), 78), 78)


def ds4_usb(sticks=CENTRE, l2=0, r2=0, **kw):
    b0, b1 = buttons(**kw)
    return pad(bytes([1, *sticks, b0, b1, 0, l2, r2]), 64)


def ds4_bt_ext(sticks=CENTRE, l2=0, r2=0, **kw):
    b0, b1 = buttons(**kw)
    return with_crc(pad(bytes([0x11, 0xC0, 0x00, *sticks, b0, b1, 0, l2, r2]), 78), 78)


class Parse(unittest.TestCase):
    def held(self, model, bt, report):
        mode, sources = ps_hid.ps_parse(model, bt, report)
        return mode, ps_hid.xinput_names(sources)

    def test_every_mode_gives_the_same_buttons(self):
        cases = (("dualsense", False, dualsense_usb, "usb"), ("dualsense", True, dualsense_bt_simple, "bt-simple"),
                 ("dualsense", True, dualsense_bt_ext, "bt-ext"), ("edge", True, dualsense_bt_ext, "bt-ext"),
                 ("ds4", False, ds4_usb, "usb"), ("ds4", True, ds4_bt_ext, "bt-ext"))
        for model, bt, make, mode in cases:
            with self.subTest(model=model, mode=mode):
                self.assertEqual(self.held(model, bt, make()), (mode, set()))
                self.assertEqual(self.held(model, bt, make(cross=1, l1=1, options=1, hat="UP"))[1],
                                 {"A", "LB", "START", "DUP"})
                self.assertEqual(self.held(model, bt, make(square=1, circle=1, triangle=1, r1=1, share=1, l3=1, r3=1))[1],
                                 {"X", "B", "Y", "RB", "BACK", "LS", "RS"})

    def test_triggers_sticks_and_resting_pad(self):
        for model, bt, make in (("dualsense", False, dualsense_usb), ("dualsense", True, dualsense_bt_ext),
                                ("ds4", False, ds4_usb)):
            with self.subTest(model=model):
                self.assertEqual(self.held(model, bt, make(l2=0, r2=0))[1], set())          # rest is no press
                self.assertEqual(self.held(model, bt, make(l2=255))[1], {"LT"})
                self.assertEqual(self.held(model, bt, make(r2=200))[1], {"RT"})
                self.assertEqual(self.held(model, bt, make(r2=60))[1], set())               # under half travel
                self.assertEqual(self.held(model, bt, make(sticks=(255, 128, 0, 128)))[1], {"LRIGHT", "RLEFT"})
                self.assertEqual(self.held(model, bt, make(sticks=(128, 0, 128, 255)))[1], {"LUP", "RDOWN"})

    def test_reports_without_input_are_ignored(self):
        self.assertEqual(ps_hid.ps_parse("dualsense", True, bytes([0x02] + [0] * 77)), (None, None))
        self.assertEqual(ps_hid.ps_parse("ds4", True, b"\x01\x00"), (None, None))
        self.assertEqual(ps_hid.ps_parse("ds4", True, bytes([0x11, 0x00] + [0] * 76)), (None, None))   # no input flag

    def test_crc(self):
        good = dualsense_bt_ext(cross=1)
        self.assertTrue(ps_hid.ps_crc_ok("dualsense", good))
        self.assertFalse(ps_hid.ps_crc_ok("dualsense", good[:20] + b"\x7f" + good[21:]))
        self.assertIsNone(ps_hid.ps_crc_ok("dualsense", dualsense_usb()))
        self.assertTrue(ps_hid.ps_crc_ok("ds4", ds4_bt_ext()))

    def test_names_are_the_ones_controls_ini_accepts(self):
        self.assertTrue(set(ps_hid.XINPUT_NAMES.values()) <= set(ini.PAD_SOURCES))


class FakeApi:
    """HID API stand-in: pads that are plugged in, each with a queue of reports."""

    def __init__(self):
        self.pads = {}          # path -> HidInfo
        self.queue = {}         # path -> [reports]
        self.refuse = set()
        self.opened = []

    def plug(self, path, model, bt, in_len, pid=0x0CE6):
        self.pads[path] = ps_hid.HidInfo(path, ps_hid.PS_VID, pid, model, bt, in_len)
        self.queue[path] = []

    def enumerate(self):
        return list(self.pads.values())

    def open(self, info):
        if info.path in self.refuse:
            return None
        self.opened.append(info.path)
        api = self

        class Reader:
            failed = False

            def reads(self, limit=128):
                if info.path not in api.pads:
                    self.failed = True
                    return []
                out, api.queue[info.path] = api.queue[info.path], []
                return out

            def close(self):
                api.opened.remove(info.path)

        return Reader()


class Hid(unittest.TestCase):
    def setUp(self):
        self.api = FakeApi()
        self.api.plug("pad-a", "dualsense", True, 78)
        self.hid = ps_hid.HidPads(api=self.api, env={})

    def test_scan_open_read_and_unplug(self):
        self.hid.scan()
        self.api.queue["pad-a"].append(dualsense_bt_ext(cross=1))
        (one,) = self.hid.read()
        self.assertEqual((one.name, one.vid, one.pid), ("DualSense (Bluetooth)", 0x054C, 0x0CE6))
        self.assertEqual(ps_hid.xinput_names(one.pressed), {"A"})
        self.assertEqual(ps_hid.xinput_names(self.hid.read()[0].pressed), {"A"})        # held until the next report
        del self.api.pads["pad-a"]
        self.assertEqual(self.hid.read(), [])
        self.assertEqual(self.api.opened, [])

    def test_a_tap_between_two_polls_is_not_lost(self):
        self.hid.scan()
        self.api.queue["pad-a"] += [dualsense_bt_ext(cross=1), dualsense_bt_ext()]
        (one,) = self.hid.read()
        self.assertEqual(ps_hid.xinput_names(one.pressed), {"A"})
        self.assertEqual(ps_hid.xinput_names(self.hid.read()[0].pressed), set())

    def test_bad_crc_after_a_good_one_is_dropped(self):
        self.hid.scan()
        bad = bytearray(dualsense_bt_ext(circle=1))
        bad[30] ^= 0xFF
        self.api.queue["pad-a"] += [dualsense_bt_ext(cross=1), bytes(bad)]
        (one,) = self.hid.read()
        self.assertEqual(ps_hid.xinput_names(one.pressed), {"A"})

    def test_pad_that_never_sends_a_good_crc_is_used_after_a_run(self):
        self.hid.scan()
        bad = bytearray(dualsense_bt_ext(circle=1))
        bad[30] ^= 0xFF
        self.api.queue["pad-a"] += [bytes(bad)] * (ps_hid.CRC_RUN_NEVER_GOOD + 1)
        self.assertEqual(ps_hid.xinput_names(self.hid.read()[0].pressed), {"B"})

    def test_pad_that_cannot_be_opened_stays_closed_until_unplugged(self):
        self.api.refuse.add("pad-a")
        self.hid.scan()
        self.hid.scan()
        self.assertEqual(self.hid.read(), [])
        self.assertEqual([n for n in self.hid.notes if n[0] == "open_failed"], [("open_failed", "pad-a")])

    def test_steam_owned_pad_is_left_to_the_virtual_pad_while_xinput_is_there(self):
        env = {"SDL_GAMECONTROLLER_IGNORE_DEVICES": "0x054C/0x0CE6"}
        for present, expected in ((True, []), (False, ["pad-a"])):
            api = FakeApi()
            api.plug("pad-a", "dualsense", True, 78)
            hid = ps_hid.HidPads(api=api, env=env, xinput_present=lambda: present)
            hid.scan()
            self.assertEqual(api.opened, expected)

    def test_pause_closes_every_pad_and_scan_opens_them_again(self):
        self.hid.scan()
        self.assertEqual(self.api.opened, ["pad-a"])
        self.hid.pause()
        self.assertEqual(self.api.opened, [])
        self.hid.scan()
        self.assertEqual(self.api.opened, ["pad-a"])

    def test_at_most_four_pads(self):
        for n in range(6):
            self.api.plug("pad-%d" % (n + 1), "ds4", False, 64, 0x09CC)
        self.hid.scan()
        self.assertEqual(len(self.api.opened), ps_hid.MAX_PADS)

    def test_fake_report_file_is_a_pad(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "reports.txt")
            Path(path).write_text("# start\n")
            hid = ps_hid.HidPads(env={"PS3_PAD_HID_FAKE": "dualsense,bt," + path})
            hid.scan()
            with open(path, "a") as stream:
                stream.write(dualsense_bt_ext(r2=255, hat="LEFT").hex() + "\n")
            (one,) = hid.read()
            self.assertEqual(ps_hid.xinput_names(one.pressed), {"RT", "DLEFT"})

    def test_nothing_is_written_to_the_device(self):
        # the only calls the API gets are enumerate / open; a reader has reads() and close(), nothing that writes
        self.hid.scan()
        reader = self.hid.pads["pad-a"]["reader"]
        self.assertEqual({n for n in dir(reader) if not n.startswith("_")}, {"failed", "reads", "close"})


class T4Reader(unittest.TestCase):
    def setUp(self):
        self.api = FakeApi()
        self.api.plug("pad-a", "dualsense", True, 78)
        self.reader = Reader(hid=ps_hid.HidPads(api=self.api, env={}))

    def test_a_dualsense_is_xinput_slot_four_with_a_name_and_the_runtimes_button_names(self):
        slots = self.reader.step()
        self.assertIn(HID_FIRST, slots)
        self.assertEqual(self.reader.name(HID_FIRST), "DualSense (Bluetooth)")
        self.api.queue["pad-a"].append(dualsense_bt_ext(cross=1, r2=255))
        self.assertEqual(self.reader.pad_held(HID_FIRST), {"A", "RT"})

    def test_second_pad_gets_slot_five_and_a_freed_slot_is_reused_by_a_new_pad(self):
        self.api.plug("pad-b", "ds4", False, 64, 0x09CC)
        self.reader.step()
        self.assertEqual(self.reader.name(5), "DualShock 4 (USB)")
        del self.api.pads["pad-a"]
        self.reader.clock = lambda t=[1e9]: t.__setitem__(0, t[0] + 5) or t[0]          # next scan is due
        self.assertEqual(self.reader.step() & {4, 5}, {5})
        self.api.plug("pad-c", "edge", True, 78, 0x0DF2)
        self.reader.step()
        self.assertEqual(self.reader.name(4), "DualSense Edge (Bluetooth)")

    def test_pause_lets_go_and_step_finds_the_pad_again(self):
        self.reader.step()
        self.reader.pause()
        self.assertEqual(self.api.opened, [])
        self.assertNotIn(HID_FIRST, self.reader.slots())
        self.assertIn(HID_FIRST, self.reader.step())

    def test_without_a_pad_the_page_name_is_the_slots_own(self):
        self.assertEqual(pad_name(0), "XInput 1")
        self.assertEqual(pad_name(HID_FIRST), "PlayStation pad 1")
        self.assertEqual(Reader(hid=ps_hid.HidPads(api=FakeApi(), env={})).step() & set(range(4, 8)), set())


class PageRow(T4Controls, Fake):
    def __init__(self, folder, reader):
        Fake.__init__(self, manifest())
        self.folder, self.reader, self.now = folder, reader, 100.0

    def _t4c_path(self):
        return os.path.join(self.folder, "save", "controls.ini")

    def _t4c_reader(self):
        return self.reader

    def _t4c_clock(self):
        return self.now


class T4Page(unittest.TestCase):
    def test_a_dualsense_row_binds_r2_and_l1_and_writes_the_files_names(self):
        api = FakeApi()
        api.plug("pad-a", "dualsense", True, 78)
        with tempfile.TemporaryDirectory() as folder:
            page = PageRow(folder, Reader(hid=ps_hid.HidPads(api=api, env={})))
            rows = {r["id"]: r for r in page.controls()}
            row = rows[ini.PAD_ID + "4"]
            self.assertEqual(row["name"], "DualSense (Bluetooth)")
            self.assertIn(row["port"], (0, 1))                    # it plays as a player
            self.assertFalse(row["features"]["player"])          # the file can pin XInput 0..3 only
            for slot_id, report in (("L1", dualsense_bt_ext(l1=1)), ("R2", dualsense_bt_ext(r2=255, l1=0))):
                page.begin_binding(ini.PAD_ID + "4", slot_id)
                page.now += 0.5
                page.poll_binding()
                api.queue["pad-a"].append(dualsense_bt_ext())    # all let go
                page.now += 0.5
                page.poll_binding()
                api.queue["pad-a"].append(report)
                page.now += 0.5
                state = page.poll_binding()
                for _ in range(10):
                    if state["state"] in ("ready", "conflict"):
                        break
                    page.now += 0.2
                    state = page.poll_binding()
                self.assertIn(state["state"], ("ready", "conflict"), slot_id)
                page.accept_binding()
                api.queue["pad-a"].append(dualsense_bt_ext())
                page.now += 0.5
                page.poll_binding()
            text = Path(folder, "save", "controls.ini").read_text(encoding="utf-8")
            self.assertRegex(text, r"(?i)L1\s*=\s*LB")
            self.assertRegex(text, r"(?i)R2\s*=\s*RT")


class Navigation(unittest.TestCase):
    def test_launcher_navigation_reads_the_extended_report(self):
        api = FakeApi()
        api.plug("pad-a", "dualsense", True, 78)
        reader = HidPlayStationReader(ps_hid.HidPads(api=api, env={}))
        self.assertEqual(reader.read(), set())
        api.queue["pad-a"].append(dualsense_bt_ext(cross=1, hat="DOWN"))
        self.assertEqual(reader.read(), {"A", "DDOWN"})
        reader.pause()
        self.assertEqual(api.opened, [])


if __name__ == "__main__":
    unittest.main()
