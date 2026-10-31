"""Side-by-side controller edits with an inert installed editor contract."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from test_controls_adapter import Capture, Device, Editor, Poller, PortMap, Ref, Slot, Subject


class FileEditor(Editor):
    loaded = []
    fail_save = False

    @classmethod
    def load(cls, path):
        editor = cls()
        editor.path = path
        with open(path, encoding="utf-8") as stream:
            editor.document = json.load(stream)
        editor.binds = {(int(port), source): mask
                        for port, source, mask in editor.document["bindings"]}
        cls.loaded.append(editor)
        return editor

    def save(self):
        if self.fail_save:
            raise RuntimeError("save refused")
        self.document["bindings"] = [[port, source, mask]
                                     for (port, source), mask in self.binds.items()]
        with open(self.path, "w", encoding="utf-8") as stream:
            json.dump(self.document, stream)


class CoexistControls(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.folder.cleanup)
        self.source = Path(self.folder.name) / "old-controls.json"
        self.private = Path(self.folder.name) / "new-launcher" / "controls.json"
        self.original = b'{"bindings": [[0, "A", 1]], "future": {"keep": true}}\n'
        self.source.write_bytes(self.original)
        FileEditor.loaded = []
        FileEditor.fail_save = False
        self.bus = SimpleNamespace(devices=[Device("xinput", "pad", "Pad", 0, 0, 0, frozenset())],
                                   edges=[], paused=0)
        ce = SimpleNamespace(ControlsEditor=FileEditor, DeviceRef=Ref, SCOPE_PORT="port",
                             SLOTS=[Slot("1", 1), Slot("2", 2)], mask_text=str,
                             controls_path=lambda out, env: env["PS3_CONTROLS"])
        self.adapter = Subject((ce, SimpleNamespace(DevicePoller=Poller, Capture=Capture),
                                SimpleNamespace(PortMap=PortMap),
                                SimpleNamespace(default_sources=lambda: [self.bus])))
        self.adapter.s = SimpleNamespace(out_dir="unused", controls_write_path=str(self.private),
            env_overrides=lambda: {"PS3_CONTROLS": str(self.private if self.private.exists() else self.source)})

    def capture(self):
        self.adapter.begin_binding("pad", "2")
        self.adapter._controls_session["capture"].result = ("ok", "X")
        self.assertEqual(self.adapter.poll_binding()["state"], "ready")

    def test_open_and_cancel_read_existing_bindings_without_copying(self):
        self.adapter.poll_binding()
        self.assertEqual(self.adapter.controls()[0]["slots"][0]["value"], "A")
        self.capture()
        self.adapter.cancel_binding()
        self.adapter.controls_close()
        self.assertFalse(self.private.parent.exists())
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_accepted_binding_saves_private_controls_and_preserves_unknown_fields(self):
        self.capture()
        self.adapter.accept_binding()
        self.assertEqual(self.source.read_bytes(), self.original)
        document = json.loads(self.private.read_text(encoding="utf-8"))
        self.assertEqual(document["future"], {"keep": True})
        self.assertIn([0, "A", 1], document["bindings"])
        self.assertIn([0, "X", 2], document["bindings"])
        self.assertEqual(self.adapter.s.env_overrides()["PS3_CONTROLS"], str(self.private))
        self.adapter.controls_close()
        self.adapter.poll_binding()
        self.assertEqual(self.adapter._controls_session["editor"].path, str(self.private))
        self.assertEqual(self.adapter.controls()[0]["slots"][1]["value"], "X")

    def test_failed_private_save_reloads_original_and_drops_pending_edit(self):
        self.capture()
        FileEditor.fail_save = True
        with self.assertRaisesRegex(RuntimeError, "save refused"):
            self.adapter.accept_binding()
        session = self.adapter._controls_session
        self.assertEqual(session["editor"].path, str(self.source))
        self.assertNotIn((0, "X"), session["editor"].binds)
        self.assertIsNone(session["pending"])
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertFalse(self.private.exists())

    def test_installed_controls_import_disables_bytecode_and_restores_policy(self):
        name = "_coexist_controls_fixture"
        path = str(Path(self.folder.name) / "controls_edit.py")
        for fails in (False, True):
            with self.subTest(fails=fails), mock.patch.dict(sys.modules), mock.patch.object(sys, "dont_write_bytecode", False):
                sys.modules.pop(name, None)
                module = SimpleNamespace(__file__=path)

                def execute(loaded):
                    self.assertIs(loaded, module)
                    self.assertTrue(sys.dont_write_bytecode)
                    if fails:
                        raise RuntimeError("fake import failed")

                spec = SimpleNamespace(loader=SimpleNamespace(exec_module=execute))
                with mock.patch("openrecomp.adapters.t5_controls.importlib.util.spec_from_file_location", return_value=spec):
                    with mock.patch("openrecomp.adapters.t5_controls.importlib.util.module_from_spec", return_value=module):
                        if fails:
                            with self.assertRaisesRegex(RuntimeError, "fake import failed"):
                                self.adapter._controls_import(name, path)
                            self.assertNotIn(name, sys.modules)
                        else:
                            self.assertIs(self.adapter._controls_import(name, path), module)
                self.assertFalse(sys.dont_write_bytecode)


if __name__ == "__main__":
    unittest.main()
