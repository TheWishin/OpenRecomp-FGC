"""Adapter safety checks use only synthetic settings and in-memory runtime objects."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp import manifest
from openrecomp.adapters.base import Adapter
from openrecomp.adapters.t4 import T4
from openrecomp.adapters.t5dr import T5DR, load_runtime


class FighterSettingsSafety(unittest.TestCase):
    def setUp(self):
        self.folder = self.enterContext(tempfile.TemporaryDirectory(dir=Path(__file__).parent))
        self.path = Path(self.folder) / "online.json"
        self.adapter = object.__new__(T5DR)
        self.adapter.online_cfg_path = lambda: str(self.path)

    def test_invalid_existing_settings_are_preserved_byte_for_byte(self):
        for content in (b'{"char": "old",', b'[]', b'null', b'"text"', b'\xff'):
            with self.subTest(content=content):
                self.path.write_bytes(content)
                with self.assertRaises((ValueError, UnicodeError)):
                    self.adapter.set_fighter("random")
                self.assertEqual(self.path.read_bytes(), content)
                self.assertEqual(list(Path(self.folder).iterdir()), [self.path])

    def test_read_error_does_not_replace_existing_settings(self):
        original = b'{"char": "old", "unrelated": [1, 2]}'
        self.path.write_bytes(original)
        real_open = open

        def denied(path, *args, **kwargs):
            if os.fspath(path) == str(self.path):
                raise PermissionError("synthetic denial")
            return real_open(path, *args, **kwargs)

        with mock.patch("builtins.open", side_effect=denied):
            with self.assertRaises(PermissionError):
                self.adapter.set_fighter("random")
        self.assertEqual(self.path.read_bytes(), original)

    def test_changing_fighter_keeps_unrelated_settings_and_creates_missing_file(self):
        expected = dict(char="old", unrelated=dict(list=[1, 2], enabled=True))
        self.path.write_text(json.dumps(expected), encoding="utf-8")
        self.adapter.set_fighter("random")
        expected["char"] = "random"
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), expected)
        self.path.unlink()
        self.adapter.set_fighter("random")
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), dict(char="random"))
        self.assertEqual(list(Path(self.folder).iterdir()), [self.path])

    def test_publish_error_cleans_temporary_file_and_preserves_original(self):
        original = b'{"char": "old"}'
        self.path.write_bytes(original)
        with mock.patch("openrecomp.adapters.t5dr.os.replace", side_effect=OSError("synthetic failure")):
            with self.assertRaises(OSError):
                self.adapter.set_fighter("random")
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(Path(self.folder).iterdir()), [self.path])


class RuntimeSafety(unittest.TestCase):
    def test_runtime_from_another_install_is_rejected_without_execution(self):
        root = os.path.join(os.path.dirname(__file__), "synthetic-selected")
        for name in ("core", "replays"):
            with self.subTest(module=name):
                expected = {module: SimpleNamespace(
                    __file__=os.path.join(root, "launcher", module + ".py"), Settings=lambda: {})
                    for module in ("core", "replays")}
                cached = SimpleNamespace(__file__=os.path.join(os.path.dirname(__file__), "synthetic-other", name + ".py"),
                                         Settings=lambda: {})
                expected[name] = cached
                with mock.patch.dict(sys.modules, expected), mock.patch.object(sys, "path", list(sys.path)), mock.patch(
                        "openrecomp.adapters.t5dr.importlib.util.spec_from_file_location") as load:
                    with self.assertRaises(ImportError):
                        T5DR(dict(id="test"), {}, root)
                    self.assertIs(sys.modules[name], cached)
                    load.assert_not_called()

    def test_cached_runtime_from_selected_install_is_used(self):
        root = os.path.join(os.path.dirname(__file__), "synthetic-selected")
        cached = SimpleNamespace(__file__=os.path.join(root, "launcher", "core.py"))
        with mock.patch.dict(sys.modules, {"core": cached}):
            self.assertIs(load_runtime(root, "core"), cached)

    def test_conflicting_dependency_is_rejected_before_loading_core(self):
        root = os.path.join(os.path.dirname(__file__), "synthetic-selected")
        cached = SimpleNamespace(__file__=os.path.join(os.path.dirname(__file__), "synthetic-other", "replays.py"))
        with mock.patch.dict(sys.modules, {"replays": cached}), mock.patch(
                "openrecomp.adapters.t5dr.importlib.util.spec_from_file_location") as load:
            sys.modules.pop("core", None)
            with self.assertRaises(ImportError):
                T5DR(dict(id="test"), {}, root)
            load.assert_not_called()

    def test_failed_wait_releases_game_lock_without_saving_a_record(self):
        a = object.__new__(T4)
        a.s = dict(existing="preserved")
        a.core = SimpleNamespace(release_run_lock=mock.Mock(), save_settings=mock.Mock())
        run = SimpleNamespace(wait=mock.Mock(side_effect=OSError("synthetic wait failure")))
        with self.assertRaises(OSError):
            a._wait(run)
        a.core.release_run_lock.assert_called_once_with()
        a.core.save_settings.assert_not_called()
        self.assertEqual(a.s, dict(existing="preserved"))

    def test_legacy_native_search_entry_point_has_no_effect(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            a = object.__new__(T5DR)
            a.root = folder
            (Path(folder) / "release.json").write_text('{"version": "1.2.0"}', encoding="utf-8")
            with mock.patch.object(T5DR, "_exe_launcher") as native:
                for action in ("ranked", "casual", "lobby"):
                    self.assertEqual(a.run_online(action), "")
                native.assert_not_called()
        self.assertIs(T5DR.run_online, Adapter.run_online)

    def test_nonobject_release_metadata_does_not_break_version_display(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            a = object.__new__(T5DR)
            a.root = folder
            for content in ("[]", "null", '"text"'):
                with self.subTest(content=content):
                    (Path(folder) / "release.json").write_text(content, encoding="utf-8")
                    self.assertEqual(a.release(), {})


class LauncherSettingsSafety(unittest.TestCase):
    def setUp(self):
        self.folder = self.enterContext(tempfile.TemporaryDirectory(dir=Path(__file__).parent))
        self.path = Path(self.folder) / "config.json"
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_HOME=self.folder))

    def test_tolerant_load_cannot_destroy_malformed_existing_config_on_save(self):
        for content in (b'{"roots":', b'[]', b'null', b'"text"', b'\xff'):
            with self.subTest(content=content):
                self.path.write_bytes(content)
                cfg = manifest.load_config()
                self.assertEqual(cfg, {})
                cfg["language"] = "ja"
                with self.assertRaises(ValueError):
                    manifest.save_config(cfg)
                self.assertEqual(self.path.read_bytes(), content)
                self.assertEqual(list(Path(self.folder).iterdir()), [self.path])

    def test_unreadable_existing_config_is_preserved(self):
        content = b'{"language": "ja", "unrelated": [1, 2]}'
        self.path.write_bytes(content)
        real_open = open

        def denied(path, *args, **kwargs):
            if os.fspath(path) == str(self.path):
                raise PermissionError("synthetic denial")
            return real_open(path, *args, **kwargs)

        with mock.patch("builtins.open", side_effect=denied):
            cfg = manifest.load_config()
            self.assertEqual(cfg, {})
            with self.assertRaises(PermissionError):
                manifest.save_config(dict(language="de"))
        self.assertEqual(self.path.read_bytes(), content)
        self.assertEqual(list(Path(self.folder).iterdir()), [self.path])

    def test_valid_and_missing_config_round_trip_without_extra_fields(self):
        cfg = dict(language="ja", unrelated=dict(enabled=True, values=[1, 2]))
        manifest.save_config(cfg)
        self.assertEqual(manifest.load_config(), cfg)
        cfg["language"] = "de"
        manifest.save_config(cfg)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), cfg)
        self.assertEqual(list(Path(self.folder).iterdir()), [self.path])

    def test_failed_publish_preserves_config_and_cleans_temp_file(self):
        content = b'{"language": "ja"}'
        self.path.write_bytes(content)
        with mock.patch("openrecomp.manifest.os.replace", side_effect=OSError("synthetic failure")):
            with self.assertRaises(OSError):
                manifest.save_config(dict(language="de"))
        self.assertEqual(self.path.read_bytes(), content)
        self.assertEqual(list(Path(self.folder).iterdir()), [self.path])

    def test_failed_serialization_preserves_config_and_cleans_temp_file(self):
        content = b'{"language": "ja"}'
        self.path.write_bytes(content)
        with self.assertRaises(TypeError):
            manifest.save_config(dict(unserializable=object()))
        self.assertEqual(self.path.read_bytes(), content)
        self.assertEqual(list(Path(self.folder).iterdir()), [self.path])


if __name__ == "__main__":
    unittest.main()
