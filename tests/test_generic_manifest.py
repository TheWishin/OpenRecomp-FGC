"""Public manifests are bounded data, never adapter or filesystem authority."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from openrecomp import manifest as mf


ROOT = Path(__file__).parents[1]


def public_manifest(**changes):
    result = dict(schema_version=1, id="example", title="Example", numeral="E", accent="#123ABC",
                  adapter="generic", platform="PC", author="Example author", repository="example/recomp",
                  exe="bin/game.exe", license="MIT", credits=["Example author"])
    result.update(changes)
    return result


class GenericManifestTests(unittest.TestCase):
    def reject(self, **changes):
        with self.assertRaises(mf.ManifestError):
            mf.validate_external(public_manifest(**changes))

    def test_minimal_and_full_version_one_round_trip(self):
        m = public_manifest(
            args=["--windowed"], cwd="bin", replays="replays", logo="assets/logo.png",
            releases=dict(channel="stable", asset="example.zip", verification=dict(method="github-sha256")),
            requirements=[dict(id="disc", label="Player disc", kind="iso", version="US 1.0", sha256="0" * 64)],
            build=dict(instructions="Build using the author's instructions."), controls=dict(file="controls.json"),
            settings=dict(file="settings.json", cyclers=[dict(id="window", key="fullscreen", label="Display",
                          options=[dict(value=False, label="Window"), dict(value=True, label="Full screen")])]),
            online=dict(mode="own"))
        first = mf.validate_external(m)
        self.assertEqual(first, mf.validate_external(first))
        self.assertEqual(first, mf.parse_bytes(json.dumps(first).encode()))
        self.assertEqual(mf.validate_external(public_manifest())["online"], dict(mode="none"))

    def test_unsupported_versions_adapters_and_unknown_hooks_are_rejected(self):
        for changes in (dict(schema_version=True), dict(schema_version=2), dict(adapter="t5dr"),
                        dict(env={"PYTHONPATH": "code"}), dict(module="evil"), dict(locations=["../other"]),
                        dict(build=dict(command=["shell"]))):
            with self.subTest(changes=changes):
                self.reject(**changes)

    def test_hostile_windows_paths_are_rejected_in_every_path_field(self):
        bad = ("../outside", "/absolute", "C:/outside", "C:relative", "//host/share", "a\\..\\b",
               "a/../b", "a/./b", "a//b", "a:stream", "%TEMP%/x", "$HOME/x", "~name/x",
               "a/b.", "a/b ", "CON", "a/NUL.txt", "COM¹.txt", "LPT2", "a/*", "a/?", "a\x00b")
        for field in ("exe", "cwd", "replays", "logo"):
            for value in bad:
                with self.subTest(field=field, value=value):
                    self.reject(**{field: value})
        for value in bad:
            with self.subTest(settings=value):
                self.reject(settings=dict(file=value, cyclers=[]))
            with self.subTest(controls=value):
                self.reject(controls=dict(file=value))

    def test_symlink_escape_is_rejected_when_resolving(self):
        with mock.patch.object(mf.os.path, "realpath", side_effect=[str(ROOT / "install"), str(ROOT / "outside" / "settings.json")]):
            with self.assertRaises(mf.ManifestError):
                mf.resolve_path(str(ROOT / "install"), "settings.json")

    def test_odd_urls_and_repository_transports_are_rejected(self):
        for value in ("https://github.com/owner/repo", "owner/repo.git", "../repo", "owner/repo/extra",
                      "owner/repo?x", "owner/repo#x", "git@github.com:owner/repo", "owner/repo%2fextra"):
            with self.subTest(repository=value):
                self.reject(repository=value)
        for value in ("http://github.com/owner/repo", "https://github.com.evil/owner/repo",
                      "https://user@github.com/owner/repo", "https://github.com:443/owner/repo",
                      "https://github.com/owner/%2e%2e/repo", "https://github.com/owner/repo?token=x", "https://["):
            with self.subTest(url=value), self.assertRaises(mf.ManifestError):
                mf.github_url(value)

    def test_bounded_json_rejects_duplicates_deep_values_and_non_json_numbers(self):
        for data in (b" " * (mf.MAX_MANIFEST_BYTES + 1), b'{"id":"one","id":"two"}',
                     b"[" * 2000 + b"]" * 2000, b'{"order":NaN}', b"\xff", b"[]"):
            with self.subTest(data=data[:40]), self.assertRaises(mf.ManifestError):
                mf.parse_bytes(data)

    def test_load_file_never_reads_more_than_limit_plus_one(self):
        with mock.patch("builtins.open", mock.mock_open(read_data=b" " * (mf.MAX_MANIFEST_BYTES + 1))) as opened:
            with self.assertRaises(mf.ManifestError):
                mf.load_file("manifest.json")
            opened().read.assert_called_once_with(mf.MAX_MANIFEST_BYTES + 1)

    def test_lone_surrogates_are_rejected_before_install(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder, mock.patch.dict(os.environ, OPENRECOMP_HOME=folder):
            source = Path(folder) / "manifest.json"
            for title in ("\ud800", "\udfff"):
                raw = json.dumps(public_manifest(title=title)).encode("utf-8")
                with self.subTest(title=repr(title)):
                    with self.assertRaises(mf.ManifestError):
                        mf.parse_bytes(raw)
                    source.write_bytes(raw)
                    with self.assertRaises(mf.ManifestError):
                        mf.install(source)
                    self.assertFalse((Path(folder) / "games").exists())

    def test_valid_surrogate_pair_round_trips_as_unicode(self):
        title = "Example \U0001f600"
        raw = json.dumps(public_manifest(title=title)).encode("utf-8")
        self.assertIn(b"\\ud83d\\ude00", raw)
        self.assertEqual(mf.parse_bytes(raw)["title"], title)
        with tempfile.TemporaryDirectory(dir=ROOT) as folder, mock.patch.dict(os.environ, OPENRECOMP_HOME=folder):
            source = Path(folder) / "manifest.json"
            source.write_bytes(raw)
            mf.install(source)
            self.assertEqual(mf.load_file(Path(folder) / "games" / "example.json")["title"], title)

    def test_settings_requirements_and_releases_are_strict(self):
        for change in (dict(requirements=[{}]), dict(requirements="disc"), dict(credits="author"),
                       dict(requirements=[dict(id="folder", label="Disc", kind="iso", version="1", sha256="a" * 64)]),
                       dict(sections=["play", "play"]), dict(sections=[{}]), dict(order=True),
                       dict(settings=dict(file="settings.json", cyclers=[dict(id="s", key="x", label="X", options=[])])),
                       dict(releases=dict(channel="stable", asset="game.zip", verification=dict(method="none"))),
                       dict(releases=dict(channel="stable", asset="../game.zip", verification=dict(method="github-sha256"))),
                       dict(releases=dict(channel="stable", asset="game.zip", verification=dict(method="sha256", sha256="bad"))),
                       dict(online=dict(mode="lobby")), dict(online=dict(mode="own", login="launcher")),
                       dict(title="x" * 161), dict(title="Author\u202eevil"), dict(accent="#zzzzzz"), dict(id="CON"),
                       dict(exe="game.cmd"), dict(exe="game.bat"), dict(version="latest"),
                       dict(version="1.2.3"), dict(version="v01.2.3"), dict(version="v1.2.3-01"),
                       dict(replays="bin"), dict(settings=dict(file="bin/game.exe", cyclers=[]))):
            with self.subTest(change=change):
                self.reject(**change)

    def test_pinned_hash_and_lobby_arrangement_are_data(self):
        m = mf.validate_external(public_manifest(
            releases=dict(channel="prerelease", asset="game.zip", verification=dict(method="sha256", sha256="a" * 64)),
            online=dict(mode="lobby", arrangement="Contact the launcher maintainer first.")))
        self.assertEqual(m["online"]["mode"], "lobby")

    def test_install_is_strict_and_builtin_ids_cannot_be_shadowed(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder, mock.patch.dict(os.environ, OPENRECOMP_HOME=folder):
            source = Path(folder) / "manifest.json"
            source.write_text(json.dumps(public_manifest()), encoding="utf-8")
            installed = mf.install(source)
            self.assertEqual(installed, mf.load_file(Path(folder) / "games" / "example.json"))
            for game_id in ("t4", "T4", "t5dr", "T5DR"):
                source.write_text(json.dumps(public_manifest(id=game_id)), encoding="utf-8")
                with self.assertRaises(mf.ManifestError):
                    mf.install(source)

    def test_large_compact_manifest_remains_loadable_after_install(self):
        manifest = public_manifest(
            args=["x" * 1024] * 8,
            settings=dict(file="settings.json", cyclers=[
                dict(id=f"setting{index}", key=f"setting{index}", label="Setting",
                     options=[dict(value=value, label="x" * 140) for value in range(32)])
                for index in range(10)]))
        raw = json.dumps(manifest, separators=(",", ":")).encode()
        self.assertLess(len(raw), mf.MAX_MANIFEST_BYTES)
        self.assertGreater(len(json.dumps(mf.validate_external(manifest), indent=1).encode()), mf.MAX_MANIFEST_BYTES)
        with tempfile.TemporaryDirectory(dir=ROOT) as folder, mock.patch.dict(os.environ, OPENRECOMP_HOME=folder):
            source = Path(folder) / "manifest.json"
            source.write_bytes(raw)
            installed = mf.install(source)
            destination = Path(folder) / "games" / "example.json"
            self.assertLessEqual(destination.stat().st_size, mf.MAX_MANIFEST_BYTES)
            self.assertEqual(installed, mf.load_file(destination))

    def test_install_checks_size_after_adding_defaults(self):
        raw = json.dumps(public_manifest(), separators=(",", ":")).encode()
        with tempfile.TemporaryDirectory(dir=ROOT) as folder, mock.patch.dict(os.environ, OPENRECOMP_HOME=folder):
            source = Path(folder) / "manifest.json"
            source.write_bytes(raw)
            with mock.patch.object(mf, "MAX_MANIFEST_BYTES", len(raw)), self.assertRaises(mf.ManifestError):
                mf.install(source)
            self.assertFalse((Path(folder) / "games").exists())

    def test_restart_rejects_injected_legacy_user_manifest(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder, mock.patch.dict(os.environ, OPENRECOMP_HOME=folder):
            games = Path(folder) / "games"
            games.mkdir()
            legacy = public_manifest(id="t5dr", adapter="t5dr")
            legacy.pop("schema_version")
            (games / "evil.json").write_text(json.dumps(legacy), encoding="utf-8")
            loaded, problems = mf.load_all()
            self.assertEqual([m["id"] for m in loaded], ["t4", "t5dr"])
            self.assertEqual(len(problems), 1)


if __name__ == "__main__":
    unittest.main()
