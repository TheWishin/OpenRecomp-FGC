"""T5DR settings in OpenRecomp with synthetic JSON and an inert native settings contract: the settings both
launchers share (docs/SETTINGS_SYNC.md) and what stays OpenRecomp's own. Temporary folders only."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp import settings_sync
from openrecomp.adapters.t5_coexist import load_settings, local_path, readonly_imports, shared_folder


class CoexistSettingsTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory(dir=Path(__file__).parent)))
        self.root = self.folder / "old-install"
        self.root.mkdir()
        self.home = self.folder / "new-home"
        self.source = self.root / "launcher.json"
        self.original = dict(display="window", out_dir=str(self.root / "native"),
                             replay_dir=str(self.root / "private-replays"),
                             future=dict(enabled=True, fields=[1, 2]))
        self.source.write_text(json.dumps(self.original), encoding="utf-8")
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_HOME=str(self.home)))
        source = self.source

        class NativeSettings(dict):
            saves = 0

            def __init__(self):
                super().__init__(json.loads(source.read_text(encoding="utf-8")))
                self.path = str(source)
                self.save()

            def save(self):
                NativeSettings.saves += 1
                source.write_text(json.dumps(self), encoding="utf-8")

            @property
            def out_dir(self):
                return self["out_dir"]

            @property
            def replay_dir(self):
                return self["replay_dir"]

            def env_overrides(self):
                return {"DISPLAY_CHOICE": self["display"], "PS3_CONTROLS": "native-controls"}

        self.native = NativeSettings
        self.core = SimpleNamespace(Settings=NativeSettings, DEFAULTS={"display": "window", "replay_dir": ""})

    def load(self, **kwargs):
        return load_settings(self.core, str(self.root), **kwargs)

    def shared(self):
        return json.loads((self.home / "t5dr-shared" / "settings.json").read_text(encoding="utf-8"))

    def launcher_json(self):
        return json.loads(self.source.read_text(encoding="utf-8"))

    def private(self):
        return Path(local_path(str(self.root), "settings.json"))

    def backups(self):
        folder = self.home / "t5dr-shared" / "settings-backup"
        return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []

    def test_the_shared_file_of_a_test_run_is_inside_the_tests_own_home(self):
        self.assertEqual(Path(shared_folder()), self.home / "t5dr-shared")
        with mock.patch.dict(os.environ, T5_SETTINGS_DIR=str(self.folder / "elsewhere")):
            self.assertEqual(Path(shared_folder()), self.folder / "elsewhere")

    def test_attachment_keeps_source_bytes_and_creates_nothing(self):
        before = self.source.read_bytes()
        settings = self.load()
        self.assertEqual(self.source.read_bytes(), before)
        self.assertFalse(self.home.exists())
        self.assertEqual(self.native.saves, 0)
        self.assertEqual(settings["future"], self.original["future"])
        self.assertEqual(settings.out_dir, self.original["out_dir"])
        self.assertEqual(settings.replay_dir, self.original["replay_dir"])
        self.assertEqual(settings.path, str(self.source))
        self.assertEqual(settings.source_path, str(self.source))


    def test_saved_always_left_edit_keeps_its_meaning_on_a_three_way_install(self):
        # An OpenRecomp 0.1.x edit from a 1.1.9 install (always_left only) must still choose the side on 1.2.0.
        self.core.DEFAULTS.update(screen_side="dealt", always_left=False)
        path = self.private()
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(dict(always_left=True)), encoding="utf-8")
        self.assertEqual(self.load()["screen_side"], "left")
        self.assertFalse(path.exists())                       # moved into the shared file
        self.assertEqual(self.shared()["values"]["screen_side"], "left")
        self.assertEqual(self.load()["screen_side"], "left")
        settings = self.load()
        settings["screen_side"] = "right"
        settings.save()
        self.assertEqual(self.load()["screen_side"], "right")
        del self.core.DEFAULTS["screen_side"]                 # a 1.1.9 install: the three-way side is not its setting
        self.source.write_text(json.dumps(self.original), encoding="utf-8")
        self.assertNotIn("screen_side", self.load())


    def test_a_change_goes_to_the_shared_file_and_into_launcher_json_for_an_older_t5dr_launcher(self):
        settings = self.load()
        settings["display"] = "borderless"
        settings.save()
        doc = self.shared()
        self.assertEqual((doc["version"], doc["updated_by"]), (1, "openrecomp"))
        self.assertEqual(doc["values"]["display"], "borderless")
        self.assertEqual(self.launcher_json(), dict(self.original, display="borderless"))    # nothing else touched
        self.assertFalse(self.private().exists())
        self.assertEqual(len(self.backups()), 1)               # launcher.json as it was before the first shared save
        self.assertEqual(settings.env_overrides()["DISPLAY_CHOICE"], "borderless")
        self.assertEqual(self.native.saves, 0)
        self.assertEqual(self.load()["display"], "borderless")

    def test_what_the_t5dr_launcher_saved_is_shown_here_after_a_restart(self):
        settings = self.load()
        settings["display"] = "borderless"
        settings.save()
        # a T5DR launcher that knows the shared file: it writes both files
        store = settings_sync.Store(shared_folder(), who="t5dr-launcher")
        changed = dict(self.launcher_json(), display="maximized")
        self.source.write_text(json.dumps(changed), encoding="utf-8")
        self.assertTrue(settings_sync.save(store, settings.coexist_install, {"display": "maximized"},
                                           mirrored=changed))
        self.assertEqual(self.load()["display"], "maximized")
        # a T5DR launcher of 1.2.2: only launcher.json, written later than the shared value
        self.source.write_text(json.dumps(dict(changed, display="window")), encoding="utf-8")
        later = time.time() + 5
        os.utime(self.source, (later, later))
        self.assertEqual(self.load()["display"], "window")
        self.assertEqual(self.shared()["values"]["display"], "window")

    def test_an_unchanged_launcher_json_does_not_undo_a_shared_value(self):
        settings = self.load()
        settings["display"] = "borderless"
        with mock.patch.object(settings_sync, "mirror", return_value=False):      # launcher.json was held
            settings.save()
        self.assertEqual(self.launcher_json()["display"], "window")
        self.source.write_text(json.dumps(self.original), encoding="utf-8")       # 1.2.2 saves the same values again
        later = time.time() + 5
        os.utime(self.source, (later, later))
        self.assertEqual(self.load()["display"], "borderless")

    def test_old_overrides_move_into_the_shared_file_and_the_newer_file_wins(self):
        path = self.private()
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"display": "maximized", "pkg": "D:/own/t5.pkg"}), encoding="utf-8")
        old = time.time() - 3600
        os.utime(self.source, (old, old))
        settings = self.load()
        self.assertEqual((settings["display"], settings["pkg"]), ("maximized", "D:/own/t5.pkg"))
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"pkg": "D:/own/t5.pkg"})
        self.assertEqual(self.shared()["values"]["display"], "maximized")
        self.assertEqual([name.split("-")[0] for name in self.backups()], ["launcher", "own"])
        self.assertEqual(self.launcher_json(), self.original)   # attachment still writes nothing into the folder

    def test_old_overrides_lose_against_a_newer_launcher_json_and_are_backed_up(self):
        path = self.private()
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"display": "maximized"}), encoding="utf-8")
        old = time.time() - 3600
        os.utime(path, (old, old))
        before = path.read_bytes()
        self.assertEqual(self.load()["display"], "window")
        self.assertFalse(path.exists())
        folder = self.home / "t5dr-shared" / "settings-backup"
        self.assertEqual([p.read_bytes() for p in folder.iterdir() if p.name.startswith("own-")], [before])

    def test_a_held_shared_file_keeps_the_edit_here_until_the_next_start(self):
        settings = self.load()
        settings["display"] = "borderless"
        with mock.patch.object(settings_sync, "write_json", return_value=False):
            settings.save()
        self.assertEqual(json.loads(self.private().read_text(encoding="utf-8")), {"display": "borderless"})
        self.assertEqual(self.launcher_json(), self.original)
        self.assertEqual(self.load()["display"], "borderless")
        self.assertFalse(self.private().exists())
        self.assertEqual(self.shared()["values"]["display"], "borderless")

    def test_a_shared_file_held_at_the_start_changes_nothing(self):
        settings = self.load()
        settings["display"] = "borderless"
        settings.save()
        store = settings_sync.Store(shared_folder(), who="t5dr-launcher")      # saved from another T5DR folder
        self.assertTrue(settings_sync.save(store, "another-folder", {"display": "maximized"}))
        before = (self.home / "t5dr-shared" / "settings.json").read_bytes()
        real = settings_sync.read_json

        def held(path, *args, **kwargs):
            return (None, "locked") if os.path.basename(path) == "settings.json" else real(path, *args, **kwargs)

        with mock.patch.object(settings_sync, "read_json", held):
            settings = self.load()
        self.assertEqual(settings["display"], "borderless")     # the folder's own value for this start
        self.assertEqual((self.home / "t5dr-shared" / "settings.json").read_bytes(), before)
        self.assertEqual(self.launcher_json()["display"], "borderless")
        self.assertTrue(settings.sync_notes)
        self.assertEqual(self.load()["display"], "maximized")

    def test_a_damaged_shared_file_is_moved_aside(self):
        folder = self.home / "t5dr-shared"
        folder.mkdir(parents=True)
        (folder / "settings.json").write_bytes(b'{"values": {"display": "bord')
        settings = self.load()
        self.assertEqual(settings["display"], "window")
        names = [p.name for p in folder.iterdir()]
        self.assertEqual(len(names), 1)
        self.assertTrue(names[0].startswith("settings.json.corrupt-"))
        self.assertEqual((folder / names[0]).read_bytes(), b'{"values": {"display": "bord')
        settings["display"] = "maximized"
        settings.save()
        self.assertEqual(self.shared()["values"]["display"], "maximized")

    def test_a_choice_the_installed_launcher_does_not_have_is_not_used(self):
        source = self.source

        class Checking(dict):                                   # a Settings that reads a path and checks, as core's
            def __init__(self, path=None):
                super().__init__(json.loads(Path(path or source).read_text(encoding="utf-8")))
                self.path = str(path or source)
                if self["display"] not in ("window", "borderless"):
                    self["display"] = "window"

            out_dir = property(lambda self: self["out_dir"])

            def env_overrides(self):
                return {}

            def save(self):
                raise AssertionError("the installed Settings must not save")

        self.core.Settings = Checking
        store = settings_sync.Store(shared_folder(), who="a later launcher")
        settings_sync.save(store, "another-folder", {"display": "a-later-mode"})
        self.assertEqual(self.load()["display"], "window")
        settings_sync.save(store, "another-folder", {"display": "borderless"})
        self.assertEqual(self.load()["display"], "borderless")
        self.assertEqual(self.launcher_json(), self.original)

    def test_a_settings_copy_uses_no_shared_file(self):
        copy = self.folder / "chosen-copy"
        copy.mkdir()
        (copy / "launcher.json").write_text(json.dumps(dict(self.original, display="maximized")), encoding="utf-8")
        settings = self.load(settings_source=str(copy))
        settings["display"] = "window"
        settings.save()
        self.assertFalse((self.home / "t5dr-shared").exists())
        self.assertEqual(json.loads(Path(settings.private_path("settings.json")).read_text(encoding="utf-8")),
                         {"display": "window"})


    def test_folder_choices_stay_in_the_private_file_and_new_native_settings_are_read(self):
        settings = self.load()
        path = Path(settings.private_path("settings.json"))
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"pkg": "D:/own/t5.pkg"}), encoding="utf-8")
        before = self.source.read_bytes()
        settings = self.load()
        settings["rap"] = "D:/own/t5.rap"
        settings.save()
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")),
                         {"pkg": "D:/own/t5.pkg", "rap": "D:/own/t5.rap"})
        self.assertEqual(self.source.read_bytes(), before)
        self.assertFalse((self.home / "t5dr-shared").exists())
        changed = dict(self.original, replay_dir=str(self.root / "another-replay-folder"))
        self.source.write_text(json.dumps(changed), encoding="utf-8")
        fresh = self.load()
        self.assertEqual(fresh.replay_dir, changed["replay_dir"])
        self.assertEqual((fresh["pkg"], fresh["rap"]), ("D:/own/t5.pkg", "D:/own/t5.rap"))

    def test_read_only_save_does_not_create_override(self):
        settings = self.load()
        settings.save()
        self.assertFalse(self.home.exists())

    def test_invalid_private_json_is_preserved(self):
        path = Path(local_path(str(self.root), "settings.json"))
        path.parent.mkdir(parents=True)
        for content in (b"[]", b'{"display":', b"\xff"):
            path.write_bytes(content)
            with self.subTest(content=content), self.assertRaises((ValueError, UnicodeError)):
                self.load()
            self.assertEqual(path.read_bytes(), content)


    def test_failed_publish_keeps_every_file_and_the_pending_edit(self):
        settings = self.load()
        settings["display"] = "maximized"
        settings.save()
        shared = self.home / "t5dr-shared" / "settings.json"
        before = shared.read_bytes(), self.source.read_bytes()
        settings["display"] = "borderless"
        with mock.patch("openrecomp.adapters.t5_coexist.os.replace", side_effect=OSError("synthetic full disk")):
            with self.assertRaises(OSError):
                settings.save()
        self.assertEqual((shared.read_bytes(), self.source.read_bytes()), before)
        leftovers = [p for folder in (shared.parent, self.root, self.private().parent) for p in folder.iterdir()
                     if p.suffix == ".tmp"]
        self.assertEqual(leftovers, [])
        settings.save()
        self.assertEqual(self.shared()["values"]["display"], "borderless")
        self.assertEqual(self.launcher_json()["display"], "borderless")

    def test_private_paths_are_distinct_per_selected_install(self):
        other = self.folder / "another-install"
        other.mkdir()
        self.assertNotEqual(local_path(str(self.root), "online.json"), local_path(str(other), "online.json"))

    def test_overlapping_home_is_refused_before_constructor(self):
        with mock.patch.dict(os.environ, OPENRECOMP_HOME=str(self.root / "new-home")):
            with mock.patch.object(self.core, "Settings", side_effect=AssertionError("must not construct")):
                with self.assertRaises(ValueError):
                    self.load()
        self.assertEqual(self.native.saves, 0)

    def test_output_overlap_and_source_copy_overlap_are_refused(self):
        changed = dict(self.original, out_dir=str(self.home))
        self.source.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.load()
        self.source.write_text(json.dumps(self.original), encoding="utf-8")
        copy = self.home / "source-copy"
        copy.mkdir(parents=True)
        (copy / "launcher.json").write_text(json.dumps(self.original), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.load(settings_source=str(copy))

    def test_controls_and_online_source_copy_is_read_only_until_explicit_changes(self):
        copy = self.folder / "chosen-copy"
        copy.mkdir()
        values = dict(self.original, display="maximized", copy_future=True)
        (copy / "launcher.json").write_text(json.dumps(values), encoding="utf-8")
        controls = copy / "controls.json"
        controls.write_text("{}", encoding="utf-8")
        before = {path.name: path.read_bytes() for path in copy.iterdir()}
        settings = self.load(settings_source=str(copy))
        self.assertEqual(settings["display"], "maximized")
        self.assertTrue(settings["copy_future"])
        self.assertEqual(settings.env_overrides()["PS3_CONTROLS"], "native-controls")      # only the player's own setting
        self.assertEqual(settings.legacy_controls_paths, (settings.controls_write_path, str(controls)))
        self.assertEqual(settings.legacy_online_paths, (str(copy / "online.json"),))
        self.assertFalse(self.home.exists())
        private = Path(settings.controls_write_path)
        private.parent.mkdir(parents=True)
        private.write_text("{}", encoding="utf-8")
        self.assertEqual(settings.env_overrides()["PS3_CONTROLS"], "native-controls")
        settings["display"] = "window"
        settings.save()
        self.assertEqual({path.name: path.read_bytes() for path in copy.iterdir()}, before)

    def test_bytecode_setting_is_restored_after_success_and_failure(self):
        before = sys.dont_write_bytecode
        with readonly_imports():
            self.assertTrue(sys.dont_write_bytecode)
        self.assertEqual(sys.dont_write_bytecode, before)
        with self.assertRaises(RuntimeError):
            with readonly_imports():
                self.assertTrue(sys.dont_write_bytecode)
                raise RuntimeError("synthetic import failure")
        self.assertEqual(sys.dont_write_bytecode, before)


if __name__ == "__main__":
    unittest.main()
