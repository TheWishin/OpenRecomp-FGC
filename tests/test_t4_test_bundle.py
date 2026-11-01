"""Source bundle regression checks; never run a launcher, build or game."""
import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock
import zipfile


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("test_bundle_tool", ROOT / "tools/t4_test_bundle.py")
bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundle)


class T4TestBundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name, data in (("LICENSE", b"launcher license"), ("run.cmd", b"@echo off\r\n"),
                           ("requirements.txt", b"PySide6-Essentials==6.8.2.1\n"),
                           ("openrecomp/app.py", b"pass\n"),
                           ("openrecomp/ui/assets/icon.svg", b"<svg></svg>")):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.selected = {name: self.root / name for name in
                         ("LICENSE", "openrecomp/app.py", "openrecomp/ui/assets/icon.svg")}
        self.scanner = types.SimpleNamespace(
            source_entries=mock.Mock(return_value=[("LICENSE", b"T4 license"),
                                                   ("tools/net_play.ps1", b"# source\n")]),
            scan_entries=mock.Mock(side_effect=lambda entries: entries))
        self.launcher_scan = self.enterContext(mock.patch.object(bundle.package, "source_files", return_value=self.selected))
        self.t4_load = self.enterContext(mock.patch.object(bundle, "load_t4_scanner", return_value=self.scanner))

    def entries(self):
        return bundle.bundle_entries(self.root, self.root / "source")

    def test_side_by_side_source_bundle_runs_both_scans_and_retains_startup(self):
        archive, count = bundle.create_bundle(self.root, self.root / "source")
        self.assertEqual(archive.parent, self.root / "dist")
        self.assertRegex(archive.name, r"^openrecomp-t4-test-\d{8}-\d{6}-\d{6}\.zip$")
        self.launcher_scan.assert_called_once_with(self.root)
        self.scanner.source_entries.assert_called_once_with(self.root / "source")
        self.scanner.scan_entries.assert_called_once()
        with zipfile.ZipFile(archive) as result:
            self.assertEqual(count, len(result.namelist()))
            self.assertEqual(result.read("OpenRecomp-FGC/run.cmd"), (self.root / "run.cmd").read_bytes())
            self.assertEqual(result.read("T4/LICENSE"), b"T4 license")
            guide = result.read("START_HIER.txt").decode("utf-8")
            self.assertLessEqual(len(guide.splitlines()), 5)
            self.assertIn("Python 3.12", guide)
            self.assertIn("run.cmd", guide)
            self.assertFalse(any(Path(name).suffix.lower() in bundle.IMAGE_SUFFIXES for name in result.namelist()))
            self.assertFalse(any(".venv" in name for name in result.namelist()))

    def test_either_scan_failure_refuses_before_output_directory(self):
        for failing in (self.launcher_scan, self.scanner.source_entries, self.scanner.scan_entries):
            with self.subTest(scan=failing):
                failing.side_effect = ValueError("synthetic scanner rejection")
                with self.assertRaisesRegex(ValueError, "scanner rejection"):
                    bundle.create_bundle(self.root, self.root / "source")
                self.assertFalse((self.root / "dist").exists())
                failing.side_effect = None
        self.scanner.scan_entries.side_effect = lambda entries: entries

    def test_exact_archived_bytes_are_rechecked_after_launcher_scan(self):
        # Simulate a changed selected file after the initial source scanner.
        (self.root / "openrecomp/app.py").write_bytes(b"MZ" + b"renamed executable")
        with self.assertRaisesRegex(ValueError, "Binary"):
            self.entries()

    def test_added_start_files_are_scanned_too(self):
        (self.root / "run.cmd").write_bytes(b"MZ" + b"renamed executable")
        with self.assertRaises(ValueError):
            self.entries()

    def test_wrong_input_material_is_rejected_by_name_or_signature(self):
        base = self.entries()
        samples = (("T4/unexpected.exe", b"source"), ("T4/picture.png", b"source"),
                   ("T4/disc.iso", b"source"), ("T4/output.txt", b"\x7fELFdata"),
                   ("T4/image.txt", b"\x89PNG\r\n\x1a\n"),
                   ("T4/vector.txt", b"<?xml?><svg viewBox='0 0 1 1'></svg>"),
                   ("T4/archive.txt", b"PK\x03\x04"),
                   ("T4/path.txt", b"C:" + b"\\Users\\" + b"synthetic\\file"),
                   ("T4/mail.txt", b"synthetic" + b"@" + b"example.invalid"))
        for name, data in samples:
            with self.subTest(name=name), self.assertRaises(ValueError):
                bundle.scan_bundle_entries(base + [(name, data)])

    def test_output_cannot_leave_dist_or_overwrite_existing_archive(self):
        for destination in (self.root / "bad.zip", self.root / "dist/nested/bad.zip",
                            self.root / "tools/bad.zip"):
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                bundle.create_bundle(self.root, self.root / "source", destination)
        path, _ = bundle.create_bundle(self.root, self.root / "source")
        original = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "already exists"):
            bundle.create_bundle(self.root, self.root / "source", path)
        self.assertEqual(path.read_bytes(), original)

    def test_duplicate_case_alias_and_path_traversal_are_rejected(self):
        base = self.entries()
        for addition in (("T4/LICENSE", b"license"), ("t4/other.txt", b"source"),
                         ("T4/../escape.txt", b"source")):
            with self.subTest(name=addition[0]), self.assertRaises(ValueError):
                bundle.scan_bundle_entries(base + [addition])

    def test_check_only_runs_scans_and_writes_nothing(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = bundle.main(["--root", str(self.root), "--t4-source", str(self.root / "source"), "--check-only"])
        self.assertEqual(result, 0)
        self.assertIn("Both source scans passed", output.getvalue())
        self.assertFalse((self.root / "dist").exists())

    def test_scan_failure_has_nonzero_exit_without_zip(self):
        self.scanner.source_entries.side_effect = ValueError("synthetic rejection")
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            result = bundle.main(["--root", str(self.root), "--t4-source", str(self.root / "source")])
        self.assertEqual(result, 1)
        self.assertIn("Test bundle refused", error.getvalue())
        self.assertFalse((self.root / "dist").exists())

    def test_powershell_wrapper_uses_python312_without_build_or_git(self):
        text = (ROOT / "tools/make_t4_test_bundle.ps1").read_text(encoding="utf-8")
        self.assertIn("'-3.12'", text)
        self.assertIn("'-I', '-B'", text)
        self.assertIn("--check-only", text)
        self.assertIn("t4_test_bundle.py", text)
        self.assertNotIn("Compress-Archive", text)


if __name__ == "__main__":
    unittest.main()
