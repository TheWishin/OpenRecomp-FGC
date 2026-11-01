"""Author registration reviews data, never installs or executes game code."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from openrecomp import game_library as library, manifest as mf

ROOT = Path(__file__).resolve().parents[1]


def public_manifest(**changes):
    manifest = dict(schema_version=1, id="sample", title="Sample recomp", numeral="S",
                    accent="#123456", adapter="generic", platform="Example",
                    author="Example author", repository="example/sample", exe="bin/sample.exe",
                    license="MIT", credits=["Example author"],
                    requirements=[dict(id="disc", label="Your own source disc", kind="iso",
                                       version="Example revision", sha256="0" * 64)])
    manifest.update(changes)
    return manifest


class GameLibrary(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "launcher-data"
        self.environment = mock.patch.dict(os.environ, {"OPENRECOMP_HOME": str(self.home)})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.config = {}

    def local(self, manifest=None):
        folder = self.root / "author-install"
        folder.mkdir(exist_ok=True)
        (folder / library.MANIFEST_NAME).write_text(json.dumps(manifest or public_manifest()), encoding="utf-8")
        return folder

    def test_local_preview_changes_nothing_and_shows_author_requirements(self):
        folder = self.local()
        with mock.patch("subprocess.Popen") as process:
            preview = library.Library(self.config).preview(str(folder))
        self.assertEqual(preview["author"], "Example author")
        self.assertEqual(preview["requirements"][0]["version"], "Example revision")
        self.assertEqual(preview["warning"], "@library.third_party")
        self.assertEqual(preview["root"], str(folder.resolve()))
        self.assertEqual(self.config, {})
        self.assertFalse(self.home.exists())
        process.assert_not_called()

    def test_remote_preview_reads_only_fixed_manifest_endpoint(self):
        fetch = mock.Mock(return_value=json.dumps(public_manifest()).encode())
        service = library.Library(self.config, fetch=fetch)
        with mock.patch("subprocess.Popen") as process:
            preview = service.preview("example/sample")
            service.accept(preview)
        fetch.assert_called_once_with(
            "https://api.github.com/repos/example/sample/contents/openrecomp-game.json", mf.MAX_MANIFEST_BYTES)
        self.assertEqual(self.config["game_sources"]["sample"]["kind"], "github")
        self.assertEqual(self.config["roots"]["sample"], str(self.home / "installs" / "sample"))
        self.assertFalse((self.home / "installs").exists())
        process.assert_not_called()

    def test_missing_root_manifest_can_be_reviewed_from_authors_latest_release(self):
        data = json.dumps(public_manifest()).encode()
        contents = "https://api.github.com/repos/example/sample/contents/openrecomp-game.json"
        asset_url = "https://github.com/example/sample/releases/download/v1.0.0/openrecomp-game.json"
        release = dict(draft=False, prerelease=False, tag_name="v1.0.0", assets=[dict(
            name=library.MANIFEST_NAME, size=len(data), browser_download_url=asset_url,
            digest="sha256:" + hashlib.sha256(data).hexdigest())])
        fetch = mock.Mock(side_effect=[
            library.urllib.error.HTTPError(contents, 404, "Not found", {}, None),
            json.dumps(release).encode(), data])
        preview = library.Library(self.config, fetch=fetch).preview("example/sample")
        self.assertEqual(preview["manifest"]["id"], "sample")
        self.assertEqual(fetch.call_args_list, [
            mock.call(contents, mf.MAX_MANIFEST_BYTES),
            mock.call("https://api.github.com/repos/example/sample/releases/latest", library.MAX_RELEASE_METADATA),
            mock.call(asset_url, len(data))])
        self.assertEqual(self.config, {})

    def test_release_fallback_refuses_misdirected_huge_and_wrong_hash_assets(self):
        data = json.dumps(public_manifest()).encode()
        asset_url = "https://github.com/example/sample/releases/download/v1.0.0/openrecomp-game.json"
        for changes in (dict(browser_download_url="https://evil.invalid/openrecomp-game.json"),
                        dict(size=mf.MAX_MANIFEST_BYTES + 1), dict(digest="sha256:" + "0" * 64)):
            with self.subTest(changes=changes):
                asset = dict(name=library.MANIFEST_NAME, size=len(data), browser_download_url=asset_url)
                asset.update(changes)
                release = dict(draft=False, prerelease=False, tag_name="v1.0.0", assets=[asset])
                fetch = mock.Mock(side_effect=[
                    library.urllib.error.HTTPError("https://api.github.com", 404, "Not found", {}, None),
                    json.dumps(release).encode(), data])
                with self.assertRaises(library.LibraryError):
                    library.Library(self.config, fetch=fetch).preview("example/sample")

    def test_accept_keeps_local_install_in_place_and_persists_manifest(self):
        folder = self.local()
        service = library.Library(self.config)
        preview = service.preview(str(folder))
        service.accept(preview)
        self.assertEqual(self.config["roots"]["sample"], str(folder.resolve()))
        self.assertEqual(mf.load_file(self.home / "games" / "sample.json")["author"], "Example author")
        self.assertEqual(mf.load_config(), self.config)
        self.assertEqual(sorted(p.name for p in folder.iterdir()), [library.MANIFEST_NAME])

    def test_accept_does_not_reread_changed_local_manifest(self):
        folder = self.local()
        service = library.Library(self.config)
        preview = service.preview(str(folder))
        (folder / library.MANIFEST_NAME).write_text("not JSON", encoding="utf-8")
        installed = service.accept(preview)
        self.assertEqual(installed["title"], "Sample recomp")

    def test_reviewing_again_preserves_an_already_updated_install(self):
        folder = self.local()
        service = library.Library(self.config)
        service.accept(service.preview(str(folder)))
        self.config["roots"]["sample"] = str(self.home / "installs" / "sample" / "updated-version")
        self.config["game_versions"] = dict(sample="v2.0.0")
        service.accept(service.preview(str(folder)))
        self.assertEqual(self.config["roots"]["sample"], str(self.home / "installs" / "sample" / "updated-version"))
        self.assertEqual(self.config["game_versions"]["sample"], "v2.0.0")

    def test_remote_manifest_version_does_not_claim_game_is_installed(self):
        service = library.Library(self.config, fetch=lambda *_: json.dumps(public_manifest(version="v3.0.0")).encode())
        service.accept(service.preview("example/sample"))
        self.assertNotIn("game_versions", self.config)

    def test_accept_preserves_compact_manifest_within_size_limit(self):
        manifest = mf.validate_external(public_manifest())
        raw = json.dumps(manifest, separators=(",", ":")).encode()
        self.assertGreater(len(json.dumps(manifest).encode()), len(raw))
        service = library.Library(self.config, fetch=lambda *_: raw)
        with mock.patch.object(mf, "MAX_MANIFEST_BYTES", len(raw)):
            installed = service.accept(service.preview("example/sample"))
            destination = self.home / "games" / "sample.json"
            self.assertLessEqual(destination.stat().st_size, len(raw))
            self.assertEqual(installed, mf.load_file(destination))

    def test_local_version_seed_requires_existing_exe_and_valid_release_version(self):
        folder = self.local(public_manifest(version="v3.0.0"))
        service = library.Library(self.config)
        preview = service.preview(str(folder))
        actual_isfile = os.path.isfile
        expected = str(folder / "bin" / "sample.exe")
        with mock.patch.object(library.os.path, "isfile", side_effect=lambda path: str(path) == expected or actual_isfile(path)):
            service.accept(preview)
        self.assertEqual(self.config["game_versions"]["sample"], "v3.0.0")

    def test_preview_cannot_be_forged_or_modified_and_is_single_use(self):
        service = library.Library(self.config)
        preview = service.preview(str(self.local()))
        forged = copy.deepcopy(preview)
        forged["manifest"]["exe"] = "elsewhere.exe"
        with self.assertRaisesRegex(library.LibraryError, "preview_expired"):
            service.accept(forged)
        service.accept(preview)
        with self.assertRaisesRegex(library.LibraryError, "preview_expired"):
            service.accept(preview)

    def test_other_library_instance_cannot_accept_preview(self):
        preview = library.Library(self.config).preview(str(self.local()))
        with self.assertRaisesRegex(library.LibraryError, "preview_expired"):
            library.Library(self.config).accept(preview)

    def test_remove_registration_preserves_all_game_data(self):
        folder = self.local()
        (folder / "settings.json").write_text('{"volume": 2}', encoding="utf-8")
        (folder / "replays").mkdir()
        service = library.Library(self.config)
        service.accept(service.preview(str(folder)))
        self.config["last_game"] = "sample"
        self.config["game_versions"] = dict(sample="v1.0.0", other="v2.0.0")
        self.config["generic_sources"] = dict(sample={"disc": "unused"}, other={})
        self.assertTrue(service.remove("sample"))
        self.assertTrue((folder / "settings.json").exists())
        self.assertTrue((folder / "replays").exists())
        self.assertTrue((folder / library.MANIFEST_NAME).exists())
        self.assertFalse((self.home / "games" / "sample.json").exists())
        self.assertNotIn("sample", self.config["roots"])
        self.assertNotIn("sample", self.config["game_sources"])
        self.assertNotIn("last_game", self.config)
        self.assertEqual(self.config["game_versions"], dict(other="v2.0.0"))
        self.assertEqual(self.config["generic_sources"], dict(other={}))

    def test_remove_does_not_touch_another_game_or_launcher_registration(self):
        service = library.Library(self.config)
        for game_id in ("t4", "t5dr", "../sample", "C:/sample", "NUL"):
            with self.subTest(game_id=game_id):
                with self.assertRaises(library.LibraryError):
                    service.remove(game_id)

    def test_source_cannot_replace_an_existing_authors_identity(self):
        folder = self.local()
        service = library.Library(self.config)
        service.accept(service.preview(str(folder)))
        self.local(public_manifest(author="Somebody else"))
        preview = service.preview(str(folder))
        with self.assertRaisesRegex(library.LibraryError, "source_changed"):
            service.accept(preview)
        self.assertEqual(mf.load_file(self.home / "games" / "sample.json")["author"], "Example author")

    def test_github_manifest_cannot_redirect_release_author(self):
        fetch = mock.Mock(return_value=json.dumps(public_manifest(repository="other/source")).encode())
        with self.assertRaisesRegex(library.LibraryError, "invalid_manifest"):
            library.Library(self.config, fetch=fetch).preview("example/sample")

    def test_hostile_or_huge_manifest_rejected_before_registration(self):
        for data in (b"x" * (mf.MAX_MANIFEST_BYTES + 1),
                     json.dumps(public_manifest(exe="../outside.exe")).encode(),
                     json.dumps(public_manifest(adapter="t5dr")).encode(),
                     json.dumps(public_manifest(id="t4")).encode()):
            with self.subTest(data_size=len(data)):
                with self.assertRaises(library.LibraryError):
                    library.Library(self.config, fetch=lambda *_: data).preview("example/sample")
        self.assertEqual(self.config, {})
        self.assertFalse(self.home.exists())

    def test_local_manifest_size_is_checked_before_reading(self):
        folder = self.local()
        (folder / library.MANIFEST_NAME).write_bytes(b" " * (mf.MAX_MANIFEST_BYTES + 1))
        with mock.patch("builtins.open", side_effect=AssertionError("oversized file was opened")):
            with self.assertRaisesRegex(library.LibraryError, "invalid_manifest"):
                library.Library(self.config).preview(str(folder))

    def test_local_manifest_symlink_cannot_escape_chosen_folder(self):
        folder = self.root / "linked-install"
        folder.mkdir()
        external = self.root / "external-manifest.json"
        external.write_text(json.dumps(public_manifest()), encoding="utf-8")
        try:
            (folder / library.MANIFEST_NAME).symlink_to(external)
        except OSError:
            self.skipTest("creating file symlinks is unavailable")
        with self.assertRaises(library.LibraryError):
            library.Library(self.config).preview(str(folder))

    def test_odd_sources_never_make_a_request(self):
        fetch = mock.Mock()
        service = library.Library(self.config, fetch=fetch)
        for source in ("https://github.com/example/sample", "example/sample?ref=x", "example/../sample",
                       "example/sample#fragment", "git@github.com:example/sample", "example/sample%2fmore", ""):
            with self.subTest(source=source), self.assertRaises(library.LibraryError):
                service.preview(source)
        fetch.assert_not_called()

    def test_save_failure_rolls_back_manifest_and_memory(self):
        service = library.Library(self.config)
        preview = service.preview(str(self.local()))
        with mock.patch.object(mf, "save_config", side_effect=OSError("unavailable")):
            with self.assertRaises(OSError):
                service.accept(preview)
        self.assertEqual(self.config, {})
        self.assertFalse((self.home / "games" / "sample.json").exists())

    def test_review_cleanup_failure_does_not_hide_success_or_reuse_preview(self):
        service = library.Library(self.config)
        preview = service.preview(str(self.local()))
        unlink = os.unlink

        def deny_review_cleanup(path, *args, **kwargs):
            if Path(path).name.startswith(".game-review-"):
                raise PermissionError("cleanup denied")
            return unlink(path, *args, **kwargs)

        with mock.patch.object(library.os, "unlink", side_effect=deny_review_cleanup):
            installed = service.accept(preview)
        self.assertEqual(mf.load_file(self.home / "games" / "sample.json"), installed)
        self.assertEqual(mf.load_config(), self.config)
        with self.assertRaisesRegex(library.LibraryError, "preview_expired"):
            service.accept(preview)

    def test_review_cleanup_failure_preserves_save_error_and_rollback(self):
        service = library.Library(self.config)
        preview = service.preview(str(self.local()))
        save_error = OSError("save unavailable")
        unlink = os.unlink

        def deny_review_cleanup(path, *args, **kwargs):
            if Path(path).name.startswith(".game-review-"):
                raise PermissionError("cleanup denied")
            return unlink(path, *args, **kwargs)

        with mock.patch.object(mf, "save_config", side_effect=save_error), \
                mock.patch.object(library.os, "unlink", side_effect=deny_review_cleanup):
            with self.assertRaises(OSError) as raised:
                service.accept(preview)
        self.assertIs(raised.exception, save_error)
        self.assertEqual(self.config, {})
        self.assertFalse((self.home / "games" / "sample.json").exists())

    def test_transport_blocks_redirects_and_enforces_content_length(self):
        self.assertIsNone(library._NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.invalid"))
        response = io.BytesIO(b"{}")
        response.headers = {"Content-Length": str(mf.MAX_MANIFEST_BYTES + 1)}
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.object(library.urllib.request, "build_opener", return_value=opener):
            with self.assertRaises(library.LibraryError):
                library.fetch_manifest("https://api.github.com/repos/example/sample/contents/openrecomp-game.json", mf.MAX_MANIFEST_BYTES)

    def test_transport_rejects_arbitrary_hosts_before_opening(self):
        with mock.patch.object(library.urllib.request, "build_opener") as opener:
            for url in ("http://api.github.com/repos/example/sample", "https://api.github.com.evil.invalid/repos/a/b",
                        "https://user@api.github.com/repos/a/b", "https://api.github.com:443/repos/a/b"):
                with self.subTest(url=url), self.assertRaises(library.LibraryError):
                    library.fetch_manifest(url, 10)
        opener.assert_not_called()

    def test_manifest_asset_redirects_only_to_githubs_asset_host(self):
        self.assertTrue(library._asset_redirect(
            "https://release-assets.githubusercontent.com/github-production-release-asset/example?token=sample"))
        for url in ("http://release-assets.githubusercontent.com/github-production-release-asset/a",
                    "https://release-assets.githubusercontent.com.evil.invalid/github-production-release-asset/a",
                    "https://release-assets.githubusercontent.com:443/github-production-release-asset/a",
                    "https://release-assets.githubusercontent.com/elsewhere/a", "https://evil.invalid/a"):
            with self.subTest(url=url), self.assertRaises(library.LibraryError):
                library._AssetRedirect().redirect_request(None, None, 302, "", {}, url)


if __name__ == "__main__":
    unittest.main()
