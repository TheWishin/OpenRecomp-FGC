"""T5DR Pad bindings: L1 / R2 (second and later edits) and the one controls.ini shared with T5DR's own launcher."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from openrecomp import controls_file
from openrecomp.adapters.base import Adapter
from openrecomp.adapters.t5_controls import Controls
from test_controls_adapter import Capture, Device, Poller, PortMap, Ref, Slot, Subject

REAL_ROOT = os.environ.get("T5DR_ROOT") or "C:/T5DROnline"


class FileChanged(Exception):
    pass


MASK = {"1": 1, "2": 2, "L1": 4, "R2": 8}


class IniEditor:
    """The installed editor's save contract: it refuses to overwrite a file that is not what it read (FileChanged)."""

    @classmethod
    def load(cls, path):
        editor = cls()
        editor.path = path
        try:
            editor.disk_bytes = Path(path).read_bytes()
        except FileNotFoundError:
            editor.disk_bytes = None
        text = (editor.disk_bytes or b"").decode("latin-1")
        editor.binds = {}
        for line in text.splitlines():
            if "=" in line:
                mask, source = (x.strip() for x in line.split("="))
                editor.binds[(0, source)] = int(mask)
        return editor

    def controls(self):
        return self

    def sources(self, dev, key):
        return [s for (_port, s), m in self.binds.items() if m == MASK[key]]

    def table(self, dev):
        return SimpleNamespace(mask_of=lambda source: self.binds.get((0, source), 0))

    def bind(self, dev, scope, key, sources):
        for source in sources:
            self.binds[(0, source)] = MASK[key]

    def save(self):
        now = Path(self.path).read_bytes() if os.path.exists(self.path) else None
        if now != self.disk_bytes:
            raise FileChanged(self.path)
        rows = sorted(self.binds.items(), key=lambda item: item[1])
        data = "".join(f"{m} = {s}\n" for (_p, s), m in rows).encode("latin-1")
        Path(self.path).write_bytes(data)
        self.disk_bytes = data


class SharedFile(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.folder.cleanup)
        self.ini = Path(self.folder.name) / "controls.ini"
        self.ini.write_bytes(b"1 = A\n")
        self.bus = SimpleNamespace(devices=[Device("xinput", "pad", "Pad", 0, 0, 0, frozenset())], edges=[], paused=0)
        ce = SimpleNamespace(ControlsEditor=IniEditor, DeviceRef=Ref, SCOPE_PORT="port", FileChanged=FileChanged,
                             SLOTS=[Slot("1", 1), Slot("2", 2), Slot("L1", 4), Slot("R2", 8)], mask_text=str,
                             controls_path=lambda out, env: str(self.ini))
        self.adapter = Subject((ce, SimpleNamespace(DevicePoller=Poller, Capture=Capture),
                                SimpleNamespace(PortMap=PortMap), SimpleNamespace(default_sources=lambda: [self.bus])))
        self.adapter.s = SimpleNamespace(out_dir="x", env_overrides=lambda: {})

    def bind(self, slot, source):
        self.adapter.begin_binding("pad", slot)
        self.adapter._controls_session["capture"].result = ("ok", source)
        self.assertEqual(self.adapter.poll_binding()["state"], "ready")
        self.adapter.accept_binding()

    def test_l1_then_r2_in_a_row_both_save(self):
        # the report: the first binding saved, the next one raised (the temporary file the save went to was empty)
        self.bind("L1", "LB")
        self.bind("R2", "RT")
        text = self.ini.read_text()
        self.assertIn("4 = LB", text)
        self.assertIn("8 = RT", text)
        self.assertEqual(sorted(p.name for p in self.ini.parent.iterdir()), ["controls.ini"])

    def test_second_binding_of_a_session_saves_and_keeps_the_first(self):
        self.bind("2", "X")
        self.bind("L1", "LB")                                         # 0.1.6: "changed on disk", nothing saved
        self.assertEqual(self.ini.read_text().splitlines(), ["1 = A", "2 = X", "4 = LB"])
        self.adapter.controls_close()
        self.adapter.poll_binding()                                   # a new page reads the same file
        slots = {slot["id"]: slot["value"] for slot in self.adapter.controls()[0]["slots"]}
        self.assertEqual((slots["2"], slots["L1"]), ("X", "LB"))

    def test_other_launcher_changed_the_file_since_we_read_it(self):
        self.adapter.poll_binding()
        self.adapter.begin_binding("pad", "R2")
        self.ini.write_bytes(b"1 = A\n2 = B\n")                       # T5DR's launcher saved meanwhile
        self.adapter._controls_session["capture"].result = ("ok", "RT")
        self.adapter.poll_binding()
        self.adapter.accept_binding()
        text = self.ini.read_text()
        self.assertIn("2 = B", text)                                    # its binding is kept
        self.assertIn("8 = RT", text)                                   # ours is added on top

    def test_locked_file_is_retried_then_saved(self):
        calls = []
        save = IniEditor.save

        def flaky(editor):
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError(13, "in use")
            save(editor)

        with mock.patch.object(IniEditor, "save", flaky), mock.patch.object(controls_file.time, "sleep"):
            self.bind("L1", "LB")
        self.assertEqual(len(calls), 3)
        self.assertIn("4 = LB", self.ini.read_text())

    def test_file_held_for_good_fails_clearly_and_leaves_the_file_alone(self):
        def held(editor):
            raise PermissionError(13, "in use")

        self.adapter.begin_binding("pad", "L1")
        self.adapter._controls_session["capture"].result = ("ok", "LB")
        self.adapter.poll_binding()
        ticks = iter(range(0, 1000, 3))
        with mock.patch.object(IniEditor, "save", held), mock.patch.object(controls_file.time, "sleep"), \
                mock.patch.object(controls_file.time, "monotonic", lambda: next(ticks)):
            with self.assertRaises(PermissionError):
                self.adapter.accept_binding()
        self.assertEqual(self.ini.read_bytes(), b"1 = A\n")
        self.assertIsNone(self.adapter._controls_session["pending"])


class AtomicWrite(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.folder.cleanup)
        self.path = os.path.join(self.folder.name, "sub", "controls.ini")

    def test_creates_folder_and_leaves_no_temporary_file(self):
        controls_file.atomic_write(self.path, b"x")
        self.assertEqual(os.listdir(os.path.dirname(self.path)), ["controls.ini"])

    def test_retries_a_locked_replace(self):
        real = os.replace
        seen = []

        def replace(a, b):
            seen.append(1)
            if len(seen) < 3:
                raise PermissionError(13, "in use")
            real(a, b)

        with mock.patch.object(controls_file.os, "replace", replace), mock.patch.object(controls_file.time, "sleep"):
            controls_file.atomic_write(self.path, b"x")
        self.assertEqual(len(seen), 3)
        self.assertEqual(Path(self.path).read_bytes(), b"x")

    def test_writes_in_place_when_the_replace_stays_refused(self):
        os.makedirs(os.path.dirname(self.path))
        Path(self.path).write_bytes(b"old")
        ticks = iter(range(0, 1000, 3))
        with mock.patch.object(controls_file.os, "replace", side_effect=PermissionError(13, "in use")), \
                mock.patch.object(controls_file.time, "sleep"), \
                mock.patch.object(controls_file.time, "monotonic", lambda: next(ticks)):
            controls_file.atomic_write(self.path, b"new")
        self.assertEqual(Path(self.path).read_bytes(), b"new")
        self.assertEqual(os.listdir(os.path.dirname(self.path)), ["controls.ini"])


class Migration(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.folder.cleanup)
        self.shared = os.path.join(self.folder.name, "game", "controls.ini")
        self.mine = os.path.join(self.folder.name, "own", "controls.json")
        os.makedirs(os.path.dirname(self.mine))

    def test_nothing_to_move(self):
        self.assertEqual(controls_file.migrate(self.shared, [self.mine]), [])
        self.assertFalse(os.path.exists(self.shared))

    def test_identical_copy_is_only_retired(self):
        os.makedirs(os.path.dirname(self.shared))
        Path(self.shared).write_bytes(b"1 = A\n")
        Path(self.mine).write_bytes(b"1 = A\n")
        self.assertEqual(controls_file.migrate(self.shared, [self.mine]), [])
        self.assertEqual(sorted(os.listdir(os.path.dirname(self.mine))), ["controls.json.migrated"])

    def test_settings_copy_is_used_only_while_there_is_no_shared_file(self):
        copy = os.path.join(self.folder.name, "copy.json")
        Path(copy).write_bytes(b"1 = C\n")
        os.makedirs(os.path.dirname(self.shared))
        Path(self.shared).write_bytes(b"1 = A\n")
        controls_file.migrate(self.shared, [self.mine, copy])
        self.assertEqual(Path(self.shared).read_bytes(), b"1 = A\n")
        os.unlink(self.shared)
        controls_file.migrate(self.shared, [self.mine, copy])
        self.assertEqual(Path(self.shared).read_bytes(), b"1 = C\n")
        self.assertTrue(os.path.exists(copy))                      # never touched


@unittest.skipUnless(os.path.isfile(os.path.join(REAL_ROOT, "launcher", "controls_edit.py")), "no T5DR install here")
class AgainstT5DRLauncher(unittest.TestCase):
    """The real controls_edit.ControlsEditor + DevicePoller of the install, scripted pads (T5_PAD_FILE)."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.out = self.folder.name
        self.pad_file = os.path.join(self.out, "pad.txt")
        modules, path = set(sys.modules), list(sys.path)      # the install's modules must not stay for other tests
        self.addCleanup(lambda: (sys.path.__setitem__(slice(None), path),
                                 [sys.modules.pop(name) for name in set(sys.modules) - modules]))
        env = mock.patch.dict(os.environ, {"T5_PAD_FILE": self.pad_file})
        env.start()
        self.addCleanup(env.stop)
        outer = self

        class Real(Controls, Adapter):
            def __init__(inner):
                super().__init__({"id": "t5dr", "short": "T5"})
                inner.root = REAL_ROOT
                inner.s = SimpleNamespace(out_dir=outer.out, env_overrides=lambda: {},
                                          legacy_controls_paths=(os.path.join(outer.out, "own", "controls.json"),))

            def running(inner):
                return False

        self.adapter = Real()
        if not self.adapter.controls_supported():
            self.skipTest("the install's controls modules do not load here")
        self.ce = self.adapter._controls_modules[0]
        self.addCleanup(self.adapter.controls_close)

    def write(self, text):
        Path(self.pad_file).write_text(text)

    def press(self, idle, held, slot):
        a = self.adapter
        a.controls_close()
        self.write(idle)
        a.poll_binding()
        time.sleep(0.05)
        a.poll_binding()
        a.begin_binding("file", slot)
        for _ in range(3):
            self.write(idle)
            a.poll_binding()
            time.sleep(0.03)
        self.write(held)
        state = {}
        for _ in range(80):
            state = a.poll_binding()
            if state["state"] in ("ready", "conflict"):
                break
            time.sleep(0.03)
        return state

    def expected(self, kind, vid, pid, binds):
        """What the launcher's own screen writes for the same presses: editor.bind on a fresh file."""
        path = os.path.join(self.out, "expected", "controls.ini")
        editor = self.ce.ControlsEditor.load(path)
        ref = self.ce.DeviceRef(kind, 0, vid, pid)
        for slot, source in binds:
            editor.bind(ref, self.ce.SCOPE_PORT, slot, [source])
        editor.save()
        return Path(path).read_text(encoding="latin-1")

    def check(self, kind, vid, pid, idle, plan):
        got = []
        for slot, source, held in plan:
            state = self.press(idle, held, slot)
            self.assertEqual((state["state"], state.get("source")), ("ready", source), (slot, held))
            self.adapter.accept_binding(swap=False)
            got.append((slot, source))
        written = Path(self.out, "controls.ini").read_text(encoding="latin-1")
        self.assertEqual(written, self.expected(kind, vid, pid, got))
        return written

    def test_xbox_pad_l1_then_r2_writes_what_the_launcher_writes(self):
        text = self.check("xinput", 0, 0, "xinput", [("L1", "LB", "xinput LB"), ("R2", "RT", "xinput RT"),
                                                     ("L2", "LT", "xinput LT")])
        self.assertIn("L1", text)
        self.assertIn("R2", text)

    def test_dualsense_l1_then_r2_with_trigger_axes(self):
        ds = "dinput:054C:0CE6"
        self.check("dinput", 0x054C, 0x0CE6, ds + " RX- RY-",
                   [("L1", "B5", ds + " RX- RY- B5"), ("R2", "B8", ds + " RY- B8 RX+"),
                    ("L2", "B7", ds + " RX- B7 RY+")])

    def test_edit_in_the_other_launcher_is_seen_and_ours_goes_to_the_same_file(self):
        self.check("xinput", 0, 0, "xinput", [("L1", "LB", "xinput LB")])
        theirs = self.ce.ControlsEditor.load(os.path.join(self.out, "controls.ini"))
        theirs.bind(self.ce.DeviceRef("xinput", 0, 0, 0), self.ce.SCOPE_PORT, "R2", ["RB"])
        theirs.save()
        state = self.press("xinput", "xinput LT", "L2")
        self.assertEqual(state["state"], "ready")
        self.adapter.accept_binding(swap=False)
        reread = self.ce.ControlsEditor.load(os.path.join(self.out, "controls.ini"))
        ref = self.ce.DeviceRef("xinput", 0, 0, 0)
        self.assertEqual(reread.sources(ref, "R2"), ["RB"])
        self.assertEqual(reread.sources(ref, "L2"), ["LT"])
        self.assertEqual(reread.sources(ref, "L1"), ["LB"])


if __name__ == "__main__":
    unittest.main()
