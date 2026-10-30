"""Pad editing against the installed module contract, using no installed code or devices."""
import unittest
import os
from collections import namedtuple
from types import SimpleNamespace
from unittest import mock

from openrecomp.adapters.base import Adapter
from openrecomp.adapters.t5_controls import Controls


Device = namedtuple("Device", "kind key name vid pid slot pressed")
Ref = namedtuple("Ref", "kind port vid pid")
Slot = namedtuple("Slot", "key mask")


class Editor:
    loaded = []
    fail_save = False

    @classmethod
    def load(cls, path):
        editor = cls()
        editor.path = path
        cls.loaded.append(editor)
        return editor

    def __init__(self):
        self.binds = {(0, "A"): 1, (0, "B"): 2, (1, "A"): 2}
        self.calls = []

    def controls(self):
        return self

    def sources(self, dev, key):
        return [source for (port, source), mask in self.binds.items() if port == dev.port and mask == int(key)]

    def table(self, dev):
        return SimpleNamespace(mask_of=lambda source: self.binds.get((dev.port, source), 0))

    def bind(self, dev, scope, key, sources):
        self.calls.append((dev, scope, key, sources))
        self.binds[(dev.port, sources[0])] = int(key)

    def save(self):
        if self.fail_save:
            raise RuntimeError("changed on disk")
        self.calls.append("saved")


class PortMap:
    def __init__(self, controls):
        self.port = {}

    def update(self, devices, controls):
        self.port = {dev.key: dev.slot for dev in devices if dev.slot >= 0}


class Poller:
    def __init__(self, sources, foreground, controls):
        self.bus = sources[0]
        self.foreground = foreground
        self.devices = ()
        self.held = {}
        self.edges = []

    def step(self, now):
        if self.foreground():
            self.devices = tuple(self.bus.devices)
            self.held = {dev.key: dev.pressed for dev in self.devices}
            self.edges += self.bus.edges
            self.bus.edges = []
        else:
            self.bus.paused += 1

    def drain(self):
        edges, self.edges = self.edges, []
        return edges


class Capture:
    def __init__(self, started, timeout_s, held):
        self.held = held
        self.timeout_s = timeout_s
        self.result = None
        self.edges = []

    def update(self, now, edges, held):
        self.edges += edges
        return self.result


class Subject(Controls, Adapter):
    def __init__(self, api):
        super().__init__({"id": "test", "short": "Test"})
        self._controls_modules = api
        self.busy = False
        self.root = "fake-root"
        self.s = SimpleNamespace(out_dir="fake-output", env_overrides=lambda: {"PS3_CONTROLS": "custom-controls"})

    def running(self):
        return self.busy


class PadBindings(unittest.TestCase):
    def setUp(self):
        Editor.loaded = []
        Editor.fail_save = False
        self.pad = Device("xinput", "pad-one", "Pad One", 0, 0, 0, frozenset({"A"}))
        self.second = Device("dinput", "pad-two", "Pad Two", 10, 20, 1, frozenset())
        self.bus = SimpleNamespace(devices=[self.pad, self.second], edges=[], paused=0)
        ce = SimpleNamespace(ControlsEditor=Editor, DeviceRef=Ref, SCOPE_PORT="port",
                             SLOTS=[Slot("1", 1), Slot("2", 2)], mask_text=str,
                             controls_path=mock.Mock(return_value="custom-controls"))
        self.adapter = Subject((ce, SimpleNamespace(DevicePoller=Poller, Capture=Capture),
                                SimpleNamespace(PortMap=PortMap),
                                SimpleNamespace(default_sources=lambda: [self.bus])))

    def capture(self, source, pad="pad-one", slot="2"):
        self.adapter.begin_binding(pad, slot)
        self.adapter._controls_session["capture"].result = ("ok", source)
        return self.adapter.poll_binding()

    def test_rows_use_runtime_editor_and_controls_path_with_settings_environment(self):
        self.assertEqual(self.adapter.controls(), [])
        self.assertEqual(Editor.loaded, [])
        self.adapter.poll_binding()
        rows = self.adapter.controls()
        self.adapter._controls_modules[0].controls_path.assert_called_once_with(
            "fake-output", {"PS3_CONTROLS": "custom-controls"})
        self.assertEqual(Editor.loaded[0].path, "custom-controls")
        self.assertEqual([row["port"] for row in rows], [0, 1])
        self.assertEqual(rows[0]["slots"][0]["value"], "A")
        self.assertEqual(rows[1]["slots"][0]["value"], "@controls.unbound")
        self.assertEqual(rows[0]["slots"][0]["label"], "@controls.slot.1")
        self.assertEqual(Editor.loaded[0].calls, [])
        self.adapter.controls()
        self.assertEqual(len(Editor.loaded), 1)

    def test_conflict_is_shown_before_explicit_accept_and_saved_for_selected_port(self):
        result = self.capture("A")
        self.assertEqual(result, dict(state="conflict", source="A", conflicts=["@controls.slot.1"]))
        editor = Editor.loaded[0]
        self.assertEqual(editor.calls, [])
        self.adapter.accept_binding()
        self.assertEqual(editor.calls, [(Ref("xinput", 0, 0, 0), "port", "2", ["A"]), "saved"])
        self.assertEqual(editor.binds[(1, "A")], 2)
        self.assertEqual(self.adapter.poll_binding()["state"], "done")

    def test_unused_source_is_ready_and_cancel_never_writes(self):
        self.assertEqual(self.capture("X")["state"], "ready")
        self.adapter.cancel_binding()
        self.assertEqual(Editor.loaded[0].calls, [])
        with self.assertRaisesRegex(RuntimeError, "controls.disconnected"):
            self.adapter.accept_binding()

    def test_opening_confirm_is_held_and_edges_from_other_pad_are_filtered(self):
        self.adapter.begin_binding("pad-one", "2")
        capture = self.adapter._controls_session["capture"]
        self.assertEqual(capture.held, frozenset({"A"}))
        self.assertEqual(capture.timeout_s, 8.0)
        self.bus.edges = [SimpleNamespace(key="pad-two", source="X"), SimpleNamespace(key="pad-one", source="Y")]
        self.adapter.poll_binding()
        self.assertEqual([edge.source for edge in capture.edges], ["Y"])

    def test_disconnection_or_port_change_invalidates_capture_and_pending_accept(self):
        for devices in ([self.second], [self.pad._replace(slot=1), self.second]):
            self.bus.devices = [self.pad, self.second]
            self.capture("A")
            self.bus.devices = devices
            self.assertEqual(self.adapter.poll_binding()["state"], "disconnected")
            with self.assertRaises(RuntimeError):
                self.adapter.accept_binding()
            self.assertEqual(Editor.loaded[0].calls, [])

    def test_game_running_blocks_begin_and_save(self):
        self.adapter.busy = True
        with self.assertRaisesRegex(RuntimeError, "controls.running"):
            self.adapter.begin_binding("pad-one", "1")
        self.adapter.busy = False
        self.capture("X")
        self.adapter.busy = True
        with self.assertRaisesRegex(RuntimeError, "controls.running"):
            self.adapter.accept_binding()
        self.assertEqual(Editor.loaded[0].calls, [])

    def test_multiple_presses_retry_and_timeout_never_writes(self):
        self.adapter.begin_binding("pad-one", "1")
        session = self.adapter._controls_session
        session["capture"].result = ("multi", ["A", "B"])
        self.assertEqual(self.adapter.poll_binding()["state"], "multi")
        self.assertIsNotNone(session["capture"])
        session["capture"].result = ("timeout", None)
        self.assertEqual(self.adapter.poll_binding()["state"], "timeout")
        self.assertIsNone(session["pending"])
        self.assertEqual(Editor.loaded[0].calls, [])

    def test_repeated_multiple_presses_cannot_extend_total_capture_timeout(self):
        with mock.patch("openrecomp.adapters.t5_controls.time.monotonic", return_value=100.0):
            self.adapter.begin_binding("pad-one", "1")
        session = self.adapter._controls_session
        session["capture"].result = ("multi", ["A", "B"])
        with mock.patch("openrecomp.adapters.t5_controls.time.monotonic", return_value=107.0):
            self.assertEqual(self.adapter.poll_binding()["state"], "multi")
        self.assertEqual(session["capture"].timeout_s, 1.0)
        with mock.patch("openrecomp.adapters.t5_controls.time.monotonic", return_value=108.1):
            self.assertEqual(self.adapter.poll_binding()["state"], "timeout")
        self.assertEqual(Editor.loaded[0].calls, [])

    def test_inactive_poll_pauses_and_close_releases_session(self):
        self.adapter.poll_binding()
        self.adapter.poll_binding(active=False)
        self.assertEqual(self.bus.paused, 1)
        self.adapter.controls_close()
        self.assertEqual(self.bus.paused, 2)
        self.assertIsNone(self.adapter._controls_session)

    def test_unassigned_device_is_visible_but_not_editable(self):
        self.bus.devices = [self.pad._replace(slot=-1)]
        self.adapter.poll_binding()
        row = self.adapter.controls()[0]
        self.assertTrue(row["disabled"])
        with self.assertRaisesRegex(RuntimeError, "controls.disconnected"):
            self.adapter.begin_binding("pad-one", "1")

    def test_failed_save_reloads_editor_and_discards_pending_binding(self):
        self.capture("X")
        Editor.fail_save = True
        with self.assertRaisesRegex(RuntimeError, "changed on disk"):
            self.adapter.accept_binding()
        self.assertEqual(len(Editor.loaded), 2)
        self.assertNotIn((0, "X"), self.adapter._controls_session["editor"].binds)
        self.assertIsNone(self.adapter._controls_session["pending"])

    def test_inactive_view_and_poll_do_not_create_or_reopen_device_reader(self):
        with mock.patch.object(self.adapter._controls_modules[3], "default_sources") as sources:
            self.assertEqual(self.adapter.controls(), [])
            self.assertEqual(self.adapter.poll_binding(active=False), dict(state="idle"))
            sources.assert_not_called()
        self.adapter.poll_binding()
        self.adapter.controls_close()
        with mock.patch.object(self.adapter._controls_modules[3], "default_sources") as sources:
            self.assertEqual(self.adapter.controls(), [])
            self.assertEqual(self.adapter.poll_binding(active=False), dict(state="idle"))
            sources.assert_not_called()

    def test_install_without_controls_modules_hides_capability(self):
        adapter = Subject(None)
        self.assertFalse(adapter.controls_supported())
        self.assertEqual(adapter.controls(), [])
        del adapter._controls_modules
        with mock.patch("openrecomp.adapters.t5_controls.os.path.isfile", return_value=False):
            with mock.patch("openrecomp.adapters.t5_controls.importlib.util.spec_from_file_location") as imported:
                self.assertFalse(adapter.controls_supported())
                imported.assert_not_called()

    def runtime_modules(self):
        ce, ui, pm, pn = self.adapter._controls_modules
        root = self.adapter.root
        modules = {"t5lobby": SimpleNamespace(), "t5lobby.padmap": pm,
                   "t5lobby.padnav": pn, "controls_edit": ce, "controls_ui": ui}
        for name, module in modules.items():
            module.__file__ = os.path.join(root, "lobby", *name.split("."), "__init__.py") if name == "t5lobby" else (
                os.path.join(root, "lobby", "t5lobby", name.split(".")[-1] + ".py") if "." in name else
                os.path.join(root, "launcher", name + ".py"))
        return modules

    def test_other_install_cached_modules_are_rejected_before_importing_dependencies(self):
        modules = self.runtime_modules()
        modules["controls_edit"].__file__ = os.path.join("other-install", "launcher", "controls_edit.py")
        del self.adapter._controls_modules
        with mock.patch.dict("sys.modules", modules):
            with mock.patch("openrecomp.adapters.t5_controls.os.path.isfile", return_value=True):
                with mock.patch("openrecomp.adapters.t5_controls.importlib.util.spec_from_file_location") as imported:
                    self.assertFalse(self.adapter.controls_supported())
                    imported.assert_not_called()

    def test_incompatible_runtime_api_is_hidden_and_compatible_api_is_supported(self):
        modules = self.runtime_modules()
        del self.adapter._controls_modules
        with mock.patch.dict("sys.modules", modules):
            with mock.patch("openrecomp.adapters.t5_controls.os.path.isfile", return_value=True):
                self.assertTrue(self.adapter.controls_supported())
        del self.adapter._controls_modules
        modules["controls_ui"] = SimpleNamespace(__file__=modules["controls_ui"].__file__)
        with mock.patch.dict("sys.modules", modules):
            with mock.patch("openrecomp.adapters.t5_controls.os.path.isfile", return_value=True):
                self.assertFalse(self.adapter.controls_supported())

    def test_verified_import_loads_the_selected_file_without_search_path_resolution(self):
        path = os.path.join(self.adapter.root, "launcher", "controls_edit.py")
        module = SimpleNamespace(__file__=path)
        loader = mock.Mock()
        spec = SimpleNamespace(loader=loader)
        with mock.patch.dict("sys.modules"):
            import sys
            sys.modules.pop("controls_edit", None)
            with mock.patch("openrecomp.adapters.t5_controls.importlib.util.spec_from_file_location", return_value=spec) as opened:
                with mock.patch("openrecomp.adapters.t5_controls.importlib.util.module_from_spec", return_value=module):
                    self.assertIs(self.adapter._controls_import("controls_edit", path), module)
        opened.assert_called_once_with("controls_edit", os.path.realpath(path))
        loader.exec_module.assert_called_once_with(module)


if __name__ == "__main__":
    unittest.main()
