"""Controller persistence failures use synthetic bindings, never an installed editor."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from test_controls_adapter import Capture, Device, Poller, PortMap, Ref, Slot, Subject
from test_t5_coexist_controls import FileEditor


class PrivateControlsPublication(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory(dir=Path(__file__).parent))
        self.folder = Path(folder)
        self.source = self.folder / "old-controls.json"
        self.private = self.folder / "private" / "controls.json"
        self.private.parent.mkdir()
        self.original = b'{"bindings": [[0, "A", 1]], "future": {"keep": true}}\n'
        self.source.write_bytes(self.original)
        self.private.write_bytes(self.original)
        self.bus = SimpleNamespace(devices=[Device("xinput", "pad", "Pad", 0, 0, 0, frozenset())],
                                   edges=[], paused=0)
        FileEditor.fail_save = False
        ce = SimpleNamespace(ControlsEditor=FileEditor, DeviceRef=Ref, SCOPE_PORT="port",
                             SLOTS=[Slot("1", 1), Slot("2", 2)], mask_text=str,
                             controls_path=lambda out, env: str(self.private))
        self.adapter = Subject((ce, SimpleNamespace(DevicePoller=Poller, Capture=Capture),
                                SimpleNamespace(PortMap=PortMap),
                                SimpleNamespace(default_sources=lambda: [self.bus])))
        self.adapter.s.controls_write_path = str(self.private)
        self.adapter.begin_binding("pad", "2")
        self.adapter._controls_session["capture"].result = ("ok", "X")
        self.assertEqual(self.adapter.poll_binding()["state"], "ready")

    def assert_preserved(self):
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(self.private.read_bytes(), self.original)
        self.assertEqual(list(self.private.parent.iterdir()), [self.private])
        session = self.adapter._controls_session
        self.assertIsNone(session["pending"])
        self.assertEqual(session["editor"].path, str(self.private))
        self.assertNotIn((0, "X"), session["editor"].binds)

    def test_partial_editor_write_preserves_previous_private_bindings(self):
        def partial_save(editor):
            Path(editor.path).write_bytes(b'{"bindings":')
            raise OSError("synthetic full disk")

        with mock.patch.object(FileEditor, "save", partial_save):
            with self.assertRaisesRegex(OSError, "synthetic full disk"):
                self.adapter.accept_binding()
        self.assert_preserved()

    def test_publish_failure_preserves_previous_private_bindings(self):
        with mock.patch("openrecomp.adapters.t5_controls.os.replace", side_effect=OSError("synthetic publish failure")):
            with self.assertRaisesRegex(OSError, "synthetic publish failure"):
                self.adapter.accept_binding()
        self.assert_preserved()

    def test_editor_writes_sibling_then_keeps_final_path_for_next_edit(self):
        written = []
        save = FileEditor.save

        def record_save(editor):
            written.append(Path(editor.path))
            self.assertEqual(self.private.read_bytes(), self.original)
            save(editor)

        with mock.patch.object(FileEditor, "save", record_save):
            self.adapter.accept_binding()
        self.assertEqual(len(written), 1)
        self.assertNotEqual(written[0], self.private)
        self.assertEqual(written[0].parent, self.private.parent)
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(list(self.private.parent.iterdir()), [self.private])
        document = json.loads(self.private.read_text(encoding="utf-8"))
        self.assertEqual(document["future"], {"keep": True})
        self.assertIn([0, "X", 2], document["bindings"])
        self.assertEqual(self.adapter._controls_session["editor"].path, str(self.private))


if __name__ == "__main__":
    unittest.main()
