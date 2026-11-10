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
        editor.disk_bytes = Path(path).read_bytes()
        editor.document = json.loads(editor.disk_bytes.decode("utf-8"))
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
        self.disk_bytes = Path(self.path).read_bytes()


def time_far():
    import time
    return time.monotonic() + 100


class CoexistControls(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.folder.cleanup)
        self.source = Path(self.folder.name) / "controls.ini"        # the file T5DR's own launcher edits
        self.private = Path(self.folder.name) / "new-launcher" / "controls.json"      # OpenRecomp's old own copy
        self.original = b'{"bindings": [[0, "A", 1]], "future": {"keep": true}}\n'
        self.source.write_bytes(self.original)
        FileEditor.loaded = []
        FileEditor.fail_save = False
        self.bus = SimpleNamespace(devices=[Device("xinput", "pad", "Pad", 0, 0, 0, frozenset())],
                                   edges=[], paused=0)
        ce = SimpleNamespace(ControlsEditor=FileEditor, DeviceRef=Ref, SCOPE_PORT="port",
                             SLOTS=[Slot("1", 1), Slot("2", 2)], mask_text=str,
                             controls_path=lambda out, env: str(self.source))
        self.adapter = Subject((ce, SimpleNamespace(DevicePoller=Poller, Capture=Capture),
                                SimpleNamespace(PortMap=PortMap),
                                SimpleNamespace(default_sources=lambda: [self.bus])))
        self.adapter.s = SimpleNamespace(out_dir="unused", legacy_controls_paths=(str(self.private),),
                                         env_overrides=lambda: {})

    def capture(self):
        self.adapter.begin_binding("pad", "2")
        self.adapter._controls_session["capture"].result = ("ok", "X")
        self.assertEqual(self.adapter.poll_binding()["state"], "ready")

    def test_open_and_cancel_read_existing_bindings_without_writing(self):
        self.adapter.poll_binding()
        self.assertEqual(self.adapter.controls()[0]["slots"][0]["value"], "A")
        self.capture()
        self.adapter.cancel_binding()
        self.adapter.controls_close()
        self.assertFalse(self.private.parent.exists())
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_accepted_binding_is_saved_in_the_shared_file_and_keeps_unknown_fields(self):
        self.capture()
        self.adapter.accept_binding()
        document = json.loads(self.source.read_text(encoding="utf-8"))
        self.assertEqual(document["future"], {"keep": True})
        self.assertIn([0, "A", 1], document["bindings"])
        self.assertIn([0, "X", 2], document["bindings"])
        self.assertFalse(self.private.exists())
        self.assertNotIn("PS3_CONTROLS", self.adapter.s.env_overrides())
        self.adapter.controls_close()
        self.adapter.poll_binding()
        self.assertEqual(self.adapter._controls_session["editor"].path, str(self.source))
        self.assertEqual(self.adapter.controls()[0]["slots"][1]["value"], "X")

    def test_failed_save_reloads_the_shared_file_and_drops_the_pending_edit(self):
        self.capture()
        FileEditor.fail_save = True
        with self.assertRaisesRegex(RuntimeError, "save refused"):
            self.adapter.accept_binding()
        session = self.adapter._controls_session
        self.assertEqual(session["editor"].path, str(self.source))
        self.assertNotIn((0, "X"), session["editor"].binds)
        self.assertIsNone(session["pending"])
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_old_private_copy_is_moved_into_the_shared_file_with_a_backup(self):
        mine = b'{"bindings": [[0, "A", 1], [0, "Q", 2]]}\n'
        self.private.parent.mkdir()
        self.private.write_bytes(mine)
        os.utime(self.private, (self.source.stat().st_mtime + 50,) * 2)       # written after the shared file
        self.adapter.poll_binding()
        self.assertEqual(self.source.read_bytes(), mine)
        self.assertFalse(self.private.exists())
        self.assertEqual(Path(str(self.private) + ".migrated").read_bytes(), mine)
        backups = list(self.private.parent.glob("controls-before-migration-*.ini"))
        self.assertEqual([b.read_bytes() for b in backups], [self.original])
        self.assertEqual(self.adapter.controls()[0]["slots"][1]["value"], "Q")

    def test_shared_file_written_later_wins_and_the_private_copy_is_kept_as_a_backup(self):
        mine = b'{"bindings": [[0, "Q", 2]]}\n'
        self.private.parent.mkdir()
        self.private.write_bytes(mine)
        os.utime(self.private, (self.source.stat().st_mtime - 50,) * 2)
        self.adapter.poll_binding()
        self.assertEqual(self.source.read_bytes(), self.original)
        backups = list(self.private.parent.glob("controls-openrecomp-*.ini"))
        self.assertEqual([b.read_bytes() for b in backups], [mine])
        self.assertFalse(self.private.exists())

    def test_old_private_copy_becomes_the_file_when_the_shared_one_is_missing(self):
        mine = b'{"bindings": [[0, "Q", 2]]}\n'
        self.source.unlink()
        self.private.parent.mkdir()
        self.private.write_bytes(mine)
        self.adapter.poll_binding()
        self.assertEqual(self.source.read_bytes(), mine)
        self.assertEqual(Path(str(self.private) + ".migrated").read_bytes(), mine)

    def test_a_change_made_by_the_other_launcher_is_shown_without_reopening(self):
        self.adapter.poll_binding()
        self.assertEqual(self.adapter.controls()[0]["slots"][0]["value"], "A")
        self.source.write_bytes(b'{"bindings": [[0, "Z", 1]]}\n')
        with mock.patch("openrecomp.adapters.t5_controls.time.monotonic", return_value=time_far()):
            self.adapter.poll_binding()
        self.assertEqual(self.adapter.controls()[0]["slots"][0]["value"], "Z")

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
