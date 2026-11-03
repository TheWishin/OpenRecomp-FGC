"""Bundle regression checks; never show a launcher or run a build or game."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
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
        self.assertRegex(archive.name, r"^openrecomp-fgc-test-\d{8}-\d{6}-\d{6}\.zip$")
        self.launcher_scan.assert_called_once_with(self.root)
        self.scanner.source_entries.assert_called_once_with(self.root / "source")
        self.scanner.scan_entries.assert_called_once()
        with zipfile.ZipFile(archive) as result:
            self.assertEqual(count, len(result.namelist()))
            self.assertEqual(result.read("OpenRecomp-FGC/run.cmd"), (self.root / "run.cmd").read_bytes())
            self.assertEqual(result.read("T4/LICENSE"), b"T4 license")
            guide = result.read("START_HIER.txt").decode("utf-8")
            self.assertLessEqual(len(guide.splitlines()), 18)
            self.assertNotIn("Python", guide)
            self.assertNotIn("Internet", guide)
            self.assertIn("run.cmd", guide)
            for text in (guide, result.read("START_HERE.txt").decode("utf-8")):
                # Both games: T4's build tools, T5DR's own folder and package.
                for phrase in ("Visual Studio 2022 Build Tools", "Git", "CMake", "Ninja", "SLUS-20328",
                               "T5DR-Online-1.2.0", ".pkg", ".rap", "T5DR Online.exe", "BUILD GAME", "7400"):
                    self.assertIn(phrase, text)
            self.assertIn("T5DR-Online-1.2.0", result.read("BUNDLE.txt").decode("utf-8"))
            self.assertFalse(any(name.startswith("T5DR") for name in result.namelist()))
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

    def test_zip_can_go_to_a_named_dist_folder_outside_the_checkout(self):
        with tempfile.TemporaryDirectory() as outside:
            dist = Path(outside) / "dist"
            archive, _ = bundle.create_bundle(self.root, self.root / "source", dist=dist, note=["Launcher: abc1234"])
            self.assertEqual(archive.parent, dist.absolute())
            self.assertFalse((self.root / "dist").exists())
            with zipfile.ZipFile(archive) as result:
                self.assertIn("Launcher: abc1234", result.read("BUNDLE.txt").decode("utf-8"))
            with self.assertRaisesRegex(ValueError, "directly in dist"):
                bundle.create_bundle(self.root, self.root / "source", self.root / "dist/x.zip", dist=dist)

    def test_this_pcs_private_words_refuse_the_bundle_in_any_spelling(self):
        word = "Synthetic-Owner-Word"
        for data in (word.encode("utf-8"), word.upper().encode("utf-8"), word.lower().encode("utf-16-le")):
            with self.subTest(data=data):
                self.scanner.source_entries.return_value = [("LICENSE", b"T4 license"), ("tools/x.ps1", b"# " + data)]
                with self.assertRaisesRegex(ValueError, "computer name or e-mail"):
                    bundle.create_bundle(self.root, self.root / "source", terms=[word])
                self.assertFalse((self.root / "dist").exists())
        with self.assertRaisesRegex(ValueError, "e-mail is in: OpenRecomp-FGC/portable/x.txt"):
            bundle.scan_private_terms([("OpenRecomp-FGC/portable/x.txt", b"..." + word.encode() + b"...")], [word])
        with self.assertRaises(ValueError):
            bundle.scan_private_terms([("T4/" + word + ".txt", b"")], [word])
        self.assertEqual(bundle.scan_private_terms([("T4/a.txt", b"nothing here")], [word]), 1)

    def test_a_zip_refused_after_writing_is_removed(self):
        with mock.patch.object(bundle, "scan_private_terms", side_effect=[0, ValueError("synthetic late refusal")]):
            with self.assertRaisesRegex(ValueError, "late refusal"):
                bundle.create_bundle(self.root, self.root / "source", terms=[])
        self.assertEqual(list((self.root / "dist").glob("*")), [])

    def test_local_words_come_from_this_pc_at_run_time(self):
        environment = {"USERNAME": "SyntheticUser", "USERPROFILE": "X:\\Profiles\\SyntheticUser", "COMPUTERNAME": "SYNTH-PC"}
        with mock.patch.dict(bundle.os.environ, environment), \
                mock.patch.object(bundle.subprocess, "run",
                                  return_value=types.SimpleNamespace(stdout="someone@example.invalid\n")):
            terms = bundle.local_terms(self.root, ["extra-word"])
        for term in ("extra-word", "SyntheticUser", "X:\\Profiles\\SyntheticUser", "X:/Profiles/SyntheticUser",
                     "SYNTH-PC", "someone@example.invalid"):
            self.assertIn(term, terms)
        with mock.patch.dict(bundle.os.environ, {"USERNAME": "abc"}, clear=True), \
                mock.patch.object(bundle.subprocess, "run", side_effect=OSError):
            self.assertEqual(bundle.local_terms(self.root), [])

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
            result = bundle.main(["--root", str(self.root), "--t4-source", str(self.root / "source"), "--check-only"])
        self.assertEqual(result, 1)
        self.assertIn("Test bundle refused", error.getvalue())
        self.assertFalse((self.root / "dist").exists())

    def test_release_name_is_the_t4_asset_the_installer_looks_for(self):
        # docs/GAME_SETUP.md: OpenRecomp-Tekken4-<tag>.zip with a T4 folder, tag like the launcher's RE_VERSION.
        self.assertEqual(bundle.release_archive_name("v0.1.0-beta.2"), "OpenRecomp-Tekken4-v0.1.0-beta.2.zip")
        self.assertEqual(bundle.release_archive_name("v1.2.3"), "OpenRecomp-Tekken4-v1.2.3.zip")
        for bad in ("0.1.0", "v0.1", "v0.1.0-beta-2", "v0.1.0+x", "v0.1.0/../x", "", None):
            with self.subTest(tag=bad), self.assertRaisesRegex(ValueError, "Release tag"):
                bundle.release_archive_name(bad)
        dist = self.root / "dist"
        archive, _ = bundle.create_bundle(self.root, self.root / "source",
                                          dist / bundle.release_archive_name("v0.1.0-beta.2"))
        digest = bundle.write_checksums(archive)
        import hashlib
        self.assertEqual(digest, hashlib.sha256(archive.read_bytes()).hexdigest())
        line = "{} *OpenRecomp-Tekken4-v0.1.0-beta.2.zip\n".format(digest)
        self.assertEqual((dist / "OpenRecomp-Tekken4-v0.1.0-beta.2.zip.sha256").read_text(encoding="ascii"), line)
        self.assertEqual((dist / "SHA256SUMS").read_text(encoding="ascii"), line)
        with zipfile.ZipFile(archive) as result:
            self.assertIn("T4/LICENSE", result.namelist())

    def test_only_a_usa_t4_source_goes_into_the_bundle(self):
        us = (b'EXPECTED_BOOT = "SLUS_203.28"\nEXPECTED_SHA1 = "' + bundle.US_ELF_SHA1.encode() + b'"\n'
              b'MSG = "not PAL SCES-50878"\n')
        ps_us = b"$ExpectedElfSha1 = '" + bundle.US_ELF_SHA1.encode() + b"'\n"
        good = [("LICENSE", b"T4 license"), ("tools/iso_extract.py", us), ("tools/build_game.ps1", ps_us)]
        self.scanner.source_entries.return_value = good
        self.assertTrue(any(name == "T4/tools/iso_extract.py" for name, _ in self.entries()))
        for name, data in (("tools/iso_extract.py", us.replace(b"SLUS_203.28", b"SCES_508.78")),
                           ("tools/iso_extract.py", us.replace(bundle.US_ELF_SHA1.encode(), b"0" * 40)),
                           ("tools/build_game.ps1", ps_us.replace(bundle.US_ELF_SHA1.encode(), b"1" * 40))):
            with self.subTest(name=name):
                self.scanner.source_entries.return_value = [(n, data if n == name else d) for n, d in good]
                with self.assertRaisesRegex(ValueError, "not the USA line"):
                    bundle.create_bundle(self.root, self.root / "source")
                self.assertFalse((self.root / "dist").exists())

    def test_powershell_wrappers_pass_the_release_tag(self):
        for name in ("make_t4_test_bundle.ps1", "make_test_bundle.ps1"):
            self.assertIn("[string]$ReleaseTag", (ROOT / "tools" / name).read_text(encoding="utf-8"))
        self.assertIn("'--release-tag', $ReleaseTag",
                      (ROOT / "tools/make_t4_test_bundle.ps1").read_text(encoding="utf-8"))

    def test_powershell_wrapper_uses_python312_without_build_or_git(self):
        text = (ROOT / "tools/make_t4_test_bundle.ps1").read_text(encoding="utf-8")
        self.assertIn("'-3.12'", text)
        self.assertIn("'-I', '-B'", text)
        self.assertIn("--check-only", text)
        self.assertIn("t4_test_bundle.py", text)
        self.assertNotIn("Compress-Archive", text)


class T4BundleEntryPointTests(unittest.TestCase):
    """Invoke the actual script with harmless, repository-local source catalogs."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in bundle.package.SOURCE_FILES | {"run.cmd", "requirements.txt"}:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"{}\n" if path.suffix == ".json" else b"# fixture source\n")
        self.t4 = self.root / "T4Source"
        (self.t4 / "tools").mkdir(parents=True)
        (self.t4 / "LICENSE").write_bytes(b"fixture T4 license\n")
        (self.t4 / "tools/make_test_zip.ps1").write_bytes(b"# source fixture\n")
        (self.t4 / "tools/publish_source.py").write_bytes(b"# source fixture\n")
        (self.t4 / "tools/test_zip.py").write_text(
            "from pathlib import Path\n"
            "def scan_entries(entries):\n"
            "    entries = list(entries)\n"
            "    if entries != [('LICENSE', b'fixture T4 license\\n')]:\n"
            "        raise ValueError('fixture T4 scan refused')\n"
            "    return entries\n"
            "def source_entries(root):\n"
            "    return scan_entries([('LICENSE', (Path(root) / 'LICENSE').read_bytes())])\n",
            encoding="utf-8")

    def invoke(self, *arguments):
        return subprocess.run(
            [sys.executable, "-I", "-B", str(ROOT / "tools/t4_test_bundle.py"),
             "--root", str(self.root), "--t4-source", str(self.t4), *arguments],
            cwd=ROOT, capture_output=True, text=True, timeout=180)

    def test_cli_checks_both_source_catalogs_without_creating_archive(self):
        result = self.invoke("--check-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Both source scans passed", result.stdout)
        self.assertFalse((self.root / "dist").exists())

    def test_cli_refuses_to_create_zip_without_portable_runtime(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("requires --runtime", result.stderr)
        self.assertFalse((self.root / "dist").exists())

    def test_cli_includes_pinned_portable_runtime_when_prepared(self):
        runtime = ROOT / "dist/portable-runtime"
        if not (runtime / "python.exe").is_file():
            self.skipTest("Run fetch_portable_runtime.ps1 to prepare the pinned runtime")
        result = self.invoke("--runtime", str(runtime), "--runtime-cache", str(ROOT / "dist/portable-cache"))
        self.assertEqual(result.returncode, 0, result.stderr)
        archives = list((self.root / "dist").glob("*.zip"))
        self.assertEqual(len(archives), 1)
        with zipfile.ZipFile(archives[0]) as archive:
            prefix = "OpenRecomp-FGC/portable/"
            self.assertEqual(archive.read(prefix + "python.exe"), (runtime / "python.exe").read_bytes())
            self.assertIn(prefix + "Lib/site-packages/PySide6/QtCore.pyd", archive.namelist())
            self.assertIn(prefix + "LICENSE.txt", archive.namelist())
            source = "licenses/sources/pyside-setup-everywhere-src-6.8.2.1.zip"
            self.assertEqual(archive.read(prefix + source), (runtime / source).read_bytes())
            guide = archive.read("START_HIER.txt").decode("utf-8")
            self.assertNotIn("Python", guide)
            self.assertNotIn("Internet", guide)
            self.assertIn("run.cmd", guide)
        self.assertIn("bytes ZIP;", result.stdout)
        self.assertIn("bytes unpacked;", result.stdout)
        named = self.invoke("--runtime", str(runtime), "--runtime-cache", str(ROOT / "dist/portable-cache"),
                            "--release-tag", "v0.1.0-beta.2")
        self.assertEqual(named.returncode, 0, named.stderr)
        self.assertTrue((self.root / "dist/OpenRecomp-Tekken4-v0.1.0-beta.2.zip").is_file())
        self.assertTrue((self.root / "dist/OpenRecomp-Tekken4-v0.1.0-beta.2.zip.sha256").is_file())
        self.assertIn("Checksums: OpenRecomp-Tekken4-v0.1.0-beta.2.zip.sha256 and SHA256SUMS", named.stdout)
        again = self.invoke("--runtime", str(runtime), "--release-tag", "v0.1.0-beta.2")
        self.assertEqual(again.returncode, 1)
        self.assertIn("already exists", again.stderr)

    def test_cli_runtime_flag_refuses_unknown_binary_before_writing_archive(self):
        runtime = self.root / "runtime"
        runtime.mkdir()
        (runtime / "unexpected.exe").write_bytes(b"MZfixture")
        result = self.invoke("--runtime", str(runtime))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Test bundle refused", result.stderr)
        self.assertFalse((self.root / "dist").exists())

if __name__ == "__main__":
    unittest.main()
