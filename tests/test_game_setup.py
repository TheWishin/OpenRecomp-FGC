"""Installing and updating T5DR Online and T4 from their GitHub releases (game_releases, game_setup, the Nav rows).

Everything runs against a fake GitHub on 127.0.0.1 with test zips and a test signing key; nothing leaves this PC.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock
import zipfile

from openrecomp import game_releases as gr
from openrecomp import game_setup as gs
from openrecomp import i18n
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import release_fixtures as rf  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TEST_KEY = rf.public_key().hex()


class Env(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix=".test-setup-", dir=ROOT)
        self.addCleanup(self.work.cleanup)
        self.dir = Path(self.work.name)
        self.gh = rf.FakeGitHub()
        self.gh.__enter__()
        self.addCleanup(self.gh.__exit__)
        env = mock.patch.dict(os.environ, {gr.TEST_ENV: self.gh.base, gr.TEST_KEY_ENV: TEST_KEY,
                                           "OPENRECOMP_HOME": str(self.dir / "home")})
        env.start()
        self.addCleanup(env.stop)

    def offer(self, game="t5dr", channel="stable"):
        return gr.latest(gr.SOURCES[game], channel)


class Releases(Env):
    def test_stable_channel_takes_the_newest_published_plain_version(self):
        self.gh.add_t5dr("1.2.0", code_id="aaaaaaaaaaaaaaaa")
        self.gh.add_t5dr("1.3.0-beta.1", prerelease=True)
        offer = self.offer()
        self.assertEqual((offer["version"], offer["code_id"], offer["prerelease"]), ("1.2.0", "aaaaaaaaaaaaaaaa", False))
        self.assertEqual(self.offer(channel="prerelease")["version"], "1.3.0-beta.1")

    def test_drafts_never_and_a_test_version_only_on_the_test_channel(self):
        release = self.gh.add_t5dr("1.2.0")
        with self.assertRaises(gr.ReleaseError):
            gr.parse_release(gr.SOURCES["t5dr"], dict(release, draft=True), "prerelease")
        with self.assertRaises(gr.ReleaseError):
            gr.parse_release(gr.SOURCES["t5dr"], dict(release, prerelease=True), "stable")
        self.assertEqual(gr.parse_release(gr.SOURCES["t5dr"], dict(release, prerelease=True), "prerelease")["version"], "1.2.0")

    def test_notes_leave_out_tables_and_markup(self):
        body = "## What's new\n\n- Faster loading\n\n| Code ID | `0123456789abcdef` |\n|---|---|\n\n---\nChecksums"
        self.assertEqual(gr.release_notes(body), "What's new Faster loading")

    def test_no_release_yet_is_none(self):
        self.assertIsNone(self.offer("t4"))
        self.assertIsNone(self.offer("t4", "prerelease"))

    def test_assets_of_another_place_or_without_checksum_are_refused(self):
        release = self.gh.add_t5dr("1.2.0")
        foreign = json.loads(json.dumps(release))
        foreign["assets"][0]["browser_download_url"] = "https://example.com/T5DR-Online-1.2.0.zip"
        no_sums = dict(release, assets=[a for a in release["assets"] if a["name"] != "SHA256SUMS"])
        for data in (foreign, no_sums):
            with self.assertRaises(gr.ReleaseError):
                gr.parse_release(gr.SOURCES["t5dr"], data)

    def test_t4_takes_its_one_launcher_zip_under_another_name(self):
        self.gh.add_t4("v0.1.0-beta.1", name="OpenRecomp-FGC-T4-beta1.zip")
        offer = self.offer("t4", "prerelease")
        self.assertEqual(offer["zip"]["name"], "OpenRecomp-FGC-T4-beta1.zip")
        self.assertEqual(offer["sums"]["name"], "SHA256SUMS")
        two = self.gh.add_t4("v0.1.1-beta.1")
        two["assets"].append(dict(two["assets"][0], name="T4-other.zip"))
        two["assets"] = [a for a in two["assets"] if a["name"] != "OpenRecomp-Tekken4-v0.1.1-beta.1.zip"]
        with self.assertRaises(gr.ReleaseError):
            gr.parse_release(gr.SOURCES["t4"], dict(two, assets=two["assets"] + [dict(two["assets"][0], name="T4-third.zip")]),
                             "prerelease")

    def test_t4_is_signed_with_its_own_key(self):
        src = gr.SOURCES["t4"]
        self.assertEqual(hashlib.sha256(bytes.fromhex(src.keys[0])).hexdigest()[:16], "6c690283a70408ad")
        self.assertNotIn(src.keys[0], gr.SOURCES["t5dr"].keys)
        cases = [dict(seed=bytes(32)), dict(signed=False)]
        for i, case in enumerate(cases):
            with self.subTest(case=i):
                self.gh.releases[rf.T4_REPO] = []
                self.gh.add_t4(f"v0.1.{i}", **case)
                with self.assertRaises(gr.ReleaseError) as raised:
                    gr.verified_zip(src, self.offer("t4", "prerelease"), str(self.dir / f"t4-{i}"))
                self.assertEqual(raised.exception.key, "@setup.err_signature")
        self.gh.releases[rf.T4_REPO] = []
        self.gh.add_t4("v0.1.9")
        self.assertTrue(zipfile.is_zipfile(gr.verified_zip(src, self.offer("t4", "prerelease"), str(self.dir / "t4-ok"))))
        # A T5DR signature is not a T4 one (another statement and format).
        sums = b"0" * 64 + b"  x.zip\n"
        with self.assertRaises(gr.ReleaseError):
            gr.check_signature(src, "0.1.0", sums, rf.t5dr_signature("0.1.0", sums), keys=(TEST_KEY,))
        self.assertEqual(gr.check_signature(src, "0.1.0", sums, rf.t4_signature("0.1.0", sums), keys=(TEST_KEY,)),
                         hashlib.sha256(bytes.fromhex(TEST_KEY)).hexdigest()[:16])

    def test_release_sign_tool_writes_the_t4_envelope_the_launcher_checks(self):
        sys.path.insert(0, str(ROOT))
        from tools import release_sign
        sums = b"1" * 64 + b"  OpenRecomp-Tekken4-v0.1.0.zip\n"
        envelope = release_sign.game_signature("t4", "0.1.0", sums, rf.TEST_SEED)
        gr.check_signature(gr.SOURCES["t4"], "0.1.0", sums, envelope, keys=(TEST_KEY,))
        with self.assertRaises(gr.ReleaseError):
            gr.check_signature(gr.SOURCES["t4"], "0.1.1", sums, envelope, keys=(TEST_KEY,))
        with self.assertRaises(ValueError):
            release_sign.game_signature("t4", "v0.1.0", sums, rf.TEST_SEED)

    def test_channels_for_the_switch_t4_beta_and_installed_test_versions(self):
        install = self.dir / "inst"
        install.mkdir()
        self.assertEqual(gr.channel({}, "t5dr", None), "stable")
        self.assertEqual(gr.channel({"game_prereleases": True}, "t5dr", None), "prerelease")
        self.assertEqual(gr.channel({}, "t4", None), "prerelease")       # T4 is in beta: no stable release yet
        (install / "release.json").write_text(json.dumps(dict(version="1.3.0-beta.1")), encoding="utf-8")
        self.assertEqual(gr.channel({}, "t5dr", str(install)), "prerelease")
        (install / "release.json").write_text(json.dumps(dict(version="1.2.0")), encoding="utf-8")
        self.assertEqual(gr.channel({}, "t5dr", str(install)), "stable")
        (install / gr.MARKER).write_text(json.dumps(dict(game="t5dr", version="1.2.0", prerelease=True)), encoding="utf-8")
        self.assertEqual(gr.channel({}, "t5dr", str(install)), "prerelease")

    def test_addresses_this_project_only(self):
        src = gr.SOURCES["t5dr"]
        with mock.patch.dict(os.environ, {gr.TEST_ENV: ""}):
            self.assertTrue(gr.url_allowed(src, "https://api.github.com/repos/TheWishin/T5DROnline/releases/latest", "api"))
            self.assertTrue(gr.url_allowed(src, "https://github.com/TheWishin/T5DROnline/releases/download/v1/x.zip", "download"))
            self.assertTrue(gr.url_allowed(src, "https://objects.githubusercontent.com/github-production-release-asset-2e65be/1423117739/abc", "download"))
            for url in ("http://github.com/TheWishin/T5DROnline/releases/download/v1/x.zip",
                        "https://github.com/Other/T5DROnline/releases/download/v1/x.zip",
                        "https://objects.githubusercontent.com/github-production-release-asset-2e65be/1435747302/abc",
                        "https://github.com:8443/TheWishin/T5DROnline/releases/download/v1/x.zip",
                        "https://user@github.com/TheWishin/T5DROnline/releases/download/v1/x.zip",
                        "https://github.com/TheWishin/T5DROnline/releases/download/../../x"):
                self.assertFalse(gr.url_allowed(src, url, "download"), url)
        with mock.patch.dict(os.environ, {gr.TEST_ENV: "http://203.0.113.5:8000"}):
            self.assertEqual(gr.test_base(), "")           # a test GitHub only on this PC
            self.assertEqual(gr.signing_keys(src), src.keys)


class Download(Env):
    def test_signed_release_downloads_through_the_storage_redirect(self):
        self.gh.add_t5dr("1.2.0")
        path = gr.verified_zip(gr.SOURCES["t5dr"], self.offer(), str(self.dir / "dl"))
        self.assertTrue(zipfile.is_zipfile(path))
        self.assertTrue(any(r.startswith("/storage/1423117739/") for r in self.gh.requests))

    def test_wrong_key_missing_signature_and_wrong_checksum_are_refused(self):
        cases = [dict(seed=bytes(32)), dict(signed=False), dict(sums_for=b"something else")]
        for i, case in enumerate(cases):
            with self.subTest(case=i):
                self.gh.releases[rf.T5DR_REPO] = []
                self.gh.add_t5dr(f"1.2.{i}", **case)
                with self.assertRaises(gr.ReleaseError) as raised:
                    gr.verified_zip(gr.SOURCES["t5dr"], self.offer(), str(self.dir / f"dl{i}"))
                self.assertIn(raised.exception.key, ("@setup.err_signature", "@setup.err_checksum"))
                self.assertFalse((self.dir / f"dl{i}" / f"T5DR-Online-1.2.{i}.zip").exists())

    def test_signature_by_the_installed_t5drs_own_key(self):
        root = self.dir / "T5DR-Online-1.1.0"
        (root / "launcher").mkdir(parents=True)
        new_key = rf.public_key(b"\x07" * 32).hex()
        (root / "launcher" / "updater.py").write_text(f'RELEASE_PUBLIC_KEYS = (\n    "{new_key}",\n)\n', encoding="utf-8")
        self.assertEqual(gr.install_keys("t5dr", str(root)), (new_key,))
        self.assertEqual(gr.install_keys("t4", str(root)), ())


class Unpack(Env):
    def zip(self, entries):
        path = self.dir / "r.zip"
        path.write_bytes(rf.zip_bytes(entries))
        return str(path)

    def test_bad_names_player_files_and_wrong_version_are_refused(self):
        src, offer = gr.SOURCES["t5dr"], dict(version="1.2.0", tag="v1.2.0")
        good = rf.t5dr_entries("1.2.0")
        for bad in ([("T5DR-Online-1.2.0/../evil.txt", "x")], [("T5DR-Online-1.2.0/native/t5dr.exe", "x")],
                    [("T5DR-Online-1.2.0/launcher.json", "{}")], [("T5DR-Online-1.2.0/aux.txt", "x")],
                    [("T5DR-Online-1.2.0/name. ", "x")], [("/T5DR-Online-1.2.0/x.txt", "x")]):
            with self.subTest(bad=bad[0][0]), self.assertRaises(gr.ReleaseError):
                gr.unpack(src, self.zip(good + bad), str(self.dir / "out"), offer)
        with self.assertRaises(gr.ReleaseError):
            gr.unpack(src, self.zip(rf.t5dr_entries("1.1.0")), str(self.dir / "out2"), offer)

    def test_t4_takes_only_its_source_folder(self):
        root = gr.unpack(gr.SOURCES["t4"], self.zip(rf.t4_entries("v0.1.0")), str(self.dir / "t4"),
                         dict(version="0.1.0", tag="v0.1.0"))
        self.assertEqual(os.listdir(self.dir / "t4"), ["T4"])
        self.assertTrue(os.path.isfile(os.path.join(root, "tools", "build_game.ps1")))
        broken = [e for e in rf.t4_entries("v0.1.0") if "runtime/" not in e[0]]
        with self.assertRaises(gr.ReleaseError):
            gr.unpack(gr.SOURCES["t4"], self.zip(broken), str(self.dir / "t4b"), dict(version="0.1.0", tag="v0.1.0"))


class InstallUpdate(Env):
    def install(self, game="t5dr", channel="stable"):
        return gr.install_fresh(game, self.offer(game, channel), str(self.dir / "games"))

    def test_fresh_install_marks_its_own_install(self):
        self.gh.add_t5dr("1.2.0")
        root = self.install()
        self.assertEqual(Path(root).name, "T5DR-Online-1.2.0")
        self.assertTrue(gr.managed("t5dr", root))
        self.assertEqual(gr.installed_version("t5dr", root), "1.2.0")
        self.assertEqual(sorted(p.name for p in (self.dir / "games").iterdir()), ["T5DR-Online-1.2.0"])   # no staging left
        with self.assertRaises(gr.ReleaseError) as raised:
            self.install()
        self.assertEqual(raised.exception.key, "@setup.err_exists")

    def test_not_enough_space_or_no_write_access_is_said_before_downloading(self):
        self.gh.add_t5dr("1.2.0")
        with mock.patch.object(gr, "free_space", return_value=10):
            self.assertEqual(gr.check_target(gr.SOURCES["t5dr"], self.offer(), str(self.dir)), "@setup.err_space")
        before = len(self.gh.requests)
        with mock.patch.object(gr, "free_space", return_value=10), self.assertRaises(gr.ReleaseError):
            self.install()
        self.assertFalse(any("/releases/download/" in r for r in self.gh.requests[before:]))

    def player_files(self, root):
        root = Path(root)
        (root / "native" / "build").mkdir(parents=True)
        (root / "native" / "build" / "t5dr_build.json").write_text(json.dumps(dict(code_id="0123456789abcdef")), encoding="utf-8")
        (root / "native" / "replays").mkdir()
        (root / "native" / "replays" / "r1.t5r").write_text("replay", encoding="utf-8")
        (root / "launcher.json").write_text(json.dumps(dict(language="de")), encoding="utf-8")
        (root / "gamedata").mkdir()
        (root / "gamedata" / "save.bin").write_text("save", encoding="utf-8")

    def test_update_keeps_settings_saves_replays_and_build_and_says_when_to_build_again(self):
        self.gh.add_t5dr("1.2.0")
        root = self.install()
        self.player_files(root)
        self.gh.add_t5dr("1.2.1")                                  # same code id: the built game stays valid
        result = gr.update_in_place("t5dr", self.offer(), root)
        self.assertEqual(result, dict(version="1.2.1", rebuild=False, restart=True))
        self.assertEqual(gr.installed_version("t5dr", root), "1.2.1")
        self.assertIn("1.2.1", (Path(root) / "launcher" / "core.py").read_text(encoding="utf-8"))
        self.assertEqual(json.loads((Path(root) / "launcher.json").read_text(encoding="utf-8")), dict(language="de"))
        self.assertTrue((Path(root) / "native" / "replays" / "r1.t5r").is_file())
        self.assertTrue((Path(root) / "gamedata" / "save.bin").is_file())
        self.assertFalse((self.dir / "games" / ".T5DR-Online-1.2.0.openrecomp-update").exists())
        self.gh.add_t5dr("1.3.0", code_id="fedcba9876543210")     # new code: build again
        self.assertTrue(gr.update_in_place("t5dr", self.offer(), root)["rebuild"])
        with self.assertRaises(gr.ReleaseError) as raised:
            gr.update_in_place("t5dr", self.offer(), root)
        self.assertEqual(raised.exception.key, "@setup.err_not_newer")

    def test_failed_exchange_puts_the_old_files_back(self):
        self.gh.add_t5dr("1.2.0")
        root = self.install()
        self.player_files(root)
        self.gh.add_t5dr("1.2.1")
        real = gr._move
        calls = []

        def flaky(a, b, timeout=20.0):
            calls.append(a)
            if len(calls) == 3:
                raise PermissionError(5, "in use")
            return real(a, b, timeout)
        with mock.patch.object(gr, "_move", side_effect=flaky), self.assertRaises(gr.ReleaseError) as raised:
            gr.update_in_place("t5dr", self.offer(), root)
        self.assertEqual(raised.exception.key, "@setup.err_busy")
        self.assertEqual(gr.installed_version("t5dr", root), "1.2.0")
        self.assertIn("1.2.0", (Path(root) / "launcher" / "core.py").read_text(encoding="utf-8"))
        self.assertTrue((Path(root) / "launcher.json").is_file())

    def test_failed_rollback_keeps_the_backup_and_the_next_check_puts_the_old_files_back(self):
        self.gh.add_t5dr("1.2.0")
        root = self.install()
        self.player_files(root)
        self.gh.add_t5dr("1.2.1")
        stage = Path(gr.update_stage(root))
        real = gr._move
        calls = []

        def locked(a, b, timeout=20.0):
            if os.path.dirname(b) == os.path.abspath(root) and "backup" not in a:     # a new item going in
                calls.append(a)
                if len(calls) == 2:
                    raise PermissionError(5, "in use")         # the second new item cannot go in
            elif calls and os.path.dirname(a) == os.path.abspath(root):
                raise PermissionError(5, "still in use")       # the first new one cannot leave: rollback fails too
            return real(a, b, timeout)
        with mock.patch.object(gr, "_move", side_effect=locked), self.assertRaises(gr.ReleaseError) as raised:
            gr.update_in_place("t5dr", self.offer(), root)
        self.assertEqual(raised.exception.key, "@setup.err_restore")
        self.assertTrue(gr.interrupted_update(root))
        self.assertTrue(list((stage / "backup").iterdir()))     # the recovery copy is still there
        # The next check (on the worker) finishes the rollback: the old version is back, player files untouched.
        setup = gs.GameSetup({}, worker=lambda fn: fn())
        setup.check("t5dr", root, force=False)
        [(_, kind, _, error)] = setup.poll()
        self.assertEqual((kind, error), ("check", None))
        self.assertFalse(stage.exists())
        self.assertEqual(gr.installed_version("t5dr", root), "1.2.0")
        self.assertEqual(setup.view("t5dr")["installed"], "1.2.0")
        self.assertIn("1.2.0", (Path(root) / "launcher" / "core.py").read_text(encoding="utf-8"))
        self.assertTrue((Path(root) / "launcher.json").is_file())
        self.assertTrue((Path(root) / "gamedata" / "save.bin").is_file())
        self.assertEqual(gr.update_in_place("t5dr", self.offer(), root)["version"], "1.2.1")

    def test_recovery_while_still_locked_keeps_the_backup_and_an_update_refuses(self):
        self.gh.add_t5dr("1.2.0")
        root = self.install()
        self.gh.add_t5dr("1.2.1")
        real = gr._move
        calls = []

        def locked(a, b, timeout=20.0):
            if os.path.dirname(b) == os.path.abspath(root) and "backup" not in a:     # a new item going in
                calls.append(a)
                if len(calls) == 2:
                    raise PermissionError(5, "in use")
            elif calls and os.path.dirname(a) == os.path.abspath(root):
                raise PermissionError(5, "still in use")
            return real(a, b, timeout)
        with mock.patch.object(gr, "_move", side_effect=locked):
            with self.assertRaises(gr.ReleaseError):
                gr.update_in_place("t5dr", self.offer(), root)
            with self.assertRaises(gr.ReleaseError) as raised:
                gr.update_in_place("t5dr", self.offer(), root)
        self.assertEqual(raised.exception.key, "@setup.err_restore")
        self.assertTrue(gr.interrupted_update(root))
        self.assertTrue(gr.recover_update("t5dr", root))
        self.assertEqual(gr.installed_version("t5dr", root), "1.2.0")

    def test_a_complete_exchange_left_behind_keeps_the_new_files(self):
        self.gh.add_t5dr("1.2.0")
        root = self.install()
        self.gh.add_t5dr("1.2.1")
        with mock.patch.object(gr.shutil, "rmtree"):       # the launcher stopped right after the exchange
            gr.update_in_place("t5dr", self.offer(), root)
        self.assertTrue(gr.interrupted_update(root))
        self.assertTrue(gr.recover_update("t5dr", root))
        self.assertFalse(Path(gr.update_stage(root)).exists())
        self.assertEqual(gr.installed_version("t5dr", root), "1.2.1")

    def test_cancel_after_unpacking_stops_before_the_exchange(self):
        self.gh.add_t5dr("1.2.0")
        root = self.install()
        self.gh.add_t5dr("1.2.1")
        cancel = threading.Event()

        def progress(step, done, total):
            if step == "unpack":
                cancel.set()                    # pressed while the last file was unpacked
        with self.assertRaises(gr.ReleaseError) as raised:
            gr.update_in_place("t5dr", self.offer(), root, progress=progress, cancel=cancel)
        self.assertEqual(raised.exception.key, "@setup.cancelled")
        self.assertEqual(gr.installed_version("t5dr", root), "1.2.0")
        self.assertFalse(Path(gr.update_stage(root)).exists())

    def test_t4_update_keeps_its_build_and_asks_for_a_new_one_when_the_sources_changed(self):
        self.gh.add_t4("v0.1.0-beta.1")
        root = self.install("t4", "prerelease")
        self.assertEqual(Path(root).name, "T4")
        (Path(root) / "out").mkdir()
        (Path(root) / "out" / "game.exe.txt").write_text("built", encoding="utf-8")
        (Path(root) / "settings.json").write_text("{}", encoding="utf-8")
        self.gh.add_t4("v0.1.0-beta.2", marker="changed")
        result = gr.update_in_place("t4", self.offer("t4", "prerelease"), root)
        self.assertTrue(result["rebuild"])
        self.assertTrue(gr.rebuild_required("t4", root))
        self.assertTrue((Path(root) / "out" / "game.exe.txt").is_file())
        self.assertTrue((Path(root) / "settings.json").is_file())
        gr.clear_rebuild("t4", root)
        self.assertFalse(gr.rebuild_required("t4", root))


class Worker(Env):
    """GameSetup's state as the launcher's tick sees it (worker threads run inline here)."""

    def setup_(self, config=None):
        return gs.GameSetup({} if config is None else config, worker=lambda fn: fn())

    def test_check_install_and_update_flow(self):
        self.gh.add_t5dr("1.2.0")
        setup = self.setup_()
        self.assertTrue(setup.check("t5dr", None, force=True))
        setup.poll()
        view = setup.view("t5dr")
        self.assertEqual((view["phase"], view["latest"], view["required"]), ("ready", "1.2.0", False))
        self.assertTrue(setup.install("t5dr", str(self.dir / "games")))
        [(gid, kind, root, error)] = setup.poll()
        self.assertEqual((gid, kind, error), ("t5dr", "install", None))
        self.gh.add_t5dr("1.2.1")
        setup.check("t5dr", root, force=True)
        setup.poll()
        view = setup.view("t5dr")
        self.assertEqual((view["installed"], view["latest"], view["available"], view["required"]), ("1.2.0", "1.2.1", True, True))
        setup.update("t5dr", root)
        [(_, kind, result, error)] = setup.poll()
        self.assertEqual((kind, error, result["version"]), ("update", None, "1.2.1"))
        self.assertEqual(setup.view("t5dr")["phase"], "updated")

    def test_test_versions_follow_the_switch_and_the_cache_knows_the_channel(self):
        self.gh.add_t5dr("1.2.0")
        self.gh.add_t5dr("1.3.0-rc.1", prerelease=True)
        config = {}
        setup = self.setup_(config)
        setup.check("t5dr", None, force=True)
        setup.poll()
        self.assertEqual(setup.view("t5dr")["latest"], "1.2.0")
        config["game_prereleases"] = True
        setup.check("t5dr", None)                     # cached for the stable channel only: asks again
        setup.poll()
        self.assertEqual((setup.view("t5dr")["latest"], setup.view("t5dr")["offer"]["prerelease"]), ("1.3.0-rc.1", True))

    def test_the_lobbys_announced_release_makes_an_update_needed(self):
        self.gh.add_t5dr("1.2.0")
        setup = self.setup_()
        root = gr.install_fresh("t5dr", self.offer(), str(self.dir / "games"))
        announced = self.gh.add_t5dr("1.2.1")
        self.gh.releases[rf.T5DR_REPO].pop()          # GitHub's latest still says 1.2.0 (cached elsewhere)
        setup.check("t5dr", root, force=True)
        setup.poll()
        self.assertFalse(setup.view("t5dr")["required"])
        self.assertTrue(setup.note_lobby("t5dr", announced, root))
        view = setup.view("t5dr")
        self.assertEqual((view["required"], view["latest"], view["source"]), (True, "1.2.1", "lobby"))
        self.assertFalse(setup.note_lobby("t5dr", announced, root))          # same data: nothing new
        self.assertFalse(setup.note_lobby("t5dr", dict(announced, draft=True), root))

    def test_a_t4_tree_without_a_version_is_offered_the_newest_release(self):
        self.gh.add_t4("v0.1.0-beta.1")
        root = gr.install_fresh("t4", self.offer("t4", "prerelease"), str(self.dir / "games"))
        os.remove(os.path.join(root, gr.MARKER))          # as Setup or a bundle placed it: no version stamp
        (Path(root) / "settings.json").write_text("{}", encoding="utf-8")
        self.gh.add_t4("v0.1.0-beta.2", marker="changed")
        setup = self.setup_()
        setup.check("t4", root, force=True)
        setup.poll()
        view = setup.view("t4")
        self.assertEqual((view["installed"], view["latest"], view["available"], view["required"]),
                         ("", "0.1.0-beta.2", True, False))
        self.assertTrue(setup.update("t4", root))
        [(_, kind, result, error)] = setup.poll()
        self.assertEqual((kind, error, result["version"]), ("update", None, "0.1.0-beta.2"))
        self.assertEqual(gr.installed_version("t4", root), "0.1.0-beta.2")
        self.assertTrue((Path(root) / "settings.json").is_file())
        # A developer's git checkout is never offered a release over its own files.
        os.remove(os.path.join(root, gr.MARKER))
        (Path(root) / ".git").mkdir()
        setup.check("t4", root, force=True)
        setup.poll()
        self.assertFalse(setup.view("t4")["available"])

    def test_a_failure_is_a_plain_message_and_the_worker_never_dies(self):
        setup = gs.GameSetup({}, worker=lambda fn: fn(), latest=mock.Mock(side_effect=RuntimeError("boom")))
        setup.check("t5dr", None, force=True)
        [(_, _, _, error)] = setup.poll()
        self.assertEqual(error[0], "@setup.err_unknown")
        self.assertEqual(setup.view("t5dr")["phase"], "error")

    def test_cancel_during_download_changes_nothing(self):
        self.gh.add_t5dr("1.2.0", zip_data=os.urandom(3_000_000))
        setup = gs.GameSetup({}, worker=lambda fn: threading.Thread(target=fn, daemon=True).start())
        setup.check("t5dr", None, force=True)
        for _ in range(200):
            if setup.poll():
                break
            threading.Event().wait(0.02)
        setup.install("t5dr", str(self.dir / "games"))
        setup.cancel("t5dr")
        events = []
        for _ in range(500):
            events += setup.poll()
            if events:
                break
            threading.Event().wait(0.02)
        self.assertEqual(events[0][3][0], "@setup.cancelled")
        self.assertEqual(setup.view("t5dr")["phase"], "ready")
        self.assertEqual(list((self.dir / "games").iterdir()), [])


class Shutdown(Env):
    def test_update_threads_are_waited_for_and_asked_to_stop_at_exit(self):
        setup = gs.GameSetup({})
        started, release = threading.Event(), threading.Event()
        seen = []

        def update(gid, offer, root, progress=None, cancel=None):
            started.set()
            release.wait(5)
            seen.append(cancel.is_set())
            return dict(version="1.2.1")
        setup.update_fn = update
        setup.offers["t5dr"] = dict(version="1.2.1", zip=dict(size=1))
        self.assertTrue(setup.update("t5dr", str(self.dir)))
        self.assertTrue(started.wait(5))
        self.assertEqual(len(setup.jobs), 1)
        self.assertFalse(setup.jobs[0].daemon)            # Python itself waits for it at exit
        threading.Timer(0.2, release.set).start()
        self.assertTrue(setup.shutdown(5))
        self.assertEqual(seen, [True])
        checks = gs.GameSetup({}, latest=lambda src, channel: None)
        checks.check("t5dr", None, force=True)
        self.assertEqual(checks.jobs, [])                 # a check is no job to wait for


class LobbyRelease(unittest.TestCase):
    """The lobby's announced release reaches game setup from the game's own online client, never by a new call."""

    def test_from_the_welcome_or_from_an_old_builds_refusal(self):
        from types import SimpleNamespace
        from openrecomp.adapters.t5_online import Online
        data = dict(tag_name="v1.2.1", assets=[])
        holder = SimpleNamespace(_online_client=SimpleNamespace(welcome=dict(latest_release=data)))
        self.assertIs(Online.lobby_release(holder), data)
        holder = SimpleNamespace(_online_client=None)
        self.assertIsNone(Online.lobby_release(holder))
        refusal = RuntimeError("build not accepted")
        refusal.code, refusal.extra = "version_mismatch", dict(latest_release=data)
        with mock.patch("openrecomp.adapters.t5_features.enabled", return_value=False):
            self.assertEqual(Online._online_error(holder, refusal), "@online.version_mismatch")
        self.assertIs(Online.lobby_release(holder), data)


class Discovery(unittest.TestCase):
    def test_t5dr_beside_the_launchers_folder_is_found_without_a_saved_root(self):
        from openrecomp.adapters import t5dr
        beside = os.path.join(os.path.dirname(str(ROOT)), "T5DR-Online-1.2.1")
        with mock.patch.object(t5dr.glob, "glob", side_effect=lambda pattern: [beside] if "T5DR-Online-" in pattern
                               and os.path.dirname(pattern) == os.path.dirname(str(ROOT)) else []),                 mock.patch.object(t5dr, "install_root", side_effect=lambda path: path if path == beside else None),                 mock.patch.dict(os.environ, {"OPENRECOMP_T5DR_ROOT": ""}):
            self.assertEqual(t5dr.find_root(dict(id="t5dr", locations=[]), {}), beside)


class Texts(unittest.TestCase):
    def test_every_error_and_step_has_a_text_in_every_language(self):
        source = (ROOT / "openrecomp" / "game_releases.py").read_text(encoding="utf-8")
        keys = set(__import__("re").findall(r'"@(setup\.[a-z_]+)"', source))
        keys.update(("setup.step_download", "setup.step_unpack", "setup.step_swap", "setup.err_unknown"))
        for code in i18n.LANGUAGES:
            catalog = i18n.catalog(code)
            for key in keys:
                self.assertIn(key, catalog, (code, key))

    def test_sources_are_the_owners_public_repositories(self):
        self.assertEqual(gr.SOURCES["t5dr"].repository, "TheWishin/T5DROnline")
        self.assertEqual(gr.SOURCES["t4"].repository, "TheWishin/Tekken4Recomp")
        self.assertEqual(gr.SOURCES["t5dr"].keys, ("b47cc1692fbdb91cb7e13a98edd56e99ceea307e693a151b05688ca8f9e67425",))
        self.assertEqual(hashlib.sha256(bytes.fromhex(gr.SOURCES["t5dr"].keys[0])).hexdigest()[:16], "c2acdfbc80f3c4c2")


if __name__ == "__main__":
    unittest.main()
