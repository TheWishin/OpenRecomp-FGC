"""Offline coexistence setup with inert metadata and fake private settings only."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location("coexist_update_drill", Path(__file__).parents[1] / "tools" / "update_drill.py")
drill = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(drill)


class CoexistUpdateDrillTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parents[1])
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.old = self.root / "old"
        self.settings = self.root / "settings-copy"
        self.work = self.root / "drill"
        self.checkout = self.root / "public-checkout"
        self.old.mkdir()
        self.settings.mkdir()
        self.write(self.old / "release.json", dict(version="1.1.9"))
        self.write(self.old / "launcher.json", dict(display="window", future=dict(keep=True)))
        self.write(self.settings / "launcher.json", dict(display="window", future=dict(keep=True)))
        self.write(self.settings / "online.json", dict(name="Fake", sessions={"fake-server": dict(token="inert-fake-session")}))
        self.write(self.settings / "controls.json", dict(unknown_binding=dict(keep=True)))

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def run_drill(self, **changes):
        args = dict(old_install=self.old, settings_copy=self.settings, work=self.work, checkout=self.checkout)
        args.update(changes)
        return drill.run_drill(**args)

    def test_stages_actual_launcher_config_and_preserves_every_input_byte(self):
        old_before = {p.name: p.read_bytes() for p in self.old.iterdir()}
        settings_before = {p.name: p.read_bytes() for p in self.settings.iterdir()}
        result = self.run_drill()
        self.assertTrue(result["ok"])
        self.assertTrue(result["old_metadata_unchanged"])
        self.assertTrue(result["settings_copy_unchanged"])
        config = json.loads((self.work / "home" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config, dict(roots={"t5dr": str(self.old)}, t5dr_settings_copy=str(self.settings)))
        self.assertEqual({p.name: p.read_bytes() for p in self.old.iterdir()}, old_before)
        self.assertEqual({p.name: p.read_bytes() for p in self.settings.iterdir()}, settings_before)
        self.assertEqual(result["settings_files_checked"], 3)
        self.assertFalse(result["launcher_started"])
        self.assertFalse(result["game_started"])
        self.assertFalse(result["signed_update_checked"])
        self.assertTrue(result["settings_loaded"])
        self.assertTrue(result["online_source_checked"])
        self.assertTrue(result["controls_source_checked"])
        self.assertTrue(result["private_write_checked"])
        self.assertTrue(result["private_edit_rollback_checked"])
        self.assertTrue(result["inert_settings_facade"])
        self.assertEqual(list((self.work / "home").iterdir()), [self.work / "home" / "config.json"])

    def test_report_has_no_paths_credentials_contents_or_fingerprints(self):
        self.run_drill()
        report = (self.work / "report.json").read_text(encoding="utf-8")
        for private in (str(self.root), "inert-fake-session", "Fake", "fake-server", "unknown_binding", "future"):
            self.assertNotIn(private, report)
        result = json.loads(report)
        self.assertTrue(all(isinstance(value, (str, bool, int)) for value in result.values()))
        self.assertEqual(result["scope"], "offline-settings-only")

    def test_helper_exercise_restores_home_environment_after_success_and_failure(self):
        with mock.patch.dict(os.environ, {"OPENRECOMP_HOME": "fake-previous-home"}):
            self.run_drill()
            self.assertEqual(os.environ["OPENRECOMP_HOME"], "fake-previous-home")
        from openrecomp.adapters import t5_coexist
        other_work = self.root / "failed-drill"
        with mock.patch.dict(os.environ, {"OPENRECOMP_HOME": "fake-previous-home"}), \
                mock.patch.object(t5_coexist, "load_settings", side_effect=ValueError("private-native-value")):
            with self.assertRaisesRegex(drill.DrillError, "inert settings helper exercise failed"):
                self.run_drill(work=other_work)
            self.assertEqual(os.environ["OPENRECOMP_HOME"], "fake-previous-home")

    def test_rollback_removes_only_new_configuration_and_keeps_copy_and_report(self):
        before = drill.snapshot(self.settings, drill.SETTINGS_FILES)
        result = self.run_drill(expect="rollback")
        self.assertTrue(result["ok"])
        self.assertTrue(result["rollback_checked"])
        self.assertFalse(result["configuration_retained"])
        self.assertFalse((self.work / "home").exists())
        self.assertTrue((self.work / "report.json").is_file())
        self.assertEqual(before, drill.snapshot(self.settings, drill.SETTINGS_FILES))
        self.assertEqual(json.loads((self.old / "release.json").read_text())["version"], "1.1.9")

    def test_other_entries_are_not_read_copied_or_traversed(self):
        ignored = self.settings / "other-private-folder"
        ignored.mkdir()
        (ignored / "opaque").write_bytes(b"inert unknown data")
        result = self.run_drill()
        self.assertEqual(result["ignored_entries"], 1)
        self.assertEqual(list((self.work / "home").iterdir()), [self.work / "home" / "config.json"])
        self.assertTrue((ignored / "opaque").is_file())

    def test_never_opens_a_game_or_runtime_tree(self):
        real_open = Path.open
        opened = []

        def tracked(path, *args, **kwargs):
            opened.append(path)
            return real_open(path, *args, **kwargs)

        with mock.patch.object(Path, "open", autospec=True, side_effect=tracked):
            self.run_drill()
        self.assertEqual({path.name for path in opened if path.parent == self.old}, {"release.json", "launcher.json"})
        self.assertFalse(any(part in ("native", "runtime", "replays", "keys") for path in opened for part in path.parts))

    def test_requires_real_copy_launcher_settings_and_exact_old_version(self):
        (self.settings / "launcher.json").unlink()
        with self.assertRaisesRegex(drill.DrillError, "include launcher.json"):
            self.run_drill()
        self.assertFalse(self.work.exists())
        self.write(self.settings / "launcher.json", {})
        for version in ("1.1.8", "1.2.0", "1.1.9-preview", None):
            self.write(self.old / "release.json", dict(version=version))
            with self.subTest(version=version), self.assertRaisesRegex(drill.DrillError, "1.1.9"):
                self.run_drill()
        self.assertFalse(self.work.exists())

    def test_rejects_malformed_and_oversized_json_without_touching_work(self):
        for data in ('{"private":', '[]', '"private-value"'):
            (self.settings / "online.json").write_text(data, encoding="utf-8")
            with self.subTest(data=data), self.assertRaises(drill.DrillError):
                self.run_drill()
        self.write(self.settings / "online.json", {})
        with mock.patch.object(drill, "MAX_SETTINGS_BYTES", 5), self.assertRaisesRegex(drill.DrillError, "size limit"):
            self.run_drill()
        self.assertFalse(self.work.exists())

    def test_rejects_overlap_and_nonempty_work_before_writes(self):
        for changes in (dict(work=self.old / "drill"), dict(work=self.settings / "drill"),
                        dict(settings_copy=self.old), dict(work=self.root), dict(old_install=self.settings)):
            with self.subTest(changes=changes), self.assertRaises(drill.DrillError):
                self.run_drill(**changes)
        self.work.mkdir()
        (self.work / "keep").write_text("unchanged", encoding="utf-8")
        with self.assertRaisesRegex(drill.DrillError, "empty"):
            self.run_drill()
        self.assertEqual((self.work / "keep").read_text(), "unchanged")
        self.assertFalse((self.work / "home").exists())

    def test_rejects_checkout_destinations_and_ancestors(self):
        for checkout in (self.root, self.old, self.settings, self.work / "checkout"):
            with self.subTest(checkout=checkout), self.assertRaisesRegex(drill.DrillError, "checkout"):
                self.run_drill(checkout=checkout)
        self.assertFalse(self.work.exists())

    def test_rejects_link_inputs_without_following_them(self):
        real_link = Path.is_symlink

        def link(path):
            return path == self.settings / "online.json" or real_link(path)

        with mock.patch.object(Path, "is_symlink", autospec=True, side_effect=link), self.assertRaisesRegex(drill.DrillError, "plain file"):
            self.run_drill()
        self.assertFalse(self.work.exists())

    def test_failure_output_does_not_include_oserror_path(self):
        output = io.StringIO()
        argv = ["--old-install", "fake-old", "--settings-copy", "fake-copy", "--work", "fake-work"]
        with mock.patch.object(drill, "run_drill", side_effect=OSError("private-player-path")), contextlib.redirect_stdout(output):
            self.assertEqual(drill.main(argv), 1)
        self.assertIn("COEXISTENCE DRILL FAIL", output.getvalue())
        self.assertNotIn("private-player-path", output.getvalue())

    def test_success_output_is_scoped_and_does_not_print_source_paths(self):
        output = io.StringIO()
        argv = ["--old-install", "fake-old", "--settings-copy", "fake-copy", "--work", "fake-work"]
        with mock.patch.object(drill, "run_drill", return_value=dict(ok=True)), contextlib.redirect_stdout(output):
            self.assertEqual(drill.main(argv), 0)
        self.assertIn("COEXISTENCE DRILL PASS: offline settings setup only", output.getvalue())
        self.assertIn("signed update not tested", output.getvalue())
        self.assertNotIn("fake-", output.getvalue())


if __name__ == "__main__":
    unittest.main()
