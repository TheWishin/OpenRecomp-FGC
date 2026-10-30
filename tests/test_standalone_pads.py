"""Windows joystick input uses only mocked native calls, never a connected pad or a game install."""
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp import pad


class StandalonePlayStationPads(unittest.TestCase):
    def caps(self):
        caps = pad._JoyCaps()
        caps.name = "Wireless Controller"
        caps.caps = 0x10
        caps.xmin, caps.xmax, caps.ymin, caps.ymax = 0, 65535, 0, 65535
        return caps

    def state(self, **values):
        state = pad._JoyState()
        state.x, state.y, state.pov = 32767, 32767, 0xFFFF
        for key, value in values.items():
            setattr(state, key, value)
        return state

    def test_face_and_system_buttons_use_same_actions_as_installed_reader(self):
        expected = {0: "X", 1: "A", 2: "B", 3: "Y", 4: "LB", 5: "RB", 8: "BACK", 9: "START"}
        for index, source in expected.items():
            with self.subTest(button=index + 1):
                self.assertEqual(pad.joystick_ps_held(self.state(buttons=1 << index), self.caps()), {source})

    def test_pov_diagonals_and_left_stick_work_without_a_keyboard(self):
        self.assertEqual(pad.joystick_ps_held(self.state(pov=4500), self.caps()), {"DUP", "DRIGHT"})
        self.assertEqual(pad.joystick_ps_held(self.state(x=0, y=65535), self.caps()), {"DLEFT", "DDOWN"})
        self.assertEqual(pad.joystick_ps_held(self.state(), self.caps()), set())

    def test_stick_uses_reported_axis_range_and_ignores_missing_axes(self):
        caps = self.caps()
        caps.xmin, caps.xmax, caps.ymin, caps.ymax = 100, 1100, 0, 0
        self.assertEqual(pad.joystick_ps_held(self.state(x=600), caps), set())
        self.assertEqual(pad.joystick_ps_held(self.state(x=1100), caps), {"DRIGHT"})

    def test_a_controller_without_pov_does_not_hold_up(self):
        caps = self.caps()
        caps.caps = 0
        self.assertEqual(pad.joystick_ps_held(self.state(pov=0), caps), set())

    def api(self, *, name="Wireless Controller"):
        def capabilities(index, pointer, size):
            self.assertEqual(size, pad.ctypes.sizeof(pad._JoyCaps))
            caps = pointer._obj
            caps.name = name
            caps.xmax, caps.ymax = 65535, 65535
            return 0

        def position(index, pointer):
            state = pointer._obj
            self.assertEqual(state.size, pad.ctypes.sizeof(pad._JoyState))
            self.assertEqual(state.flags, 0xFF)
            state.buttons, state.x, state.y, state.pov = 2, 32767, 32767, 0xFFFF
            return 0

        return SimpleNamespace(joyGetNumDevs=mock.Mock(return_value=1),
                               joyGetDevCapsW=mock.Mock(side_effect=capabilities),
                               joyGetPosEx=mock.Mock(side_effect=position))

    def test_empty_shelf_reader_needs_only_windows_and_hotplug_is_rescanned(self):
        api = self.api()
        with mock.patch.object(pad.ctypes, "windll", SimpleNamespace(winmm=api), create=True), \
                mock.patch.object(pad.time, "monotonic", side_effect=[0, 0.5, 1.1]), \
                mock.patch.object(pad.importlib, "import_module") as imported:
            reader = pad.WinMMPlayStationReader()
            self.assertEqual(reader.read(), {"A"})
            self.assertEqual(reader.read(), {"A"})
            self.assertEqual(reader.read(), {"A"})
        self.assertEqual(api.joyGetDevCapsW.call_count, 2)
        imported.assert_not_called()

    def test_xinput_and_unrecognized_joysticks_are_not_mapped_as_playstation(self):
        api = self.api(name="Xbox Controller")
        with mock.patch.object(pad.ctypes, "windll", SimpleNamespace(winmm=api), create=True):
            reader = pad.WinMMPlayStationReader()
            self.assertEqual(reader.read(), set())
        api.joyGetPosEx.assert_not_called()

    def test_unplug_releases_buttons(self):
        api = self.api()
        with mock.patch.object(pad.ctypes, "windll", SimpleNamespace(winmm=api), create=True), \
                mock.patch.object(pad.time, "monotonic", return_value=1):
            reader = pad.WinMMPlayStationReader()
            self.assertEqual(reader.read(), {"A"})
            api.joyGetPosEx.side_effect = None
            api.joyGetPosEx.return_value = 167
            self.assertEqual(reader.read(), set())
            reader.pause()
            self.assertEqual(reader.next_scan, 2)

    def test_game_ticks_keep_device_capability_rescan_at_one_second(self):
        api = self.api()
        elapsed = [0.0]
        with mock.patch.object(pad.ctypes, "windll", SimpleNamespace(winmm=api), create=True), \
                mock.patch.object(pad.time, "monotonic", side_effect=lambda: elapsed[0]):
            pads = pad.Pads([pad.WinMMPlayStationReader()])
            for tick in range(125):
                elapsed[0] = tick * 0.016
                pads.forget()
                self.assertFalse(pads.return_requested(0.016))
        self.assertEqual(api.joyGetDevCapsW.call_count, 2)
        self.assertEqual(api.joyGetPosEx.call_count, 125)

    def test_missing_windows_api_is_inert(self):
        with mock.patch.object(pad.ctypes, "windll", SimpleNamespace(), create=True):
            reader = pad.WinMMPlayStationReader()
        self.assertEqual(reader.read(), set())


class ReturnToLauncherChord(unittest.TestCase):
    def native(self, held):
        reader = pad.XInputReader.__new__(pad.XInputReader)
        reader.read = mock.Mock(return_value=held)
        reader.return_devices = lambda: {0} if {"BACK", "START"} <= reader.read() else set()
        return reader

    def test_chord_requires_two_seconds_and_fires_once_until_release(self):
        reader = self.native({"BACK", "START"})
        pads = pad.Pads([reader])
        self.assertFalse(pads.return_requested(1.0))
        self.assertFalse(pads.return_requested(0.9))
        self.assertTrue(pads.return_requested(0.1))
        self.assertFalse(pads.return_requested(2.0))
        self.assertEqual(pads.down["confirm"], float("inf"))
        reader.read.return_value = {"START"}
        self.assertFalse(pads.return_requested(0.1))
        reader.read.return_value = {"BACK", "START"}
        self.assertTrue(pads.return_requested(2.0))

    def test_two_controllers_cannot_combine_half_a_chord(self):
        pads = pad.Pads([self.native({"BACK"}), self.native({"START"})])
        self.assertFalse(pads.return_requested(3.0))

    def test_xinput_ports_cannot_combine_half_a_chord(self):
        def get(index, pointer):
            pointer._obj.pad.buttons = 0x20 if index == 0 else 0x10
            return 0 if index < 2 else 1167

        reader = pad.XInputReader.__new__(pad.XInputReader)
        reader.get = get
        self.assertEqual(reader.read(), {"BACK", "START"})
        self.assertFalse(pad.Pads([reader]).return_requested(3.0))

    def test_native_playstation_return_uses_both_buttons_on_one_device(self):
        reader = pad.WinMMPlayStationReader.__new__(pad.WinMMPlayStationReader)
        reader._devices = mock.Mock(return_value={0: {"BACK"}, 1: {"START"}})
        self.assertEqual(reader.return_devices(), set())
        reader._devices.return_value = {1: {"BACK", "START"}}
        self.assertEqual(reader.return_devices(), {1})

    def test_chord_hold_cannot_move_between_readers(self):
        first = self.native({"BACK", "START"})
        second = self.native(set())
        pads = pad.Pads([first, second])
        self.assertFalse(pads.return_requested(1.5))
        first.read.return_value = set()
        second.read.return_value = {"BACK", "START"}
        self.assertFalse(pads.return_requested(0.6))
        self.assertTrue(pads.return_requested(1.4))

    def test_chord_hold_cannot_move_between_xinput_ports(self):
        active_port = [0]

        def get(index, pointer):
            pointer._obj.pad.buttons = 0x30 if index == active_port[0] else 0
            return 0

        reader = pad.XInputReader.__new__(pad.XInputReader)
        reader.get = get
        pads = pad.Pads([reader])
        self.assertFalse(pads.return_requested(1.5))
        active_port[0] = 1
        self.assertFalse(pads.return_requested(0.6))
        self.assertTrue(pads.return_requested(1.4))

    def test_chord_hold_cannot_move_between_windows_joysticks(self):
        reader = pad.WinMMPlayStationReader.__new__(pad.WinMMPlayStationReader)
        reader._devices = mock.Mock(return_value={0: {"BACK", "START"}})
        pads = pad.Pads([reader])
        self.assertFalse(pads.return_requested(1.5))
        reader._devices.return_value = {1: {"BACK", "START"}}
        self.assertFalse(pads.return_requested(0.6))
        self.assertTrue(pads.return_requested(1.4))

    def test_game_return_never_polls_external_hid_or_generates_navigation_actions(self):
        external = pad.PlayStationReader.__new__(pad.PlayStationReader)
        external.read = mock.Mock(return_value={"BACK", "START"})
        pads = pad.Pads([external, self.native({"A"})])
        pads.poll = mock.Mock()
        self.assertFalse(pads.return_requested(3.0))
        external.read.assert_not_called()
        pads.poll.assert_not_called()

    def test_new_game_resets_partial_hold(self):
        pads = pad.Pads([self.native({"BACK", "START"})])
        self.assertFalse(pads.return_requested(1.5))
        pads.reset_return()
        self.assertFalse(pads.return_requested(0.6))


if __name__ == "__main__":
    unittest.main()
