"""Third-party release checks never share the launcher's trust or install tree."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock
import zipfile

from openrecomp import game_updates as gu
from openrecomp import manifest as mf

ROOT = Path(__file__).resolve().parents[1]


def manifest():
    return dict(schema_version=1, id="sample", title="Sample recomp", numeral="R", accent="#123456",
                adapter="generic", platform="Console", author="Example author", repository="example/recomp",
                exe="app.exe", license="MIT", credits=["Example authors"],
                releases=dict(channel="stable", asset="recomp.zip", verification=dict(method="github-sha256")))


def archive(entries=None):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, data in entries or [("app.exe", b"inert test marker")]:
            entry = zipfile.ZipInfo(name)
            # ZipInfo normalizes Windows separators; keep the unsafe name under test.
            entry.filename = name
            z.writestr(entry, data)
    return out.getvalue()


class AuthorGameUpdates(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix=".test-updates-", dir=ROOT)
        self.addCleanup(self.folder.cleanup)
        self.home = Path(self.folder.name)
        self.env = mock.patch.dict(os.environ, OPENRECOMP_HOME=str(self.home))
        self.env.start()
        self.addCleanup(self.env.stop)
        self.m = manifest()
        self.config = dict(game_sources={"sample": dict(repository="example/recomp", author="Example author")})
        self.raw = archive()
        self.release = dict(tag_name="v1.2.3", draft=False, prerelease=False, body="Author release notes", assets=[dict(
            name="recomp.zip", size=len(self.raw), digest="sha256:" + hashlib.sha256(self.raw).hexdigest(),
            browser_download_url="https://github.com/example/recomp/releases/download/v1.2.3/recomp.zip")])
        self.fetch = mock.Mock(side_effect=self.read)
        self.service = gu.GameUpdates(self.config, fetch=self.fetch)

    def read(self, url, limit):
        if url.startswith("https://api.github.com/"):
            return json.dumps(self.release).encode()
        return self.raw

    def test_check_reads_metadata_only_and_install_is_separate(self):
        offer = self.service.check(self.m)
        self.assertEqual(offer["version"], "v1.2.3")
        self.assertEqual(self.fetch.call_count, 1)
        self.assertIn("api.github.com/repos/example/recomp/releases/latest", self.fetch.call_args.args[0])
        self.assertNotIn("roots", self.config)
        root = Path(self.service.install(self.m, offer))
        self.assertEqual((root / "app.exe").read_bytes(), b"inert test marker")
        self.assertEqual(self.config["roots"]["sample"], str(root))
        self.assertEqual(self.config["game_versions"]["sample"], "v1.2.3")
        self.assertFalse((self.home / "config.json").exists())

    def test_update_copies_declared_user_data_and_leaves_original(self):
        old = self.home / "existing"
        old.mkdir()
        (old / "settings.json").write_text('{"volume": 3}')
        (old / "saves").mkdir()
        (old / "saves" / "marker.txt").write_text("keep")
        self.config["roots"] = {"sample": str(old)}
        self.m["settings"] = dict(file="settings.json", cyclers=[])
        root = Path(self.service.install(self.m, self.service.check(self.m)))
        self.assertEqual((root / "settings.json").read_text(), '{"volume": 3}')
        self.assertEqual((old / "saves" / "marker.txt").read_text(), "keep")
        self.assertTrue(old.exists())

    def test_retry_after_unsaved_install_uses_a_fresh_version_folder(self):
        old = self.home / "old"
        old.mkdir()
        (old / "app.exe").write_bytes(b"previous inert marker")
        self.config["roots"] = {"sample": str(old)}
        self.config["game_versions"] = {"sample": "v1.0.0"}
        previous = copy.deepcopy(self.config)
        orphan = Path(self.service.install(self.m, self.service.check(self.m)))
        (orphan / "app.exe").write_bytes(b"changed inert marker")
        service = gu.GameUpdates(previous, fetch=self.fetch)
        root = Path(service.install(self.m, service.check(self.m)))
        self.assertNotEqual(root, orphan)
        self.assertEqual(root.parent, orphan.parent)
        self.assertEqual((root / "app.exe").read_bytes(), b"inert test marker")
        self.assertEqual((orphan / "app.exe").read_bytes(), b"changed inert marker")
        self.assertEqual((old / "app.exe").read_bytes(), b"previous inert marker")
        self.assertEqual(previous["roots"]["sample"], str(root))
        self.assertEqual(previous["game_versions"]["sample"], "v1.2.3")
        self.assertEqual(self.fetch.call_count, 4)

    def test_hash_mismatch_cannot_change_active_root(self):
        self.config["roots"] = {"sample": "unchanged"}
        offer = self.service.check(self.m)
        self.raw = self.raw[:-1] + b"x"
        with self.assertRaises(gu.GameUpdateError):
            self.service.install(self.m, offer)
        self.assertEqual(self.config["roots"]["sample"], "unchanged")
        self.assertFalse((self.home / "installs").exists())

    def test_mutated_or_unchecked_offers_rejected_before_download(self):
        offer = self.service.check(self.m)
        for key, value in (("url", "https://evil.invalid/recomp.zip"), ("repository", "other/game"),
                           ("sha256", "0" * 64), ("version", "v1.2.4"), ("channel", "prerelease")):
            altered = dict(offer, **{key: value})
            with self.subTest(key=key), self.assertRaises(gu.GameUpdateError):
                self.service.install(self.m, altered)
        with self.assertRaises(gu.GameUpdateError):
            gu.GameUpdates(self.config, self.fetch).install(self.m, offer)
        self.assertEqual(self.fetch.call_count, 1)

    def test_source_pin_and_manifest_changes_rejected(self):
        self.config["game_sources"]["sample"]["repository"] = "other/game"
        with self.assertRaises(gu.GameUpdateError):
            self.service.check(self.m)
        self.assertFalse(self.fetch.called)
        self.config["game_sources"]["sample"]["repository"] = "example/recomp"
        offer = self.service.check(self.m)
        altered = dict(self.m, args=["--different"])
        with self.assertRaises(gu.GameUpdateError):
            self.service.install(altered, offer)

    def test_release_rejects_foreign_asset_missing_digest_oversize_and_bad_version(self):
        cases = [dict(tag_name="v1.2"), dict(tag_name="v1.2.4-rc.1"), dict(draft=True)]
        for change in cases:
            old = copy.deepcopy(self.release)
            self.release.update(change)
            with self.subTest(change=change), self.assertRaises(gu.GameUpdateError):
                self.service.check(self.m)
            self.release = old
        for key, value in (("browser_download_url", "https://github.com/other/game/releases/download/v1.2.3/recomp.zip"),
                           ("digest", None), ("size", gu.MAX_ARCHIVE + 1), ("size", True)):
            old = copy.deepcopy(self.release)
            self.release["assets"][0][key] = value
            with self.subTest(key=key), self.assertRaises(gu.GameUpdateError):
                self.service.check(self.m)
            self.release = old

    def test_pin_hash_does_not_trust_github_digest(self):
        self.m["releases"]["verification"] = dict(method="sha256", sha256="0" * 64)
        with self.assertRaises(gu.GameUpdateError):
            self.service.install(self.m, self.service.check(self.m))

    def test_bounded_injected_response_and_duplicate_json(self):
        self.service.fetch = mock.Mock(return_value=b" " * (gu.MAX_METADATA + 1))
        with self.assertRaises(gu.GameUpdateError):
            self.service.check(self.m)
        self.service.fetch = mock.Mock(return_value=b'{"draft":false,"draft":true}')
        with self.assertRaises(gu.GameUpdateError):
            self.service.check(self.m)

    def test_archive_hostile_paths_symlinks_case_aliases_and_file_ancestors(self):
        entries = [[("../outside", b"x")], [("C:/outside", b"x")], [("dir\\x", b"x")],
                   [("NUL.txt", b"x")], [("x:ads", b"x")], [("x", b"1"), ("X", b"2")],
                   [("Dir/a", b"1"), ("dir/b", b"2")],
                   [("dir", b"1"), ("dir/file", b"2")]]
        for values in entries:
            with self.subTest(values=values):
                raw = archive(values)
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    self.assertEqual([entry.orig_filename for entry in z.infolist()], [name for name, _ in values])
                with self.assertRaises((gu.GameUpdateError, mf.ManifestError)):
                    gu.GameUpdates._extract(raw, self.home)
                self.assertEqual(list(self.home.iterdir()), [])
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as z:
            entry = zipfile.ZipInfo("link")
            entry.create_system = 3
            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(entry, "../outside")
        with self.assertRaises(gu.GameUpdateError):
            gu.GameUpdates._extract(out.getvalue(), self.home)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_unpack_size_and_entry_count_limited(self):
        with mock.patch.object(gu, "MAX_FILES", 1), self.assertRaises(gu.GameUpdateError):
            gu.GameUpdates._extract(archive([("a", b"a"), ("b", b"b")]), self.home)
        with mock.patch.object(gu, "MAX_UNPACKED", 1), self.assertRaises(gu.GameUpdateError):
            gu.GameUpdates._extract(self.raw, self.home)

    def test_release_versions_require_ascii_core_digits(self):
        for version in ("v1\u0662.0.0", "v1.2\u0662.0", "v1.2.3\u0662"):
            with self.subTest(version=version):
                with self.assertRaises(gu.GameUpdateError):
                    gu.version_key(version)
                self.release["tag_name"] = version
                self.release["assets"][0]["browser_download_url"] = (
                    f"https://github.com/example/recomp/releases/download/{version}/recomp.zip")
                with self.assertRaises(gu.GameUpdateError):
                    self.service.check(self.m)
                self.assertNotIn("sample", self.service.offers)
        for version, expected in (("v0.0.0", ((0, 0, 0), "")), ("v12.22.32", ((12, 22, 32), "")),
                                  ("v1.2.3-rc.10", ((1, 2, 3), "rc.10"))):
            with self.subTest(version=version):
                self.assertEqual(gu.version_key(version), expected)

    def test_versions_and_channel_do_not_downgrade(self):
        self.m["version"] = "v3.0.0"
        old = self.home / "old"
        old.mkdir()
        (old / "app.exe").write_bytes(b"inert marker")
        self.config["roots"] = {"sample": str(old)}
        self.assertIsNone(self.service.check(self.m))
        del self.m["version"]
        self.config["game_versions"] = {"sample": "v1.2.3"}
        self.assertIsNone(self.service.check(self.m))
        self.config["game_versions"]["sample"] = "v2.0.0"
        self.assertIsNone(self.service.check(self.m))
        self.m["releases"]["channel"] = "prerelease"
        self.config["game_versions"]["sample"] = "v2.0.0-rc.2"
        self.release["prerelease"] = True
        self.release["tag_name"] = "v2.0.0-rc.10"
        self.release["assets"][0]["browser_download_url"] = "https://github.com/example/recomp/releases/download/v2.0.0-rc.10/recomp.zip"
        self.service.fetch = mock.Mock(return_value=json.dumps([self.release]).encode())
        self.assertEqual(self.service.check(self.m)["version"], "v2.0.0-rc.10")

    def test_remote_first_install_ignores_manifest_version_without_executable(self):
        self.m["version"] = "v1.2.3"
        self.assertIsNotNone(self.service.check(self.m))

    def test_prerelease_check_ignores_releases_without_the_configured_asset(self):
        self.m["releases"]["channel"] = "prerelease"
        historical = copy.deepcopy(self.release)
        historical["tag_name"] = "v1.0.0"
        historical["assets"][0]["name"] = "old-package.zip"
        self.service.fetch = mock.Mock(return_value=json.dumps([self.release, historical]).encode())
        self.assertEqual(self.service.check(self.m)["version"], "v1.2.3")
        self.assertEqual(self.service.fetch.call_count, 1)
        self.assertNotIn("roots", self.config)
        self.service.fetch = mock.Mock(return_value=json.dumps([historical]).encode())
        self.assertIsNone(self.service.check(self.m))

    def test_stale_offer_cannot_downgrade_changed_install(self):
        offer = self.service.check(self.m)
        self.config["game_versions"] = {"sample": "v2.0.0"}
        with self.assertRaises(gu.GameUpdateError):
            self.service.install(self.m, offer)
        self.assertEqual(self.fetch.call_count, 1)

    def test_redirect_policy_never_accepts_other_repos_or_local_urls(self):
        for url in ("file:///c:/test", "http://github.com/example/recomp/releases/download/v1/recomp.zip",
                    "https://github.com@evil.invalid/example/recomp/releases/download/v1/recomp.zip",
                    "https://github.com/other/game/releases/download/v1/recomp.zip",
                    "https://localhost/example/recomp/releases/download/v1/recomp.zip"):
            self.assertFalse(gu._url(url, "example/recomp"))
        handler = gu._Redirects("example/recomp", False)
        req = gu.urllib.request.Request("https://github.com/example/recomp/releases/download/v1/recomp.zip")
        with self.assertRaises(gu.GameUpdateError):
            handler.redirect_request(req, None, 302, "redirect", {}, "https://evil.invalid/game")


if __name__ == "__main__":
    unittest.main()

