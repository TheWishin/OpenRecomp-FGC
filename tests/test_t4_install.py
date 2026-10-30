"""T4 registration uses only synthetic archive entries and never starts/imports a game."""
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock
import zipfile

from openrecomp.adapters import make
from openrecomp.adapters.base import Missing
from openrecomp.adapters.t4 import T4, find_root, load_core
from openrecomp.adapters import t4_install


MANIFEST = dict(id="t4", adapter="t4", short="T4", locations=[])
MARKER = b"# Synthetic registration marker, not a game core.\n"


class T4Install(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext(tempfile.TemporaryDirectory(dir=Path(__file__).parent))
        self.folder = Path(self.tmp)
        self.home = self.folder / "user"
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_HOME=str(self.home), OPENRECOMP_T4_ROOT=""))
        self.cfg = {"language": "ja", "t4_graphics": {"aa": "smaa"}}

    def archive(self, entries):
        path = self.folder / "synthetic.zip"
        with zipfile.ZipFile(path, "w") as archive:
            for name, data in entries:
                if isinstance(name, str):
                    entry = zipfile.ZipInfo(name)
                    # ZipInfo normalizes Windows separators; keep the unsafe name under test.
                    entry.filename = name
                else:
                    entry = name
                archive.writestr(entry, data)
        return path

    def install(self, path):
        adapter = Missing(MANIFEST, self.cfg)
        self.assertEqual(adapter.set_source("folder", str(path)), "@t4.installing")
        adapter._source_thread.join(5)
        self.assertFalse(adapter.source_state()["running"])
        return adapter.source_state()["result"]

    def test_registration_runs_off_the_controller_thread_and_refuses_duplicate_work(self):
        adapter = Missing(MANIFEST, self.cfg)
        with mock.patch("openrecomp.adapters.base.threading.Thread") as worker:
            self.assertEqual(adapter.set_source("folder", "synthetic.zip"), "@t4.installing")
            self.assertTrue(adapter.source_state()["running"])
            self.assertEqual(adapter.set_source("folder", "other.zip"), "@t4.installing")
            worker.assert_called_once()
            worker.return_value.start.assert_called_once_with()

    def test_worker_start_failure_keeps_registration_available_and_error_visible(self):
        adapter = Missing(MANIFEST, self.cfg)
        with mock.patch("openrecomp.adapters.base.threading.Thread") as worker:
            worker.return_value.start.side_effect = RuntimeError("synthetic worker unavailable")
            self.assertEqual(adapter.set_source("folder", "synthetic.zip"), "@t4.install_failed")
        self.assertFalse(adapter.source_state()["running"])
        self.assertEqual(adapter.sources()[0]["note"], "@t4.install_failed")

    def test_missing_offers_zip_or_directory_without_loading_a_core(self):
        source = Missing(MANIFEST, self.cfg).sources()[0]
        self.assertEqual(source["kind"], "file_or_folder")
        self.assertEqual(source["exts"], [".zip"])

    def test_register_existing_install_or_enclosing_folder_and_preserve_settings(self):
        install = self.folder / "enclosing" / "T4-synthetic"
        (install / "launcher").mkdir(parents=True)
        (install / "launcher" / "t4core.py").write_bytes(MARKER)
        self.assertEqual(self.install(install.parent), "reload")
        self.assertEqual(find_root(MANIFEST, self.cfg), str(install.resolve()))
        self.assertEqual(self.cfg["language"], "ja")
        self.assertEqual(self.cfg["t4_graphics"], {"aa": "smaa"})
        self.assertFalse(self.home.exists())

    def test_flat_and_wrapped_zips_extract_under_home_and_find_adapter(self):
        for prefix in ("", "T4-synthetic/"):
            with self.subTest(prefix=prefix):
                path = self.archive([(prefix + "launcher/t4core.py", MARKER),
                                     (prefix + "docs/example.txt", b"synthetic data")])
                with mock.patch("openrecomp.adapters.t4.importlib.import_module", side_effect=AssertionError):
                    self.assertEqual(self.install(path), "reload")
                root = Path(self.cfg["roots"]["t4"])
                self.assertTrue(root.is_relative_to(self.home / "installs" / "t4"))
                self.assertEqual((root / "launcher" / "t4core.py").read_bytes(), MARKER)
                self.assertEqual(find_root(MANIFEST, self.cfg), str(root))
                with mock.patch("openrecomp.adapters.t4.T4", return_value="fake-adapter") as adapter:
                    self.assertEqual(make(MANIFEST, self.cfg), "fake-adapter")
                    adapter.assert_called_once_with(MANIFEST, self.cfg, str(root))
                self.assertEqual(self.install(path), "reload")
                self.assertEqual(self.cfg["roots"]["t4"], str(root))
                self.assertFalse(list((self.home / "installs" / "t4").glob("pending-*")))

    def test_bad_archive_paths_refused_before_any_extraction_or_registration(self):
        for bad in ("../escape.txt", "/escape.txt", "C:/escape.txt", "a\\escape.txt", "a/../escape.txt",
                    "a/./escape.txt", "a//escape.txt", "a/NUL.txt", "a/COM1", "a/foo. /bar.txt",
                    "a/b.txt:stream", "a/lpt²", "a/trailing."):
            with self.subTest(path=bad):
                path = self.archive([("launcher/t4core.py", MARKER), (bad, b"synthetic")])
                with zipfile.ZipFile(path) as archive:
                    self.assertEqual(archive.infolist()[1].orig_filename, bad)
                self.assertEqual(self.install(path), "@t4.zip_invalid")
                self.assertNotIn("roots", self.cfg)
                self.assertFalse(self.home.exists())

    def test_duplicate_case_and_file_directory_aliases_are_refused(self):
        for entries in ([('launcher/t4core.py', MARKER), ('LAUNCHER/T4CORE.PY', MARKER)],
                        [('launcher/t4core.py', MARKER), ('docs', b"synthetic"), ('docs/a.txt', b"synthetic")],
                        [('launcher/t4core.py', MARKER), ('docs/a.txt', b"synthetic"), ('docs', b"synthetic")]):
            with self.subTest(entries=entries):
                self.assertEqual(self.install(self.archive(entries)), "@t4.zip_invalid")
                self.assertNotIn("roots", self.cfg)

    def test_symlink_archive_entry_is_refused(self):
        link = zipfile.ZipInfo("link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        path = self.archive([("launcher/t4core.py", MARKER), (link, b"../outside")])
        self.assertEqual(self.install(path), "@t4.zip_invalid")
        self.assertNotIn("roots", self.cfg)

    def test_limits_wrong_or_ambiguous_install_and_bad_zip_keep_old_root(self):
        self.cfg["roots"] = {"t4": "synthetic-old-root"}
        for entries in ([("README.txt", b"synthetic")],
                        [("a/launcher/t4core.py", MARKER), ("b/launcher/t4core.py", MARKER)]):
            self.assertEqual(self.install(self.archive(entries)), "@t4.install_invalid")
            self.assertEqual(self.cfg["roots"]["t4"], "synthetic-old-root")
        path = self.archive([("launcher/t4core.py", MARKER)])
        with mock.patch.object(t4_install, "MAX_UNPACKED", 1):
            self.assertEqual(self.install(path), "@t4.zip_too_large")
        with mock.patch.object(t4_install, "MAX_ARCHIVE", 1):
            self.assertEqual(self.install(path), "@t4.zip_too_large")
        with mock.patch.object(t4_install, "MAX_FILES", 0):
            self.assertEqual(self.install(path), "@t4.zip_too_large")
        path.write_bytes(b"synthetic invalid zip")
        self.assertEqual(self.install(path), "@t4.install_failed")
        self.assertEqual(self.cfg["roots"]["t4"], "synthetic-old-root")

    def test_failed_extraction_cleans_stage_and_keeps_settings(self):
        path = self.archive([("launcher/t4core.py", MARKER)])
        with mock.patch.object(zipfile.ZipFile, "open", side_effect=OSError):
            self.assertEqual(self.install(path), "@t4.install_failed")
        self.assertNotIn("roots", self.cfg)
        self.assertEqual(list((self.home / "installs" / "t4").iterdir()), [])

    def test_switching_install_loads_its_own_core_and_caches_by_root(self):
        first = SimpleNamespace(load_settings=lambda: {"synthetic": "first"})
        second = SimpleNamespace(load_settings=lambda: {"synthetic": "second"})
        specs = [SimpleNamespace(loader=mock.Mock()), SimpleNamespace(loader=mock.Mock())]
        roots = [str(self.folder / "first"), str(self.folder / "second")]
        with mock.patch.dict(sys.modules), mock.patch.object(sys, "path", list(sys.path)), \
                mock.patch("openrecomp.adapters.t4.importlib.util.spec_from_file_location", side_effect=specs) as spec, \
                mock.patch("openrecomp.adapters.t4.importlib.util.module_from_spec", side_effect=[first, second]):
            a = T4(MANIFEST, self.cfg, roots[0])
            b = T4(MANIFEST, self.cfg, roots[1])
            self.assertIs(a.core, first)
            self.assertIs(b.core, second)
            self.assertIs(sys.modules["t4core"], second)
            self.assertEqual(a.s["synthetic"], "first")
            self.assertEqual(b.s["synthetic"], "second")
            self.assertNotEqual(spec.call_args_list[0].args[0], spec.call_args_list[1].args[0])
            self.assertEqual(spec.call_args_list[1].args[1], os.path.join(roots[1], "launcher", "t4core.py"))
            self.assertIs(load_core(roots[0]), first)
            self.assertEqual(spec.call_count, 2)
            self.assertEqual(sys.path[0], os.path.join(roots[0], "launcher"))

    def test_failed_core_load_restores_previous_module(self):
        previous = SimpleNamespace()
        core = SimpleNamespace()
        spec = SimpleNamespace(loader=SimpleNamespace(exec_module=mock.Mock(side_effect=RuntimeError("synthetic"))))
        with mock.patch.dict(sys.modules, {"t4core": previous}), \
                mock.patch.object(sys, "path", list(sys.path)), \
                mock.patch("openrecomp.adapters.t4.importlib.util.spec_from_file_location", return_value=spec) as load, \
                mock.patch("openrecomp.adapters.t4.importlib.util.module_from_spec", return_value=core):
            with self.assertRaisesRegex(RuntimeError, "synthetic"):
                load_core(str(self.folder / "failed"))
            self.assertIs(sys.modules["t4core"], previous)
            self.assertNotIn(load.call_args.args[0], sys.modules)


if __name__ == "__main__":
    unittest.main()
