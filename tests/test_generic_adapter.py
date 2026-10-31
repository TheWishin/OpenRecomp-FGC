"""Declarative games never load author code into the launcher."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from openrecomp.adapters.base import Generic


ROOT = Path(__file__).resolve().parents[1]


class GenericAdapter(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.manifest = dict(schema_version=1, id="sample", title="Sample", short="Sample",
                             adapter="generic", exe="bin/game.exe", args=["--player-ui"],
                             settings=dict(file="settings.json", cyclers=[dict(
                                 id="display", label="Display", key="display",
                                 options=[dict(value="window", label="Window"), dict(value="full", label="Full screen")])]),
                             online=dict(mode="own"))
        self.config = dict(roots=dict(sample=str(self.root)))
        self.adapter = Generic(self.manifest, self.config)

    def test_constructor_reads_no_author_code_and_starts_nothing(self):
        with mock.patch("builtins.__import__", wraps=__import__) as imports, mock.patch("subprocess.Popen") as start:
            Generic(self.manifest, self.config)
        start.assert_not_called()
        self.assertEqual(imports.call_args_list, [])

    def test_v1_executable_and_arguments_are_relative_to_chosen_root(self):
        process = mock.Mock(pid=12)
        process.poll.return_value = None
        with mock.patch.object(self.adapter, "ready", return_value=True), mock.patch("subprocess.Popen", return_value=process) as launch:
            self.assertEqual(self.adapter.start(), 12)
        args, kwargs = launch.call_args
        self.assertEqual(args[0], [str(self.root / "bin" / "game.exe"), "--player-ui"])
        self.assertEqual(kwargs["cwd"], str(self.root))
        self.assertIs(kwargs["shell"], False)

    def test_missing_root_cannot_launch_and_missing_exe_is_not_ready(self):
        self.assertTrue(self.adapter.found())
        self.assertFalse(self.adapter.ready())
        self.assertFalse(Generic(self.manifest, {}).ready())
        with mock.patch("subprocess.Popen") as launch, self.assertRaises(RuntimeError):
            Generic(self.manifest, {}).start()
        launch.assert_not_called()

    def test_runtime_paths_reject_traversal_even_if_validation_was_bypassed(self):
        self.manifest["exe"] = "../outside.exe"
        self.assertFalse(self.adapter.ready())
        self.manifest["settings"]["file"] = "../outside.json"
        self.assertEqual(self.adapter.settings(), [])
        with self.assertRaises(RuntimeError):
            self.adapter.set_setting("display", "full")

    def test_v1_cannot_launch_a_script_even_if_validation_was_bypassed(self):
        self.manifest["exe"] = "setup.cmd"
        with mock.patch("os.path.isfile", return_value=True), mock.patch("subprocess.Popen") as launch:
            self.assertFalse(self.adapter.ready())
            with self.assertRaises(RuntimeError):
                self.adapter.start()
        launch.assert_not_called()

    def test_installed_release_version_overrides_manifest_version(self):
        self.manifest["version"] = "v1.0.0"
        self.config["game_versions"] = dict(sample="v2.0.0")
        with mock.patch.object(self.adapter, "ready", return_value=True):
            self.assertEqual(self.adapter.status()["version"], dict(_literal="v2.0.0"))

    def test_logo_is_a_bounded_local_bitmap_only(self):
        for extension in ("png", "jpg", "jpeg", "webp"):
            self.manifest["logo"] = "logo." + extension
            with mock.patch("os.path.isfile", return_value=True), mock.patch("os.path.getsize", return_value=1024):
                self.assertEqual(self.adapter.hero(), str(self.root / ("logo." + extension)))
        self.manifest["logo"] = "logo.png"
        with mock.patch("os.path.isfile", return_value=True), mock.patch("os.path.getsize", return_value=8 * 1024 * 1024 + 1):
            self.assertEqual(self.adapter.hero(), "")
        with mock.patch("os.path.isfile", return_value=False):
            self.assertEqual(self.adapter.hero(), "")
        self.manifest["logo"] = "logo.svg"
        with mock.patch("os.path.isfile", return_value=True), mock.patch("os.path.getsize", return_value=1024):
            self.assertEqual(self.adapter.hero(), "")
        self.manifest["logo"] = "../outside.png"
        self.assertEqual(self.adapter.hero(), "")

    def test_cyclers_preserve_unknown_settings_and_never_execute_values(self):
        path = self.root / "settings.json"
        path.write_text(json.dumps(dict(display="window", unrelated=dict(keep=True))), encoding="utf-8")
        self.assertEqual(self.adapter.settings()[0]["value"], "window")
        with mock.patch("subprocess.Popen") as launch:
            self.adapter.set_setting("display", "full")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), dict(display="full", unrelated=dict(keep=True)))
        launch.assert_not_called()
        with self.assertRaises(RuntimeError):
            self.adapter.set_setting("display", "arbitrary")

    def test_malformed_or_huge_settings_are_preserved(self):
        path = self.root / "settings.json"
        for data in ("{", " " * (1024 * 1024 + 1)):
            path.write_text(data, encoding="utf-8")
            self.assertEqual(self.adapter.settings(), [])
            with self.assertRaises(RuntimeError):
                self.adapter.set_setting("display", "full")
            self.assertEqual(path.read_text(encoding="utf-8"), data)

    def test_own_online_is_only_an_explicit_game_launch(self):
        with mock.patch.object(self.adapter, "start") as launch:
            self.assertFalse(self.adapter.online_supported())
            self.assertEqual(self.adapter.online_items()[0]["id"], "own")
            self.adapter.online_state()
            self.adapter.online_poll()
            self.adapter.online_close()
            launch.assert_not_called()
            self.adapter.run_online("own")
            launch.assert_called_once_with()
        self.manifest["online"] = dict(mode="lobby", arrangement="Ask the maintainers")
        with mock.patch.object(self.adapter, "start") as launch:
            self.assertTrue(self.adapter.online_items()[0]["disabled"])
            self.adapter.run_online("own")
            launch.assert_not_called()

    def test_build_instructions_and_controls_are_data_only(self):
        self.manifest["build"] = dict(instructions="Build in the author's own tool.")
        self.manifest["controls"] = dict(file="controls.json")
        with mock.patch("subprocess.Popen") as launch:
            self.assertEqual(self.adapter.build_ready(), dict(_literal="Build in the author's own tool."))
            with self.assertRaises(RuntimeError):
                self.adapter.build_start()
            self.assertFalse(self.adapter.controls_supported())
        launch.assert_not_called()

    def test_player_supplied_files_are_verified_before_registration(self):
        path = self.root / "input.txt"
        data = b"synthetic test input"
        path.write_bytes(data)
        required = dict(id="source", label="Source", kind="file", version="Test version", sha256=hashlib.sha256(data).hexdigest())
        self.manifest["requirements"] = [required]
        self.adapter.set_source("source", str(path))
        self.adapter._source_thread.join(5)
        self.assertTrue(self.adapter.source_state()["ok"])
        self.assertTrue(self.adapter.sources()[1]["ok"])
        required["sha256"] = "0" * 64
        self.adapter.set_source("source", str(path))
        self.adapter._source_thread.join(5)
        self.assertFalse(self.adapter.source_state()["ok"])
        self.assertEqual(self.adapter.source_state()["result"], "@generic.requirement_bad_hash")

    def test_running_game_prevents_file_mutation_or_duplicate_launch(self):
        self.adapter.proc = mock.Mock()
        self.adapter.proc.poll.return_value = None
        for action in (lambda: self.adapter.set_setting("display", "full"),
                       lambda: self.adapter.set_source("folder", str(self.root)), self.adapter.start):
            with self.assertRaises(RuntimeError):
                action()

    def test_source_hashing_rejects_directories_and_missing_files(self):
        self.manifest["requirements"] = [dict(id="source", label="Source", kind="file", version="Test", sha256="0" * 64)]
        with mock.patch("threading.Thread") as worker:
            for path in (str(self.root), str(self.root / "missing.txt")):
                with self.assertRaises(RuntimeError):
                    self.adapter.set_source("source", path)
        worker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
