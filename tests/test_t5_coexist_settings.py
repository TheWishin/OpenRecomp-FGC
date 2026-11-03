"""Side-by-side settings with synthetic JSON and an inert native settings contract."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp.adapters.t5_coexist import load_settings, local_path, readonly_imports


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
        # An OpenRecomp edit from a 1.1.9 install (always_left only) must still choose the side on 1.2.0.
        self.core.DEFAULTS.update(screen_side="dealt", always_left=False)
        settings = self.load()
        settings["always_left"] = True
        settings.save()
        self.assertEqual(self.load()["screen_side"], "left")
        path = Path(settings.private_path("settings.json"))
        path.write_text(json.dumps(dict(always_left=True, screen_side="right")), encoding="utf-8")
        self.assertEqual(self.load()["screen_side"], "right")
        del self.core.DEFAULTS["screen_side"]
        path.write_text(json.dumps(dict(always_left=True)), encoding="utf-8")
        self.assertNotIn("screen_side", self.load())

    def test_explicit_change_saves_only_override_and_leaves_native_unknown_fields(self):
        settings = self.load()
        before = self.source.read_bytes()
        settings["display"] = "borderless"
        settings.save()
        path = Path(settings.private_path("settings.json"))
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"display": "borderless"})
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(settings.env_overrides()["DISPLAY_CHOICE"], "borderless")
        self.assertEqual(self.native.saves, 0)
        self.assertEqual(self.load()["display"], "borderless")

    def test_save_merges_unknown_private_fields_and_new_native_settings_are_read(self):
        settings = self.load()
        path = Path(settings.private_path("settings.json"))
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"private_future": [1, 2]}), encoding="utf-8")
        settings["display"] = "maximized"
        settings.save()
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")),
                         {"private_future": [1, 2], "display": "maximized"})
        changed = dict(self.original, replay_dir=str(self.root / "another-replay-folder"))
        self.source.write_text(json.dumps(changed), encoding="utf-8")
        fresh = self.load()
        self.assertEqual(fresh.replay_dir, changed["replay_dir"])
        self.assertEqual(fresh["private_future"], [1, 2])

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

    def test_failed_publish_keeps_source_override_and_pending_edit(self):
        settings = self.load()
        settings["display"] = "maximized"
        settings.save()
        path = Path(settings.private_path("settings.json"))
        before = path.read_bytes()
        settings["display"] = "borderless"
        with mock.patch("openrecomp.adapters.t5_coexist.os.replace", side_effect=OSError("synthetic full disk")):
            with self.assertRaises(OSError):
                settings.save()
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(path.parent.iterdir()), [path])
        settings.save()
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["display"], "borderless")

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
        self.assertEqual(settings.env_overrides()["PS3_CONTROLS"], str(controls))
        self.assertEqual(settings.legacy_online_paths, (str(copy / "online.json"),))
        self.assertFalse(self.home.exists())
        private = Path(settings.controls_write_path)
        private.parent.mkdir(parents=True)
        private.write_text("{}", encoding="utf-8")
        self.assertEqual(settings.env_overrides()["PS3_CONTROLS"], str(private))
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
