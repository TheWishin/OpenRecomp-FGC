"""The settings file T5DR's launcher and OpenRecomp share (openrecomp/settings_sync.py, docs/SETTINGS_SYNC.md): version,
unknown fields, atomic writes, a held file tried again, a damaged file moved aside, and the migration rules.
Temporary folders only. The same tests run in T5DR's repository against its copy of the module; the settings class
that uses it here is tested in test_t5_coexist_settings.py."""
import json
import os
import tempfile
import time
import unittest
from unittest import mock

from openrecomp import settings_sync as ss


def read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def raw(path):
    with open(path, "rb") as f:
        return f.read()


def write(path, value, age=0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f)
    if age:
        stamp = time.time() - age
        os.utime(path, (stamp, stamp))


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = self.enterContext(tempfile.TemporaryDirectory())
        self.shared = os.path.join(self.dir, "user")
        self.file = os.path.join(self.shared, ss.FILE_NAME)
        self.install = os.path.join(self.dir, "T5DR-Online-1.2.3")
        self.launcher_json = os.path.join(self.install, "launcher.json")
        os.makedirs(self.install)
        self.id = ss.install_id(self.install)

    def store(self, who="test", **kw):
        return ss.Store(self.shared, who=who, sleep=lambda _s: None, **kw)

    def backups(self):
        folder = os.path.join(self.shared, ss.BACKUP_DIR)
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []


class FileTests(Base):
    def test_nothing_is_written_until_something_is_saved(self):
        write(self.launcher_json, {"display": "borderless", "pkg": "p.pkg"})
        result = ss.sync(self.store(), self.id, read(self.launcher_json), self.launcher_json)
        self.assertEqual((result.state, result.values), ("missing", {"display": "borderless"}))
        self.assertFalse(os.path.exists(self.shared))

    def test_first_save_makes_the_file_from_launcher_json_and_backs_it_up(self):
        local = {"display": "borderless", "vsync": "off", "pkg": "p.pkg", "language": "de"}
        write(self.launcher_json, local)
        self.assertTrue(ss.save(self.store("a"), self.id, {"vsync": "on"}, local, self.launcher_json))
        doc = read(self.file)
        self.assertEqual((doc["format"], doc["version"], doc["updated_by"]), ("t5dr-settings", 1, "a"))
        self.assertEqual(doc["values"], {"display": "borderless", "vsync": "on"})       # no pkg, no language
        self.assertEqual(doc["installs"][self.id]["seen"], {"display": "borderless", "vsync": "off"})
        self.assertEqual(len(self.backups()), 1)
        self.assertTrue(self.backups()[0].startswith(f"launcher-{self.id}-"))
        self.assertEqual(os.listdir(self.shared).count(ss.FILE_NAME), 1)
        self.assertFalse([n for n in os.listdir(self.shared) if n.endswith(".tmp")])

    def test_folder_only_settings_never_reach_the_file(self):
        ss.save(self.store(), self.id, {"display": "window", "pkg": "x", "rap": "y", "out": "z", "language": "ja",
                                        "background": True, "clock_hint_shown": True, "controls_hint_shown": True,
                                        "gpu_build_warning": False})
        self.assertEqual(read(self.file)["values"], {"display": "window"})

    def test_unknown_fields_and_a_newer_version_are_kept(self):
        write(self.file, {"format": "t5dr-settings", "version": 7, "later": {"a": 1},
                          "values": {"display": "window", "from_a_later_launcher": [1, 2]}})
        self.assertTrue(ss.save(self.store(), self.id, {"display": "maximized"}))
        doc = read(self.file)
        self.assertEqual(doc["version"], 7)
        self.assertEqual(doc["later"], {"a": 1})
        self.assertEqual(doc["values"], {"display": "maximized", "from_a_later_launcher": [1, 2]})

    def test_a_save_keeps_what_another_launcher_saved_meanwhile(self):
        ss.save(self.store("a"), self.id, {"display": "window", "vsync": "on"})
        ss.save(self.store("b"), "other", {"display": "borderless"})        # the other launcher, while a is open
        ss.save(self.store("a"), self.id, {"vsync": "off"})
        self.assertEqual(read(self.file)["values"], {"display": "borderless", "vsync": "off"})

    def test_a_held_file_is_tried_again(self):
        ss.save(self.store(), self.id, {"display": "window"})
        real, calls = os.replace, []

        def replace(src, dst):
            calls.append(dst)
            if len(calls) <= 3:
                raise PermissionError(13, "held by the antivirus")
            return real(src, dst)

        with mock.patch.object(ss.os, "replace", replace):
            self.assertTrue(ss.save(self.store(), self.id, {"display": "maximized"}))
        self.assertEqual(len(calls), 4)
        self.assertEqual(read(self.file)["values"]["display"], "maximized")

    def test_a_file_held_for_good_is_left_alone_and_reported(self):
        ss.save(self.store(), self.id, {"display": "window"})
        before = raw(self.file)
        store = self.store(seconds=0.0)
        with mock.patch.object(ss.os, "replace", side_effect=PermissionError(13, "held")):
            self.assertFalse(ss.save(store, self.id, {"display": "maximized"}))
        self.assertEqual(raw(self.file), before)
        self.assertEqual(os.listdir(self.shared), [ss.FILE_NAME])           # no temporary file left
        self.assertTrue(store.notes)

    def test_a_file_that_cannot_be_read_now_changes_nothing(self):
        ss.save(self.store(), self.id, {"display": "window"})
        write(self.launcher_json, {"display": "borderless"})
        real = open

        def held(path, *a, **kw):
            if os.path.abspath(path) == os.path.abspath(self.file):
                raise PermissionError(13, "held")
            return real(path, *a, **kw)

        store = self.store(seconds=0.0)
        with mock.patch("builtins.open", held):
            result = ss.sync(store, self.id, read(self.launcher_json), self.launcher_json)
            self.assertFalse(ss.save(store, self.id, {"display": "maximized"}))
        self.assertEqual((result.state, result.values), ("locked", {"display": "borderless"}))
        self.assertEqual(read(self.file)["values"], {"display": "window"})
        self.assertEqual(os.listdir(self.shared), [ss.FILE_NAME])           # not moved aside, not replaced

    def test_a_damaged_file_is_moved_aside(self):
        for content in (b'{"values": {"display": ', b"[]", b"\xff\xfe", b'{"values": 3}'):
            with self.subTest(content=content):
                os.makedirs(self.shared, exist_ok=True)
                for name in os.listdir(self.shared):
                    os.unlink(os.path.join(self.shared, name))
                with open(self.file, "wb") as f:
                    f.write(content)
                write(self.launcher_json, {"display": "borderless"})
                store = self.store()
                result = ss.sync(store, self.id, read(self.launcher_json), self.launcher_json)
                self.assertEqual((result.state, result.values), ("missing", {"display": "borderless"}))
                aside = [n for n in os.listdir(self.shared) if ".corrupt-" in n]
                self.assertEqual(len(aside), 1)
                self.assertEqual(raw(os.path.join(self.shared, aside[0])), content)
                self.assertFalse(os.path.exists(self.file))
                self.assertTrue(ss.save(store, self.id, {"vsync": "off"}, read(self.launcher_json)))
                self.assertEqual(read(self.file)["values"], {"display": "borderless", "vsync": "off"})

    def test_a_file_being_replaced_is_read_again_before_it_counts_as_damaged(self):
        os.makedirs(self.shared)
        with open(self.file, "wb") as f:
            f.write(b'{"values": {"disp')
        good = json.dumps({"values": {"display": "maximized"}}).encode()

        def finish(_seconds):
            with open(self.file, "wb") as f:
                f.write(good)

        doc, state = ss.Store(self.shared, sleep=finish).read()
        self.assertEqual((state, doc["values"]), ("ok", {"display": "maximized"}))
        self.assertEqual(os.listdir(self.shared), [ss.FILE_NAME])

    def test_only_a_few_folders_and_backups_are_remembered(self):
        for n in range(ss.MAX_INSTALLS + 3):
            store = self.store(now=lambda n=n: 1000.0 + n)
            ss.save(store, f"id{n}", {"display": "window"}, mirrored={"display": "window"})
        self.assertEqual(sorted(read(self.file)["installs"]),
                         sorted(f"id{n}" for n in range(3, ss.MAX_INSTALLS + 3)))
        write(self.launcher_json, {"display": "window"})
        store = self.store()
        for _ in range(ss.MAX_BACKUPS + 4):
            store.backup(self.launcher_json, "launcher-x")
        self.assertEqual(len(self.backups()), ss.MAX_BACKUPS)


class MigrationTests(Base):
    """`extra` = what OpenRecomp 0.1.x kept for itself (its overrides file)."""

    def setUp(self):
        super().setUp()
        self.own = os.path.join(self.dir, "openrecomp-home", "settings.json")

    def migrate(self):
        store = self.store("openrecomp")
        result = ss.sync(store, self.id, read(self.launcher_json), self.launcher_json, read(self.own), self.own)
        return result, store

    def test_the_newer_own_file_wins_and_both_are_backed_up(self):
        write(self.launcher_json, {"display": "window", "vsync": "on", "mute": True, "pkg": "p"}, age=3600)
        write(self.own, {"display": "borderless", "training": "off", "pkg": "q"})
        before = raw(self.launcher_json), raw(self.own)
        result, _store = self.migrate()
        self.assertEqual(result.values, {"display": "borderless", "vsync": "on", "mute": True, "training": "off"})
        self.assertEqual(result.migrated, ("display", "training"))
        self.assertEqual(read(self.file)["values"], result.values)
        self.assertEqual((raw(self.launcher_json), raw(self.own)), before)
        names = self.backups()
        self.assertEqual([n.split("-")[0] for n in names], ["launcher", "own"])
        folder = os.path.join(self.shared, ss.BACKUP_DIR)
        self.assertEqual(raw(os.path.join(folder, names[0])), before[0])
        self.assertEqual(raw(os.path.join(folder, names[1])), before[1])

    def test_the_newer_launcher_json_wins_but_values_only_the_own_file_has_stay(self):
        write(self.own, {"display": "borderless", "training": "off"}, age=3600)
        write(self.launcher_json, {"display": "window", "vsync": "on"})
        result, _store = self.migrate()
        self.assertEqual(result.values, {"display": "window", "vsync": "on", "training": "off"})
        self.assertEqual(result.migrated, ("training",))
        self.assertEqual(len(self.backups()), 2)                 # the losing "borderless" is in the backup

    def test_own_overrides_meet_a_file_the_other_launcher_already_made(self):
        ss.save(self.store(now=lambda: time.time() - 600), self.id, {"display": "window", "vsync": "on"})
        write(self.launcher_json, {"display": "window", "vsync": "on"}, age=900)
        write(self.own, {"display": "borderless"})               # edited after the file's stamp: wins
        result, _store = self.migrate()
        self.assertEqual(result.values, {"display": "borderless", "vsync": "on"})
        write(self.own, {"vsync": "off"}, age=3600)             # older than the stamp: the file's value stays
        result, _store = self.migrate()
        self.assertEqual(result.values, {"display": "borderless", "vsync": "on"})

    def test_a_folder_seen_for_the_first_time_takes_the_shared_values(self):
        ss.save(self.store(), "the-old-folder", {"display": "borderless", "vsync": "off"})
        write(self.launcher_json, {"display": "window", "vsync": "off", "training": "inputs"})
        store = self.store()
        result = ss.sync(store, self.id, read(self.launcher_json), self.launcher_json)
        self.assertEqual(result.values, {"display": "borderless", "vsync": "off", "training": "inputs"})
        self.assertEqual(result.imported, ())
        self.assertEqual(len(self.backups()), 1)                 # its "window" is kept in the backup
        self.assertEqual(read(self.file)["installs"][self.id]["seen"],
                         {"display": "window", "vsync": "off", "training": "inputs"})
        ss.sync(self.store(), self.id, read(self.launcher_json), self.launcher_json)
        self.assertEqual(len(self.backups()), 1)                 # once


class EnvironmentTests(unittest.TestCase):
    def test_the_folder_is_next_to_the_online_settings(self):
        self.assertEqual(ss.shared_dir({"APPDATA": os.path.join("C:", os.sep, "u", "Roaming")}),
                         os.path.join("C:", os.sep, "u", "Roaming", "T5DROnline"))
        self.assertEqual(ss.shared_dir({"APPDATA": "a", "T5_ONLINE_DIR": os.path.abspath("o")}), os.path.abspath("o"))
        self.assertEqual(ss.shared_dir({"T5_ONLINE_DIR": "o", "T5_SETTINGS_DIR": os.path.abspath("s")}),
                         os.path.abspath("s"))

    def test_one_folder_has_one_id_however_it_is_written(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(ss.install_id(folder), ss.install_id(os.path.join(folder, "x", "..")))
            self.assertNotEqual(ss.install_id(folder), ss.install_id(os.path.join(folder, "x")))


if __name__ == "__main__":
    unittest.main()
