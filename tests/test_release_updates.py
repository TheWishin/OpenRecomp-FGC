"""The launcher's configured release channel against the layout Setup and the release zip really install.

Inert files only: a fake GitHub on 127.0.0.1 (tests/release_fixtures.py), test keys, no real registry writes.
"""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock
import zipfile

from openrecomp import updater as u

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import release_fixtures as rf  # noqa: E402

TEST_KEY = rf.public_key().hex()


def program(root, version):
    for item in u.REQUIRED_ITEMS:
        path = root / item
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("inert fixture", encoding="utf-8")
    (root / "release.json").write_text(json.dumps(dict(project=u.PROJECT, channel=u.RELEASE_CHANNEL, version=version)),
                                       encoding="utf-8")


def release_zip(version, extra=()):
    entries = [(f"{u.ARCHIVE_TOP}/{item}", b"inert fixture") for item in u.REQUIRED_ITEMS if item != "release.json"]
    entries.append((f"{u.ARCHIVE_TOP}/release.json",
                    json.dumps(dict(project=u.PROJECT, channel=u.RELEASE_CHANNEL, version=version)).encode()))
    entries += [("START_HERE.txt", b"read me"), ("START_HIER.txt", b"lies mich"), *extra]
    return rf.zip_bytes(entries)


class Temp(unittest.TestCase):
    def setUp(self):
        self.temp = Path(self.enterContext(tempfile.TemporaryDirectory(dir=Path(__file__).parent)))
        self.folder = self.temp / "install folder"
        self.root = self.folder / u.ARCHIVE_TOP
        self.root.mkdir(parents=True)
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_HOME=str(self.temp / "player-data")))


class ArchiveLayout(Temp):
    def test_program_folder_and_start_texts_beside_it(self):
        with zipfile.ZipFile(io.BytesIO(release_zip("v0.1.1"))) as archive:
            names = {"/".join(parts) for _info, parts in u._archive_members(archive, "v0.1.1")}
        self.assertEqual(names, set(u.REQUIRED_ITEMS))
        for bad in ("OTHER.txt", "T4/tools/build_game.ps1", "OpenRecomp-v0.1.1/run.cmd", f"{u.ARCHIVE_TOP}/settings.json"):
            with self.subTest(bad=bad), zipfile.ZipFile(io.BytesIO(release_zip("v0.1.1", [(bad, b"x")]))) as archive:
                with self.assertRaises(u.UpdateError):
                    u._archive_members(archive, "v0.1.1")

    def test_every_file_the_release_builder_puts_in_the_program_folder_is_a_program_item(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from tools import make_release
        self.assertTrue(set(make_release.LAUNCHER_ITEMS) <= set(u.PROGRAM_ITEMS))
        self.assertTrue(set(make_release.LOOSE) <= set(u.LOOSE_FILES))


class Helper(Temp):
    def test_helper_copies_only_the_interpreter_and_remembers_the_switches(self):
        program(self.root, "v0.1.0")
        (self.root / "portable" / "python312.dll").write_text("dll")
        site = self.root / "portable" / "Lib" / "site-packages" / "PySide6"
        site.mkdir(parents=True)
        (site / "QtCore.pyd").write_text("qt")
        staged = u._work_root(self.root) / ("a" * 24) / "new"
        program(staged, "v0.1.1")
        (staged.parent / "verified.json").write_text(json.dumps(dict(version="v0.1.1", channel=u.RELEASE_CHANNEL)))
        with mock.patch.object(u, "_verify_staged"), mock.patch.object(sys, "argv", ["openrecomp", "--windowed", "x"]):
            plan = u.prepare_update(self.root, staged)
        runner = plan.parent / "runner"
        self.assertTrue((runner / "portable" / "pythonw.exe").is_file())
        self.assertTrue((runner / "portable" / "python312.dll").is_file())
        self.assertFalse((runner / "portable" / "Lib").exists())
        self.assertTrue((runner / "updater.py").is_file())
        self.assertEqual(json.loads(plan.read_text())["args"], ["--windowed"])
        with mock.patch.object(u.subprocess, "Popen") as spawn:
            u.launch_update(self.root, plan)
        self.assertEqual(Path(spawn.call_args.args[0][0]), runner / "portable" / "pythonw.exe")


class FakeRegistry:
    HKEY_CURRENT_USER, KEY_READ, KEY_SET_VALUE, REG_SZ = 1, 2, 4, 1

    def __init__(self, location):
        self.values = {u.UNINSTALL_KEY: dict(InstallLocation=location, DisplayVersion="0.1.0"),
                       u.SETUP_KEY: dict(InstallLocation=location, Version="0.1.0")}
        registry = self

        class Key:
            def __init__(self, path):
                self.path = path

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False
        self.Key = Key

        def open_key(root, path, reserved, access):
            if path not in registry.values:
                raise OSError("no key")
            return Key(path)
        self.OpenKey = open_key
        self.QueryValueEx = lambda key, name: (registry.values[key.path][name], 1)
        self.SetValueEx = lambda key, name, reserved, kind, value: registry.values[key.path].__setitem__(name, value)


class SetupRecord(Temp):
    def record(self):
        lines = ["# OpenRecomp-FGC install record, written by Setup. Uninstall removes the file= lines only.",
                 "version=0.1.0", "desktop=1", f"file={u.ARCHIVE_TOP}/portable/old.dll", f"file={u.ARCHIVE_TOP}/run.cmd",
                 "file=Uninstall OpenRecomp.exe", "game=T4/tools/build_game.ps1"]
        (self.folder / u.SETUP_RECORD).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_setup_record_and_apps_entry_follow_the_update(self):
        program(self.root, "v0.1.1")
        (self.root / "games").mkdir()
        (self.root / "games" / "t4.json").write_text("{}")
        self.record()
        registry = FakeRegistry(str(self.folder))
        with mock.patch.dict(sys.modules, winreg=registry), mock.patch.object(u.os, "name", "nt"):
            self.assertTrue(u.follow_setup(self.root, "v0.1.1"))
        lines = (self.folder / u.SETUP_RECORD).read_text(encoding="utf-8").splitlines()
        self.assertIn("version=0.1.1", lines)
        self.assertIn("desktop=1", lines)
        self.assertIn("file=Uninstall OpenRecomp.exe", lines)
        self.assertIn("game=T4/tools/build_game.ps1", lines)
        self.assertNotIn(f"file={u.ARCHIVE_TOP}/portable/old.dll", lines)
        files = {line[5:] for line in lines if line.startswith(f"file={u.ARCHIVE_TOP}/")}
        self.assertEqual(files, {f"{u.ARCHIVE_TOP}/{item}" for item in u.REQUIRED_ITEMS} | {f"{u.ARCHIVE_TOP}/games/t4.json"})
        self.assertEqual(registry.values[u.UNINSTALL_KEY]["DisplayVersion"], "0.1.1")
        self.assertEqual(registry.values[u.SETUP_KEY]["Version"], "0.1.1")

    def test_another_installation_in_the_registry_is_left_alone(self):
        program(self.root, "v0.1.1")
        self.record()
        registry = FakeRegistry(str(self.temp / "elsewhere"))
        with mock.patch.dict(sys.modules, winreg=registry), mock.patch.object(u.os, "name", "nt"):
            u.follow_setup(self.root, "v0.1.1")
        self.assertEqual(registry.values[u.UNINSTALL_KEY]["DisplayVersion"], "0.1.0")

    def test_zip_install_has_no_record_and_nothing_changes(self):
        program(self.root, "v0.1.1")
        self.assertFalse(u.follow_setup(self.root, "v0.1.1"))
        (self.folder / u.SETUP_RECORD).write_text("something else\n", encoding="utf-8")
        self.assertFalse(u.follow_setup(self.root, "v0.1.1"))
        self.assertEqual((self.folder / u.SETUP_RECORD).read_text(encoding="utf-8"), "something else\n")


class Cleanup(Temp):
    def transaction(self, name, *, consumed=None, backup=False, result=False, age=0):
        path = u._work_root(self.root) / name
        (path / "new").mkdir(parents=True)
        if consumed:
            (path / "consumed.json").write_text(json.dumps(dict(status=consumed)))
        if backup:
            (path / "backup").mkdir()
        if result:
            (path / "result.json").write_text(json.dumps(dict(status="updated", version="v0.1.1")))
        stamp = time.time() - age
        for item in (path / "consumed.json", path):
            if item.exists():
                os.utime(item, (stamp, stamp))
        return path

    def test_finished_and_abandoned_folders_go_recovery_and_running_ones_stay(self):
        old = self.transaction("1" * 24, consumed="updated", backup=True, age=3600)
        fresh = self.transaction("2" * 24, consumed="rolled_back", backup=True, age=10)
        recovery = self.transaction("3" * 24, consumed="recovery_required", backup=True, age=86400 * 9)
        interrupted = self.transaction("4" * 24, backup=True, age=86400 * 9)
        abandoned = self.transaction("5" * 24, age=86400 * 9)
        waiting = self.transaction("6" * 24, result=True, age=86400 * 9)
        helper = self.transaction("7" * 24, age=60)
        self.assertEqual(u.clean_finished(self.root), 2)
        self.assertFalse(old.exists())
        self.assertFalse(abandoned.exists())
        for kept in (fresh, recovery, interrupted, waiting, helper):
            self.assertTrue(kept.exists(), kept.name)

    def test_nothing_is_removed_while_a_helper_holds_the_lock(self):
        old = self.transaction("1" * 24, consumed="updated", age=3600)
        (u._work_root(self.root) / "apply.lock").mkdir()
        self.assertEqual(u.clean_finished(self.root), 0)
        self.assertTrue(old.exists())

    def test_shown_result_is_marked_then_removed_later(self):
        path = self.transaction("8" * 24, result=True)
        self.assertEqual(u.update_result(self.root)["status"], "updated")
        self.assertTrue((path / "consumed.json").is_file())
        self.assertEqual(u.clean_finished(self.root, now=time.time() + 3600), 1)
        self.assertFalse(u._work_root(self.root).exists())


class FakeGitHubChannel(Temp):
    def setUp(self):
        super().setUp()
        self.gh = self.enterContext(rf.FakeGitHub())
        self.enterContext(mock.patch.dict(os.environ, {u.TEST_ENV: self.gh.base, u.TEST_KEY_ENV: TEST_KEY}))
        program(self.root, "v0.1.0")

    def publish(self, tag, prerelease=False, seed=rf.TEST_SEED, zip_data=None):
        data = zip_data if zip_data is not None else release_zip(tag)
        return self.gh.add(rf.LAUNCHER_REPO, tag, rf.launcher_release_assets(tag, data, seed=seed), prerelease=prerelease)

    def test_signed_update_is_offered_downloaded_and_staged(self):
        self.assertIsNone(u.check_release(self.root))                       # nothing published yet
        self.publish("v0.1.1")
        offer = u.check_release(self.root)
        self.assertEqual(offer["version"], "v0.1.1")
        staged = u.stage_update(self.root, offer)
        self.assertEqual(u.local_version(staged), "v0.1.1")
        self.assertTrue(any(r.startswith(f"/storage/{rf.LAUNCHER_ID}/") for r in self.gh.requests))
        self.assertFalse((staged / "START_HERE.txt").exists())

    def test_test_version_only_with_the_switch(self):
        self.publish("v0.2.0-beta.1", prerelease=True)
        self.assertIsNone(u.check_release(self.root))
        self.assertEqual(u.check_release(self.root, prereleases=True)["version"], "v0.2.0-beta.1")

    def test_wrong_key_and_tampered_zip_change_nothing(self):
        self.publish("v0.1.1", seed=bytes(32))
        with self.assertRaises(u.UpdateError):
            u.stage_update(self.root, u.check_release(self.root))
        self.gh.releases[rf.LAUNCHER_REPO] = []
        release = self.publish("v0.1.2")
        path = f"/{rf.LAUNCHER_REPO}/releases/download/v0.1.2/OpenRecomp-v0.1.2.zip"
        data = bytearray(self.gh.files[path])
        data[len(data) // 2] ^= 0xFF                                          # same size, other bytes
        self.gh.files[path] = bytes(data)
        offer = u.check_release(self.root)
        self.assertEqual(offer["version"], release["tag_name"])
        with self.assertRaises(u.UpdateError):
            u.stage_update(self.root, offer)
        self.assertEqual(u.local_version(self.root), "v0.1.0")
        self.assertFalse(u._work_root(self.root).exists())      # nothing left beside the installation

    def test_foreign_address_is_refused_in_test_mode_too(self):
        channel = u.configured_channel()
        self.assertTrue(u.url_allowed(f"{self.gh.base}/repos/{rf.LAUNCHER_REPO}/releases/latest", channel, "api"))
        self.assertFalse(u.url_allowed(f"{self.gh.base}/repos/{rf.T4_REPO}/releases/latest", channel, "api"))
        self.assertFalse(u.url_allowed(f"{self.gh.base}/storage/{rf.T4_ID}/v0.1.1/x.zip", channel))
        self.assertFalse(u.url_allowed(f"https://github.com/{rf.LAUNCHER_REPO}/releases/download/v1/x.zip", channel))


if __name__ == "__main__":
    unittest.main()
