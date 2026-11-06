"""Offline updater tests: published crypto vector, fake release bytes and fake processes."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

from openrecomp import updater as u
from tools import release_sign


PUBLIC = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
CHANNEL = u.Channel("example/OpenRecomp", "12345", "openrecomp-test", (PUBLIC,))


def release(version="v1.2.3"):
    names = (f"OpenRecomp-{version}.zip", "SHA256SUMS", "SHA256SUMS.sig")
    return dict(tag_name=version, draft=False, prerelease=False, body="A launcher update.",
                assets=[dict(name=n, size=100, digest="sha256:" + "a" * 64,
                             browser_download_url=f"https://github.com/{CHANNEL.repository}/releases/download/{version}/{n}") for n in names])


def program(path, version="v1.2.3"):
    for item in u.REQUIRED_ITEMS:
        target = path / item
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fake program", encoding="utf-8")
    (path / "release.json").write_text(json.dumps(dict(project=u.PROJECT, channel=CHANNEL.name, version=version)), encoding="utf-8")


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "install"
        self.root.mkdir()

    def archive(self, entries):
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as archive:
            for name, value in entries.items():
                entry = zipfile.ZipInfo(name)
                # ZipInfo normalizes Windows separators; keep the unsafe name under test.
                entry.filename = name
                archive.writestr(entry, value)
        return raw.getvalue()

    def test_ed25519_published_rfc8032_vector_and_tampering(self):
        signature = bytes.fromhex("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555f"
                                  "b8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")
        public = bytes.fromhex(PUBLIC)
        self.assertTrue(u.verify_ed25519(public, b"", signature))
        self.assertFalse(u.verify_ed25519(public, b"changed", signature))
        self.assertFalse(u.verify_ed25519(public, b"", signature[:32] + u._L.to_bytes(32, "little")))
        self.assertFalse(u.verify_ed25519(bytes.fromhex("01" + "00" * 31), b"", signature))

    def test_offline_signer_roundtrip_with_ephemeral_memory_only_seed(self):
        seed = os.urandom(32)
        public = release_sign.public_key(seed)
        message = u.signature_message(CHANNEL.name, "v1.2.3", b"checksums\n")
        signature = release_sign.sign(seed, message)
        self.assertTrue(u.verify_ed25519(public, message, signature))
        self.assertFalse(u.verify_ed25519(public, message + b"changed", signature))
        with self.assertRaises(ValueError):
            release_sign._outside_repository(Path(__file__))

    def test_incomplete_configuration_refuses_before_network(self):
        with mock.patch.multiple(u, RELEASE_REPOSITORY="", RELEASE_REPOSITORY_ID="", RELEASE_CHANNEL="",
                                 RELEASE_PUBLIC_KEYS=()), \
                mock.patch.object(u, "_open") as opener, self.assertRaises(u.UpdateError) as error:
            u.check_release(self.root)
        self.assertEqual(error.exception.key, "updates_unconfigured")
        opener.assert_not_called()

    def test_configured_channel_is_the_launchers_own_repository_and_key(self):
        channel = u.configured_channel()
        self.assertEqual((channel.repository, channel.repository_id, channel.name),
                         ("TheWishin/OpenRecomp-FGC", "1439720330", "openrecomp-fgc"))
        self.assertEqual(len(channel.public_keys), 1)
        self.assertEqual(hashlib.sha256(bytes.fromhex(channel.public_keys[0])).hexdigest()[:16], "240b33a1229ca79b")
        # A test key counts only with a fake GitHub on this PC.
        with mock.patch.dict(os.environ, {u.TEST_KEY_ENV: "ab" * 32, u.TEST_ENV: ""}):
            self.assertEqual(len(u.configured_channel().public_keys), 1)
        with mock.patch.dict(os.environ, {u.TEST_KEY_ENV: "ab" * 32, u.TEST_ENV: "http://example.com:80"}):
            self.assertEqual(len(u.configured_channel().public_keys), 1)
        with mock.patch.dict(os.environ, {u.TEST_KEY_ENV: "ab" * 32, u.TEST_ENV: "http://127.0.0.1:8123"}):
            self.assertEqual(u.configured_channel().public_keys[-1], "ab" * 32)

    def test_only_plain_versions(self):
        self.assertEqual(u.version_key("v2.10.0")[:3], (2, 10, 0))
        for value in ("2.0.0", "V2.0.0", "v2.0.0+build", "v02.0.0", "v2.0.0\n", "v2.0.0-", "v2.0.0-01",
                      "v2.0.0-beta..1", "v2.0.0-b\u00e9ta", "v1\u0662.0.0", "v1.2\u0662.0", "v1.2.3\u0662"):
            with self.subTest(value=value):
                self.assertIsNone(u.version_key(value))
                with self.assertRaises(u.UpdateError):
                    u.parse_release(release(value), CHANNEL)
        with self.assertRaises(u.UpdateError):             # a test version is never offered on the stable channel
            u.parse_release(dict(release("v2.0.0-rc1"), prerelease=True), CHANNEL)

    def test_test_versions_order_and_need_matching_prerelease_flag(self):
        order = ["v1.0.0", "v1.1.0-beta.1", "v1.1.0-beta.2", "v1.1.0-beta.10", "v1.1.0-rc.1", "v1.1.0", "v1.1.1"]
        self.assertEqual(sorted(order, key=u.version_key), order)
        test = dict(release("v1.3.0-beta.1"), prerelease=True)
        self.assertEqual(u.parse_release(test, CHANNEL, prereleases=True)["version"], "v1.3.0-beta.1")
        for bad in (dict(test, prerelease=False), dict(test, draft=True)):
            with self.subTest(bad=bad["tag_name"]), self.assertRaises(u.UpdateError):
                u.parse_release(bad, CHANNEL, prereleases=True)
        # 0.1.4: a plain tag marked pre-release (the owner publishes every release as a pre-release first) is a
        # test version: offered with prereleases=True, never on the stable channel.
        plain_test = dict(release("v1.3.0"), prerelease=True)
        self.assertTrue(u.parse_release(plain_test, CHANNEL, prereleases=True)["test"])
        self.assertFalse(u.parse_release(release("v1.3.0"), CHANNEL, prereleases=True)["test"])
        with self.assertRaises(u.UpdateError):
            u.parse_release(plain_test, CHANNEL)

    def test_release_offers_and_release_for_a_game_that_needs_a_newer_launcher(self):
        program(self.root, "v0.1.2")
        listing = [dict(release("v0.1.4"), prerelease=True), dict(release("v0.1.3"), prerelease=True),
                   release("v0.1.2"), dict(release("v0.2.0"), draft=True)]
        reply = lambda *a, **k: io.BytesIO(json.dumps(listing).encode())
        with mock.patch.object(u, "_open", side_effect=reply):
            stable, test = u.release_offers(self.root, CHANNEL)
            self.assertIsNone(stable)                                  # nothing stable above 0.1.2
            self.assertEqual(test["version"], "v0.1.4")
            self.assertEqual(u.release_for(self.root, "0.1.4", CHANNEL)["version"], "v0.1.4")
            self.assertIsNone(u.release_for(self.root, "0.1.5", CHANNEL))
        listing.append(release("v0.1.5"))                             # a stable one at/above the need wins
        with mock.patch.object(u, "_open", side_effect=reply):
            self.assertEqual(u.release_for(self.root, "0.1.4", CHANNEL)["version"], "v0.1.5")

    def test_check_with_test_versions_picks_the_newest_published_one(self):
        program(self.root, "v1.0.0")
        listing = [dict(release("v1.3.0-beta.1"), prerelease=True), release("v1.2.3"),
                   dict(release("v9.0.0"), draft=True), dict(release("v1.4.0-beta.1"), prerelease=True, assets=[])]
        with mock.patch.object(u, "_open", return_value=io.BytesIO(json.dumps(listing).encode())) as opener:
            self.assertEqual(u.check_release(self.root, CHANNEL, prereleases=True)["version"], "v1.3.0-beta.1")
        self.assertTrue(opener.call_args.args[0].endswith(f"/repos/{CHANNEL.repository}/releases?per_page=30"))
        with mock.patch.object(u, "_open", return_value=io.BytesIO(json.dumps(listing[1]).encode())) as opener:
            self.assertEqual(u.check_release(self.root, CHANNEL)["version"], "v1.2.3")
        self.assertTrue(opener.call_args.args[0].endswith(f"/repos/{CHANNEL.repository}/releases/latest"))
        missing = u.urllib.error.HTTPError("https://api.github.com/x", 404, "Not Found", {}, None)
        with mock.patch.object(u, "_open", side_effect=missing):
            self.assertIsNone(u.check_release(self.root, CHANNEL))     # no release published yet: up to date
        refused = u.urllib.error.HTTPError("https://api.github.com/x", 403, "rate limited", {}, None)
        with mock.patch.object(u, "_open", side_effect=refused), self.assertRaises(u.UpdateError):
            u.check_release(self.root, CHANNEL)

    def test_release_rejects_test_duplicate_and_foreign_assets(self):
        self.assertEqual(u.parse_release(release(), CHANNEL)["version"], "v1.2.3")
        for mutate in (lambda d: d.update(prerelease=True), lambda d: d.update(draft=True),
                       lambda d: d["assets"].append(d["assets"][0]),
                       lambda d: d["assets"][0].update(browser_download_url="https://github.com/other/project/releases/download/v1.2.3/OpenRecomp-v1.2.3.zip"),
                       lambda d: d["assets"][0].update(digest="")):
            data = release()
            mutate(data)
            with self.assertRaises(u.UpdateError):
                u.parse_release(data, CHANNEL)

    def test_check_only_offers_later_published_release(self):
        program(self.root, "v1.0.0")
        with mock.patch.object(u, "_open", return_value=io.BytesIO(json.dumps(release()).encode())):
            self.assertEqual(u.check_release(self.root, CHANNEL)["version"], "v1.2.3")
        program(self.root, "v2.0.0")
        with mock.patch.object(u, "_open", return_value=io.BytesIO(json.dumps(release()).encode())):
            self.assertIsNone(u.check_release(self.root, CHANNEL))

    def test_download_limit_refuses_before_returning_unbounded_bytes(self):
        with mock.patch.object(u, "_open", return_value=io.BytesIO(b"too large")), self.assertRaises(u.UpdateError):
            u._download("fake", CHANNEL, 1)

    def test_urls_bound_to_repository_and_storage_id(self):
        good = "https://github.com/example/OpenRecomp/releases/download/v1.2.3/a.zip"
        self.assertTrue(u.url_allowed(good, CHANNEL))
        self.assertTrue(u.url_allowed("https://release-assets.githubusercontent.com/github-production-release-asset/12345/token", CHANNEL))
        for bad in (good.replace("https:", "http:"), good.replace("github.com", "github.com.evil"),
                    good.replace("github.com", "user@github.com"), good.replace("OpenRecomp", "T5DROnline"),
                    good.replace("/a.zip", "/%2e%2e/a.zip"), "https://objects.githubusercontent.com/github-production-release-asset/999/token"):
            self.assertFalse(u.url_allowed(bad, CHANNEL), bad)
        handler = u._Redirects(CHANNEL, "download")
        request = u.urllib.request.Request(good)
        with self.assertRaises(u.UpdateError):
            handler.redirect_request(request, None, 302, "redirect", {}, "https://example.invalid/a")

    def test_signature_binds_project_context_channel_version_and_exact_sums(self):
        sums = b"a" * 64 + b"  OpenRecomp-v1.2.3.zip\n"
        metadata = dict(algorithm="ed25519", channel=CHANNEL.name, version="v1.2.3",
                        key_id=hashlib.sha256(bytes.fromhex(PUBLIC)).hexdigest()[:16], signature="aa" * 64)
        with mock.patch.object(u, "verify_ed25519", return_value=True) as verify:
            u.verify_signature(json.dumps(metadata), sums, dict(version="v1.2.3"), CHANNEL)
        self.assertEqual(verify.call_args.args[1], u.signature_message(CHANNEL.name, "v1.2.3", sums))
        for field, value in (("channel", "t5dr"), ("version", "v9.9.9"), ("key_id", "0" * 16), ("algorithm", "none")):
            bad = dict(metadata, **{field: value})
            with mock.patch.object(u, "verify_ed25519", return_value=True), self.assertRaises(u.UpdateError):
                u.verify_signature(json.dumps(bad), sums, dict(version="v1.2.3"), CHANNEL)
        with self.assertRaises(u.UpdateError):
            u.verify_signature(json.dumps(metadata), sums, dict(version="v1.2.3"), CHANNEL)

    def test_archive_refuses_traversal_case_collisions_devices_and_player_data(self):
        prefix = u.ARCHIVE_TOP + "/"
        bad_entries = ["../escape", "openrecomp/../../escape", "openrecomp/./bad", "settings.json", "portable/CON.txt", "portable/COM¹.txt",
                       "portable/bad:stream", "portable/space ", "portable\\escape", "/absolute"]
        for name in bad_entries:
            with self.subTest(path=name):
                raw = self.archive({prefix + name: b"fake"})
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    self.assertEqual(archive.infolist()[0].orig_filename, prefix + name)
                    with self.assertRaises(u.UpdateError):
                        u._archive_members(archive, "v1.2.3")
        raw = self.archive({prefix + "openrecomp/A.py": b"a", prefix + "openrecomp/a.py": b"b"})
        with zipfile.ZipFile(io.BytesIO(raw)) as archive, self.assertRaises(u.UpdateError):
            u._archive_members(archive, "v1.2.3")

    def test_archive_refuses_symlink(self):
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as archive:
            link = zipfile.ZipInfo(u.ARCHIVE_TOP + "/openrecomp/link")
            link.external_attr = (0o120777 << 16)
            archive.writestr(link, "outside")
        with zipfile.ZipFile(io.BytesIO(raw.getvalue())) as archive, self.assertRaises(u.UpdateError):
            u._archive_members(archive, "v1.2.3")

    def staged(self):
        staged = u._work_root(self.root) / "transaction" / "new"
        staged.mkdir(parents=True)
        program(staged)
        return staged

    def test_home_inside_program_is_refused(self):
        with mock.patch.dict(os.environ, OPENRECOMP_HOME=str(self.root / "openrecomp" / "settings")), self.assertRaises(u.UpdateError):
            u.stage_update(self.root, dict(version="v1.2.3"), CHANNEL)

    def test_stage_verifies_checksums_size_and_manifest(self):
        source = Path(self.temp.name) / "source"
        source.mkdir()
        program(source)
        entries = {u.ARCHIVE_TOP + "/" + str(p.relative_to(source)).replace("\\", "/"): p.read_bytes()
                   for p in source.rglob("*") if p.is_file()}
        archive = self.archive(entries)
        digest = hashlib.sha256(archive).hexdigest()
        offered = dict(version="v1.2.3", sums_url="sums", sig_url="sig", zip_url="zip", digest=digest, size=len(archive))
        sums = f"{digest}  OpenRecomp-v1.2.3.zip\n".encode()
        def download(url, channel, limit, destination=None):
            if destination:
                Path(destination).write_bytes(archive)
                return len(archive)
            return sums if url == "sums" else b"signature"
        with mock.patch.object(u, "_download", side_effect=download), mock.patch.object(u, "verify_signature") as verify:
            staged = u.stage_update(self.root, offered, CHANNEL)
        self.assertTrue((staged / "run.cmd").is_file())
        verify.assert_called_once()
        with mock.patch.object(u, "_download", side_effect=download), mock.patch.object(u, "verify_signature"), self.assertRaises(u.UpdateError):
            u.stage_update(self.root, dict(offered, digest="0" * 64), CHANNEL)
        self.assertEqual(len(list(u._work_root(self.root).iterdir())), 1)

    def test_manifest_rejects_other_project_and_channel(self):
        program(self.root)
        for key in ("project", "channel", "version"):
            info = dict(project=u.PROJECT, channel=CHANNEL.name, version="v1.2.3")
            info[key] = "foreign"
            (self.root / "release.json").write_text(json.dumps(info))
            with self.assertRaises(u.UpdateError):
                u._manifest(self.root, dict(version="v1.2.3"), CHANNEL)

    def transaction(self):
        program(self.root, "v1.0.0")
        (self.root / "settings.json").write_text("player settings")
        staged = self.staged()
        seed = os.urandom(32)
        public = release_sign.public_key(seed)
        self.channel = u.Channel(CHANNEL.repository, CHANNEL.repository_id, CHANNEL.name, (public.hex(),))
        archive_path = staged.parent / "release.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            for source in staged.rglob("*"):
                if source.is_file():
                    archive.write(source, u.ARCHIVE_TOP + "/" + source.relative_to(staged).as_posix())
        sums = (hashlib.sha256(archive_path.read_bytes()).hexdigest() + "  OpenRecomp-v1.2.3.zip\n").encode("ascii")
        signature = release_sign.sign(seed, u.signature_message(self.channel.name, "v1.2.3", sums))
        (staged.parent / "SHA256SUMS").write_bytes(sums)
        (staged.parent / "SHA256SUMS.sig").write_text(json.dumps(dict(algorithm="ed25519",
            channel=self.channel.name, version="v1.2.3", key_id=hashlib.sha256(public).hexdigest()[:16],
            signature=signature.hex())), encoding="utf-8")
        path = staged.parent / "plan.json"
        path.write_text(json.dumps(dict(root=str(self.root), staged=str(staged), version="v1.2.3", channel=CHANNEL.name,
                                        pid=123, token="a" * 64)))
        return path, staged

    def test_healthy_confirmation_keeps_update_and_settings(self):
        path, staged = self.transaction()
        def restart(root, marker=None):
            Path(marker["path"]).write_text(json.dumps(dict(token=marker["token"])))
            return mock.Mock()
        with mock.patch.object(u, "configured_channel", return_value=self.channel):
            self.assertTrue(u.apply_plan(path, wait=0.1, alive=lambda p: False, processes=lambda r: [], restart=restart))
        self.assertEqual(u.local_version(self.root), "v1.2.3")
        self.assertEqual((self.root / "settings.json").read_text(), "player settings")

    def test_failed_start_rolls_back_and_restarts_old_version(self):
        path, staged = self.transaction()
        restarts = []
        def restart(root, marker=None):
            restarts.append(u.local_version(root))
            if marker:
                raise OSError("fake restart failure")
        with mock.patch.object(u, "configured_channel", return_value=self.channel), self.assertRaises(u.UpdateError):
            u.apply_plan(path, wait=0, alive=lambda p: False, processes=lambda r: [], restart=restart)
        self.assertEqual(restarts, ["v1.2.3", "v1.0.0"])
        self.assertEqual(u.local_version(self.root), "v1.0.0")
        self.assertEqual((self.root / "settings.json").read_text(), "player settings")
        self.assertEqual(u.update_result(self.root)["status"], "rolled_back")
        self.assertIsNone(u.update_result(self.root))

    def test_failed_move_restores_old_program(self):
        path, staged = self.transaction()
        calls = []
        def move(source, target):
            calls.append((source, target))
            if len(calls) == 3:
                raise OSError("fake file locked")
            os.replace(source, target)
        with mock.patch.object(u, "configured_channel", return_value=self.channel), self.assertRaises(u.UpdateError):
            u.apply_plan(path, wait=0, alive=lambda p: False, processes=lambda r: [], restart=mock.Mock(), move=move)
        self.assertEqual(u.local_version(self.root), "v1.0.0")
        for item in u.REQUIRED_ITEMS:
            self.assertTrue((self.root / item).is_file())

    def test_unconfirmed_process_rolled_back_and_busy_install_unchanged(self):
        path, staged = self.transaction()
        proc = mock.Mock()
        proc.poll.return_value = 0
        with mock.patch.object(u, "configured_channel", return_value=self.channel), self.assertRaises(u.UpdateError):
            u.apply_plan(path, wait=0, alive=lambda p: False, processes=lambda r: [], restart=mock.Mock(return_value=proc))
        self.assertEqual(u.local_version(self.root), "v1.0.0")
        with mock.patch.object(u, "configured_channel", return_value=self.channel), self.assertRaises(u.UpdateError):
            u.apply_plan(path, wait=0, alive=lambda p: True, processes=lambda r: [], restart=mock.Mock())
        self.assertEqual(u.local_version(self.root), "v1.0.0")

    def test_confirm_only_writes_own_transaction(self):
        staged = self.staged()
        marker = staged.parent / "confirmed.json"
        with mock.patch.dict(os.environ, {u.CONFIRM_ENV: json.dumps(dict(path=str(marker), token="a" * 64))}):
            self.assertTrue(u.confirm_startup(self.root))
        with mock.patch.dict(os.environ, {u.CONFIRM_ENV: json.dumps(dict(path=str(self.root / "other.json"), token="a" * 64))}):
            self.assertFalse(u.confirm_startup(self.root))
        self.assertFalse((self.root / "other.json").exists())

    def test_restart_owns_private_python_instead_of_wrapper(self):
        with mock.patch.object(u.subprocess, "Popen") as spawn:
            u._restart(self.root, None, ["--windowed", "C:\\not-a-switch", "--x;evil"])
        command = spawn.call_args.args[0]
        # Setup's shortcut: the install's own portable pythonw, -B -m openrecomp, in the program folder.
        self.assertEqual(Path(command[0]), self.root / "portable" / "pythonw.exe")
        self.assertEqual(command[1:], ["-B", "-m", "openrecomp", "--windowed"])
        self.assertEqual(spawn.call_args.kwargs["cwd"], self.root)

    def test_live_unconfirmed_python_terminated_before_restore(self):
        path, staged = self.transaction()
        proc = mock.Mock()
        proc.poll.return_value = None
        restored = []
        def move(source, target):
            if source.parent.name == "backup":
                self.assertTrue(proc.wait.called)
                restored.append(source.name)
            os.replace(source, target)
        with mock.patch.object(u, "configured_channel", return_value=self.channel), self.assertRaises(u.UpdateError):
            u.apply_plan(path, wait=0, alive=lambda p: False, processes=lambda r: [], restart=mock.Mock(return_value=proc), move=move)
        proc.terminate.assert_called_once()
        self.assertTrue(restored)
        self.assertEqual(u.local_version(self.root), "v1.0.0")

    def test_failed_termination_still_attempts_restore_and_reports_recovery(self):
        path, staged = self.transaction()
        proc = mock.Mock()
        proc.poll.return_value = None
        proc.terminate.side_effect = OSError("fake access denied")
        with mock.patch.object(u, "configured_channel", return_value=self.channel), self.assertRaises(u.UpdateError):
            u.apply_plan(path, wait=0, alive=lambda p: False, processes=lambda r: [], restart=mock.Mock(return_value=proc))
        self.assertEqual(u.local_version(self.root), "v1.0.0")
        self.assertEqual(u.update_result(self.root)["status"], "recovery_required")

    def test_process_inspection_failure_restarts_unchanged_launcher(self):
        path, staged = self.transaction()
        restart = mock.Mock()
        with mock.patch.object(u, "configured_channel", return_value=self.channel), self.assertRaises(u.UpdateError):
            u.apply_plan(path, wait=0, alive=lambda p: False,
                         processes=mock.Mock(side_effect=OSError("fake process inspection race")), restart=restart)
        restart.assert_called_once_with(self.root)
        self.assertEqual(u.local_version(self.root), "v1.0.0")
        self.assertEqual(u.update_result(self.root)["status"], "unchanged")

    def test_busy_timeout_does_not_restart_a_still_running_launcher(self):
        path, staged = self.transaction()
        restart = mock.Mock()
        with mock.patch.object(u, "configured_channel", return_value=self.channel), self.assertRaises(u.UpdateError):
            u.apply_plan(path, wait=0, alive=lambda p: True, processes=lambda r: [], restart=restart)
        restart.assert_not_called()
        self.assertEqual(u.local_version(self.root), "v1.0.0")
