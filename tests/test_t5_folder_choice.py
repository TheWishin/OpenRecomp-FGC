"""T5DR folder choices use synthetic metadata and inert file markers only."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp import adapters
from openrecomp.adapters.base import Adapter, Missing
from openrecomp.adapters import t5dr
from openrecomp.app_game_setup import GameSetupBackend


ROOT = Path(__file__).resolve().parents[1]


class FolderLayout(unittest.TestCase):
    def setUp(self):
        home = ROOT / "build" / "tmp-home"
        home.mkdir(parents=True, exist_ok=True)
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="t5-choice-", dir=home)))
        self.files = {}
        self.real_isfile = os.path.isfile
        self.enterContext(mock.patch.object(t5dr.os.path, "isfile", side_effect=self.isfile))
        self.process = self.enterContext(mock.patch.object(t5dr.subprocess, "run"))
        self.runtime = self.enterContext(mock.patch.object(t5dr, "load_runtime"))

    def isfile(self, path):
        return self.real_isfile(self.files.get(os.path.realpath(path), path))

    def install(self, name, version="1.2.0"):
        root = self.folder / name
        (root / "python").mkdir(parents=True)
        (root / "release.json").write_text(json.dumps(dict(version=version)), encoding="utf-8")
        for relative, marker in (("T5DR Online.exe", ".launcher-marker"),
                                 ("python/python.exe", "python/.python-marker")):
            inert = root / marker
            inert.write_text("inert file identity", encoding="utf-8")
            self.files[str(root / relative)] = inert
        return root

    def candidates(self, chosen):
        result = t5dr.root_candidates(str(chosen))
        self.process.assert_not_called()
        self.runtime.assert_not_called()
        return result


class FolderChoices(FolderLayout):
    def test_exact_root_wins_without_looking_at_another_install_below_it(self):
        root = self.install("exact")
        self.install("exact/another")
        with mock.patch.object(t5dr.os, "scandir", side_effect=AssertionError("exact root needs no scan")):
            self.assertEqual(self.candidates(root), [str(root.resolve())])

    def test_selected_parent_resolves_its_only_direct_install_child(self):
        root = self.install("wrapper/install")
        self.assertEqual(self.candidates(root.parent), [str(root.resolve())])

    def test_native_and_folders_up_to_three_levels_below_install_find_the_root(self):
        root = self.install("install")
        for relative in ("native", "native/build", "native/build/detail"):
            with self.subTest(relative=relative):
                chosen = root / relative
                chosen.mkdir(parents=True, exist_ok=True)
                self.assertEqual(self.candidates(chosen), [str(root.resolve())])

    def test_parent_search_stops_after_three_levels(self):
        root = self.install("install")
        chosen = root / "native" / "build" / "detail" / "below-limit"
        chosen.mkdir(parents=True)
        self.assertEqual(self.candidates(chosen), [])

    def test_search_does_not_descend_into_grandchildren(self):
        root = self.install("wrapper/nested/install")
        self.assertEqual(self.candidates(root.parent.parent), [])

    def test_search_does_not_scan_siblings_of_a_selected_output_folder(self):
        self.install("wrapper/other-install")
        chosen = self.folder / "wrapper" / "output"
        chosen.mkdir()
        self.assertEqual(self.candidates(chosen), [])

    def test_several_children_are_returned_in_deterministic_order_for_player_choice(self):
        zed = self.install("wrapper/zed")
        alpha = self.install("wrapper/Alpha")
        self.assertEqual(self.candidates(alpha.parent), [str(alpha.resolve()), str(zed.resolve())])

    def test_matching_parent_and_child_are_both_returned_without_arbitrary_selection(self):
        parent = self.install("outer")
        child = self.install("outer/selected/child")
        self.assertEqual(self.candidates(child.parent), [str(parent.resolve()), str(child.resolve())])

    def test_each_required_marker_must_be_a_file_even_with_launcher_code_present(self):
        for index, missing in enumerate(("T5DR Online.exe", "release.json", "python/python.exe")):
            with self.subTest(missing=missing):
                root = self.install(f"incomplete-{index}")
                (root / "launcher").mkdir()
                (root / "launcher" / "core.py").write_text("# inert marker\n", encoding="utf-8")
                path = root / missing
                marker = self.files.get(str(path), path)
                marker.unlink()
                path.mkdir()
                self.assertEqual(self.candidates(root), [])

    def test_unreadable_selected_folder_does_not_hide_a_matching_parent(self):
        root = self.install("install")
        chosen = root / "native"
        chosen.mkdir()
        with mock.patch.object(t5dr.os, "scandir", side_effect=PermissionError("synthetic unreadable folder")):
            self.assertEqual(self.candidates(chosen), [str(root.resolve())])

    def test_unreadable_or_missing_folder_returns_no_candidates(self):
        chosen = self.folder / "empty"
        chosen.mkdir()
        with mock.patch.object(t5dr.os, "scandir", side_effect=PermissionError("synthetic unreadable folder")):
            self.assertEqual(self.candidates(chosen), [])
        self.assertEqual(self.candidates(self.folder / "missing"), [])

    def test_candidates_are_canonical_and_duplicate_aliases_are_removed(self):
        root = self.install("wrapper/install")
        alias = self.folder / "wrapper" / "alias"
        alias.mkdir()
        realpath = os.path.realpath

        def resolve(path, *args, **kwargs):
            path = os.fspath(path)
            if path == str(alias) or path.startswith(str(alias) + os.sep):
                path = str(root) + path[len(str(alias)):]
            return realpath(path, *args, **kwargs)

        with mock.patch.object(t5dr.os.path, "realpath", side_effect=resolve):
            self.assertEqual(self.candidates(root.parent), [str(root.resolve())])

    def test_only_legacy_1_1_releases_offer_the_old_install_update(self):
        root = self.install("version")
        for version, expected in (("1.1.0", True), ("v1.1.9", True), ("1.1.10-beta.1", True),
                                  ("1.0.9", False), ("1.2.0", False), ("2.1.0", False),
                                  ("invalid", False), (None, False), (12, False)):
            with self.subTest(version=version):
                (root / "release.json").write_text(json.dumps(dict(version=version)), encoding="utf-8")
                self.assertEqual(t5dr.legacy_install(str(root)), expected)
        (root / "release.json").write_text("[]", encoding="utf-8")
        self.assertFalse(t5dr.legacy_install(str(root)))
        (root / "release.json").unlink()
        self.assertFalse(t5dr.legacy_install(str(root)))

    def test_legacy_factory_never_imports_old_runtime_and_keeps_an_update_target(self):
        root = self.install("legacy", version="1.1.9")
        manifest = dict(id="t5dr", adapter="t5dr", short="T5DR")
        config = dict(roots=dict(t5dr=str(root)))
        adapter = adapters.make(manifest, config)
        self.assertIsInstance(adapter, t5dr.LegacyT5DR)
        self.assertFalse(adapter.found())
        self.assertEqual(adapter.setup_root(), str(root))
        self.assertEqual(adapter.problem, "@t5.folder_old")
        self.runtime.assert_not_called()
        self.process.assert_not_called()

    def test_current_release_keeps_the_current_adapter_path(self):
        root = self.install("current", version="1.2.0")
        manifest = dict(id="t5dr", adapter="t5dr", short="T5DR")
        config = dict(roots=dict(t5dr=str(root)))
        with mock.patch.object(t5dr, "T5DR") as current:
            self.assertIs(adapters.make(manifest, config), current.return_value)
        current.assert_called_once_with(manifest, config, str(root))

    def test_source_choice_interface_does_not_register_until_a_root_is_selected(self):
        first = self.install("wrapper/first")
        second = self.install("wrapper/second")
        config = dict(roots=dict(t5dr="previous"), t5dr_settings_copy="previous-copy")
        manifest = dict(id="t5dr", adapter="t5dr")
        for adapter in (Missing(manifest, config), object.__new__(t5dr.T5DR)):
            with self.subTest(adapter=type(adapter).__name__):
                adapter.m, adapter.config, adapter.root = manifest, config, "previous"
                self.assertEqual(adapter.source_choices("folder", str(first.parent)),
                                 [str(first.resolve()), str(second.resolve())])
                self.assertIsNone(adapter.source_choices("pkg", str(first.parent)))
                self.assertEqual(adapter.set_source("folder", str(first.parent)), "@t5.install_incomplete_python")
                self.assertEqual(config, dict(roots=dict(t5dr="previous"), t5dr_settings_copy="previous-copy"))
        self.assertIsNone(Adapter(manifest).source_choices("folder", str(first.parent)))

    def test_legacy_backend_checks_and_updates_the_existing_folder_without_fresh_install(self):
        root = self.install("legacy", version="1.1.9")
        adapter = t5dr.LegacyT5DR(dict(id="t5dr", adapter="t5dr"), {}, str(root))
        backend = GameSetupBackend()
        backend.nav = SimpleNamespace(game_by_id=lambda gid: SimpleNamespace(a=adapter) if gid == "t5dr" else None,
                                      close_online=mock.Mock())
        backend._update_busy = mock.Mock(return_value=False)
        backend.setup = SimpleNamespace(check=mock.Mock(return_value=True), update=mock.Mock(return_value=True),
                                        install=mock.Mock())
        self.assertEqual(backend._setup_root("t5dr"), str(root))
        self.assertIsNone(backend._setup_root("absent"))
        self.assertTrue(backend._setup_action("check", "t5dr", True))
        backend.setup.check.assert_called_once_with("t5dr", str(root), force=True)
        self.assertFalse(backend._setup_action("install", "t5dr", str(root.parent)))
        backend.setup.install.assert_not_called()
        self.assertTrue(backend._setup_action("update", "t5dr", None))
        backend.nav.close_online.assert_called_once_with(only="t5dr")
        backend.setup.update.assert_called_once_with("t5dr", str(root))
        self.runtime.assert_not_called()


if __name__ == "__main__":
    unittest.main()
