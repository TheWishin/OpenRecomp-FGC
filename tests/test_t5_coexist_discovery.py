"""Side-by-side registration uses synthetic metadata and inert runtime objects."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp.adapters import t5dr


MANIFEST = dict(id="t5dr", adapter="t5dr", locations=[])


class Discovery(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory(dir=Path(__file__).parent)))
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_T5DR_ROOT=""))

    def install(self, name, version="1.1.9", built=False):
        root = self.folder / name
        (root / "launcher").mkdir(parents=True)
        (root / "launcher" / "core.py").write_text("# Inert discovery marker.\n", encoding="utf-8")
        (root / "release.json").write_text(json.dumps(dict(version=version)), encoding="utf-8")
        if built:
            self.stamp(root / "native")
        return root

    def stamp(self, output):
        (output / "build").mkdir(parents=True)
        (output / "build" / "t5dr_build.json").write_text('{"code_id":"synthetic"}', encoding="utf-8")

    def find(self, *roots, config=None):
        manifest = dict(MANIFEST, locations=[str(root) for root in roots])
        return t5dr.find_root(manifest, config or {})

    def test_built_install_wins_over_newer_unbuilt_shipped_runtime(self):
        built = self.install("older", built=True)
        newer = self.install("newer", version="1.2.0")
        real_isfile = os.path.isfile
        runtime = str(newer / "runtime" / "t5dr.exe")
        with mock.patch.object(t5dr.os.path, "isfile", side_effect=lambda path: path == runtime or real_isfile(path)):
            self.assertEqual(self.find(built, newer), str(built))

    def test_newest_install_is_fallback_without_a_build_stamp(self):
        old = self.install("older")
        new = self.install("newer", version="1.2.0")
        self.assertEqual(self.find(old, new), str(new))

    def test_declared_output_stamp_is_used_without_loading_native_code(self):
        old = self.install("custom")
        self.stamp(old / "custom-output")
        (old / "launcher.json").write_text('{"out_dir":"custom-output"}', encoding="utf-8")
        new = self.install("newer", version="1.2.0")
        with mock.patch.object(t5dr.importlib.util, "spec_from_file_location", side_effect=AssertionError("no import")):
            self.assertEqual(self.find(new, old), str(old))

    def test_explicit_root_and_environment_are_authoritative_without_fallback(self):
        old = self.install("chosen")
        new = self.install("newer", version="1.2.0", built=True)
        cfg = dict(roots=dict(t5dr=str(old)))
        self.assertEqual(self.find(new, config=cfg), str(old))
        cfg["roots"]["t5dr"] = str(self.folder / "missing")
        self.assertIsNone(self.find(new, config=cfg))
        with mock.patch.dict(os.environ, OPENRECOMP_T5DR_ROOT=str(old)):
            self.assertEqual(self.find(new), str(old))

    def test_enclosing_folder_requires_exactly_one_install(self):
        root = self.install("wrapper/only")
        self.assertEqual(t5dr.install_root(root.parent), str(root))
        self.install("wrapper/second")
        self.assertIsNone(t5dr.install_root(root.parent))

    def test_discovery_keeps_all_existing_bytes_and_does_not_make_private_data(self):
        root = self.install("existing", built=True)
        settings = root / "launcher.json"
        settings.write_text('{"unrecognized":{"keep":true}}', encoding="utf-8")
        before = {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}
        self.assertEqual(self.find(root), str(root))
        after = {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}
        self.assertEqual(after, before)

    def test_builtin_manifest_finds_downloaded_release_and_wrapped_extraction(self):
        builtin = json.loads((Path(__file__).parent.parent / "games" / "t5dr.json").read_text(encoding="utf-8"))
        self.assertEqual(builtin["locations"], [])
        root = self.install("Downloads/T5DR-Online-1.1.9/T5DR-Online-1.1.9", built=True)
        with mock.patch.dict(os.environ, USERPROFILE=str(self.folder)):
            self.assertEqual(t5dr.find_root(builtin, {}), str(root))

    def test_default_discovery_covers_desktop_with_empty_or_absent_locations(self):
        root = self.install("Desktop/T5DR-Online-1.1.9", built=True)
        for manifest in (MANIFEST, dict(id="t5dr", adapter="t5dr")):
            with self.subTest(manifest=manifest), mock.patch.dict(os.environ, USERPROFILE=str(self.folder)):
                self.assertEqual(t5dr.find_root(manifest, {}), str(root))

    def test_custom_locations_do_not_fall_back_to_default_discovery(self):
        chosen = self.install("custom", version="1.1.9")
        self.install("Downloads/T5DR-Online-1.2.0", version="1.2.0", built=True)
        with mock.patch.dict(os.environ, USERPROFILE=str(self.folder)):
            self.assertEqual(self.find(chosen), str(chosen))
            self.assertIsNone(self.find(self.folder / "missing"))

    def test_unreadable_or_nonobject_versions_do_not_break_discovery(self):
        root = self.install("malformed")
        for content in ("[]", "null", '{"version":3}', '{"version":"bad"}'):
            with self.subTest(content=content):
                (root / "release.json").write_text(content, encoding="utf-8")
                self.assertEqual(t5dr.version_key(root), (0,))

    def test_install_beside_the_launcher_folder_is_found_first(self):
        # Test bundle layout: <folder>/OpenRecomp-FGC (this launcher), <folder>/T4, <folder>/T5DR-Online-1.2.0.
        launcher = self.folder / "bundle" / "OpenRecomp-FGC"
        adapter = launcher / "openrecomp" / "adapters" / "t5dr.py"
        sibling = self.install("bundle/T5DR-Online-1.2.0", version="1.2.0")
        downloads = self.install("Downloads/T5DR-Online-1.2.1", version="1.2.1", built=True)
        with mock.patch.object(t5dr, "__file__", str(adapter)):
            self.assertEqual(t5dr.sibling_locations(), [str(self.folder / "bundle" / "T5DR-Online-*")])
            self.assertEqual(self.find(downloads), str(sibling))
            # A chosen folder still wins; without a sibling the old search is unchanged.
            self.assertEqual(self.find(downloads, config=dict(roots=dict(t5dr=str(downloads)))), str(downloads))
        with mock.patch.object(t5dr, "__file__", str(self.folder / "elsewhere" / "openrecomp" / "adapters" / "t5dr.py")):
            self.assertEqual(self.find(downloads), str(downloads))

    def test_brackets_in_the_bundle_folder_name_are_not_patterns(self):
        launcher = self.folder / "test [1]" / "OpenRecomp-FGC"
        sibling = self.install("test [1]/T5DR-Online-1.2.0", version="1.2.0")
        with mock.patch.object(t5dr, "__file__", str(launcher / "openrecomp" / "adapters" / "t5dr.py")):
            self.assertEqual(self.find(), str(sibling))


class BorrowedInstall(unittest.TestCase):
    def adapter(self, compatibility="same", state=None):
        adapter = object.__new__(t5dr.T5DR)
        adapter.m, adapter.config = MANIFEST, {}
        adapter.root = "synthetic-install"
        adapter.s = SimpleNamespace(coexistence=True, out_dir="synthetic-output", online_config_path="private-online.json")
        adapter.core = SimpleNamespace(game_state=mock.Mock(return_value=state or dict(ok=True, built=True, needs_rebuild=False)),
                                       BuildRun=mock.Mock())
        adapter.release = mock.Mock(return_value=dict(version="1.1.9", code_id="synthetic"))
        adapter._state = None
        self.enterContext(mock.patch.object(t5dr, "build_compatibility", return_value=compatibility))
        return adapter

    def test_constructor_uses_isolated_settings_and_explicit_drill_source(self):
        settings = SimpleNamespace(coexistence=True)
        core = SimpleNamespace(Settings=mock.Mock(side_effect=AssertionError("helper must control settings")))
        config = dict(t5dr_settings_copy="synthetic-settings-copy")
        with mock.patch.object(t5dr, "load_settings", return_value=settings) as load:
            adapter = t5dr.T5DR(MANIFEST, config, "synthetic-install", core=core)
        self.assertIs(adapter.s, settings)
        load.assert_called_once_with(core, "synthetic-install", settings_source="synthetic-settings-copy")
        core.Settings.assert_not_called()

    def test_build_code_identity_overrides_optimistic_runtime_state(self):
        for compatibility, ready in (("same", True), ("different", False), ("unknown", False)):
            with self.subTest(compatibility=compatibility):
                adapter = self.adapter(compatibility)
                self.assertEqual(adapter.ready(), ready)
                self.assertEqual(adapter.state()["compatibility"], compatibility)
                self.assertEqual(adapter.coexistence_state(), dict(active=True, source="synthetic-install", build=compatibility))

    def test_borrowed_build_and_package_changes_stop_before_native_calls(self):
        adapter = self.adapter()
        self.assertEqual(adapter.build_ready(), "@t5.coexist.build_blocked")
        for action in (lambda: adapter.build_start(), lambda: adapter.build_start(force=True),
                       lambda: adapter.set_source("pkg", "synthetic.pkg"), lambda: adapter.set_source("rap", "synthetic.rap")):
            with self.assertRaisesRegex(RuntimeError, "t5.coexist.build_blocked"):
                action()
        adapter.core.BuildRun.assert_not_called()

    def test_state_refreshes_when_old_launcher_changes_the_build(self):
        adapter = self.adapter()
        self.assertTrue(adapter.ready())
        adapter.core.game_state.return_value = dict(ok=False, built=False, needs_rebuild=False)
        started = []

        class Worker:
            def __init__(self, target, name, daemon):
                started.append(target)

            def start(self):
                pass

        with mock.patch.object(t5dr, "build_compatibility", return_value="unknown"),                 mock.patch.object(t5dr.threading, "Thread", Worker):
            # Asked again at once (every redraw): the window never waits for the game's files.
            self.assertTrue(adapter.ready())
            self.assertEqual(started, [])
            adapter._state_at -= t5dr.STATE_SECONDS
            self.assertTrue(adapter.ready())          # the old answer now, the new one is read on a worker
            self.assertTrue(adapter.ready())
            self.assertEqual(len(started), 1)
            started[0]()
            self.assertFalse(adapter.ready())
            self.assertEqual(adapter.state()["compatibility"], "unknown")
        self.assertEqual(adapter.core.game_state.call_count, 2)

    def test_state_fresh_reads_at_once(self):
        adapter = self.adapter()
        self.assertTrue(adapter.ready())
        adapter.core.game_state.return_value = dict(ok=False, built=False, needs_rebuild=False)
        with mock.patch.object(t5dr, "build_compatibility", return_value="unknown"):
            self.assertFalse(adapter.state(fresh=True)["ok"])

    def test_invalid_new_folder_preserves_registered_root(self):
        adapter = self.adapter()
        adapter.config["roots"] = dict(t5dr="previous")
        adapter.config["t5dr_settings_copy"] = "previous-settings-copy"
        with mock.patch.object(t5dr, "root_candidates", return_value=[]):
            self.assertEqual(adapter.set_source("folder", "invalid"), "@t5.install_incomplete_python")
        self.assertEqual(adapter.config["roots"]["t5dr"], "previous")
        self.assertEqual(adapter.config["t5dr_settings_copy"], "previous-settings-copy")
        with mock.patch.object(t5dr, "root_candidates", return_value=["validated"]):
            self.assertEqual(adapter.set_source("folder", "chosen"), "reload")
        self.assertEqual(adapter.config["roots"]["t5dr"], "validated")
        self.assertNotIn("t5dr_settings_copy", adapter.config)

    def test_same_install_reselection_keeps_its_explicit_settings_copy(self):
        adapter = self.adapter()
        adapter.config["t5dr_settings_copy"] = "same-install-copy"
        with mock.patch.object(t5dr, "root_candidates", return_value=[adapter.root]):
            self.assertEqual(adapter.set_source("folder", adapter.root), "reload")
        self.assertEqual(adapter.config["t5dr_settings_copy"], "same-install-copy")

    def test_picture_runtime_import_suppresses_bytecode_without_reading_art(self):
        adapter = self.adapter()
        flags = []
        previous = sys.dont_write_bytecode

        def load(name):
            flags.append(sys.dont_write_bytecode)
            return SimpleNamespace(ra=SimpleNamespace(find_sources=lambda output: []))

        with mock.patch.object(t5dr.importlib, "import_module", side_effect=load):
            adapter._make_hero(0, "unused-output")
        self.assertEqual(flags, [True])
        self.assertEqual(sys.dont_write_bytecode, previous)

    def test_fighter_preferences_read_legacy_view_and_write_only_private_overlay(self):
        adapter = self.adapter()
        adapter._online_config = mock.Mock(return_value=dict(char="saved-fighter"))
        adapter._online_write_preferences = mock.Mock()
        self.assertEqual(adapter.online_cfg_path(), "private-online.json")
        self.assertEqual(adapter.chosen_fighter(), "saved-fighter")
        adapter.set_fighter("new-choice")
        adapter._online_write_preferences.assert_called_once_with(dict(char="new-choice"))


class RuntimeBytecode(unittest.TestCase):
    def test_runtime_import_suppresses_bytecode_and_restores_flag_even_on_failure(self):
        name = "openrecomp_synthetic_attachment"
        previous = sys.dont_write_bytecode
        for fail in (False, True):
            with self.subTest(fail=fail):
                flags = []

                class Loader:
                    def create_module(self, spec):
                        return None

                    def exec_module(self, module):
                        flags.append(sys.dont_write_bytecode)
                        if fail:
                            raise ImportError("synthetic failure")

                spec = importlib.util.spec_from_loader(name, Loader())
                with mock.patch.object(t5dr.importlib.util, "spec_from_file_location", return_value=spec):
                    try:
                        if fail:
                            with self.assertRaises(ImportError):
                                t5dr.load_runtime("synthetic-install", name)
                            self.assertNotIn(name, sys.modules)
                        else:
                            t5dr.load_runtime("synthetic-install", name)
                    finally:
                        sys.modules.pop(name, None)
                self.assertEqual(flags, [True])
                self.assertEqual(sys.dont_write_bytecode, previous)


if __name__ == "__main__":
    unittest.main()
