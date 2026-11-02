"""Exercise the PowerShell bundle entry point without opening the launcher."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell.exe")


@unittest.skipUnless(os.name == "nt" and POWERSHELL, "Windows PowerShell entry point")
class PortableBundleEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.tools = self.root / "tools"
        self.tools.mkdir()
        shutil.copyfile(ROOT / "tools/make_t4_test_bundle.ps1", self.tools / "make_t4_test_bundle.ps1")
        # Test the real wrapper using this test process's real interpreter. The
        # download/extraction entry point has its own archive regression tests.
        self.runtime = Path(sys.executable).parent
        self.fetch = self.tools / "fetch_portable_runtime.ps1"
        self.fetch.write_text(
            "param([string]$Destination, [string]$CacheDirectory, [switch]$CheckOnly)\n"
            "if ($CheckOnly) { Set-Content -LiteralPath (Join-Path $PSScriptRoot 'verified') -Value 'verified'; return }\n"
            "Set-Content -LiteralPath (Join-Path $PSScriptRoot 'fetch-called') -Value 'called'\n",
            encoding="utf-8")
        (self.tools / "t4_test_bundle.py").write_text(
            "import json, sys\nfrom pathlib import Path\n"
            "assert sys.version_info[:2] == (3, 12)\n"
            "Path(__file__).with_suffix('.arguments').write_text(json.dumps(sys.argv[1:]))\n",
            encoding="utf-8")
        self.arguments = self.tools / "t4_test_bundle.arguments"

    def run_wrapper(self, *extra):
        environment = dict(os.environ)
        # No py/python discovery is available to the normal bundle path.
        environment["PATH"] = str(Path(POWERSHELL).parent)
        return subprocess.run(
            [POWERSHELL, "-NoProfile", "-NonInteractive", "-File",
             str(self.tools / "make_t4_test_bundle.ps1"), "-RuntimeRoot", str(self.runtime),
             "-T4Source", str(self.root / "T4"), *extra],
            cwd=self.root, env=environment, capture_output=True, text=True, timeout=90)

    def test_fetches_then_runs_bundle_cli_with_portable_python_without_system_path(self):
        result = self.run_wrapper()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.tools / "fetch-called").is_file())
        self.assertEqual(json.loads(self.arguments.read_text()),
                         ["--root", str(self.root), "--runtime", str(self.runtime),
                          "--runtime-cache", str(self.root / "dist/portable-cache"),
                          "--t4-source", str(self.root / "T4")])

    def test_check_only_does_not_fetch_and_passes_runtime_to_scanner(self):
        result = self.run_wrapper("-CheckOnly")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.tools / "fetch-called").exists())
        self.assertTrue((self.tools / "verified").is_file())
        self.assertIn("--check-only", json.loads(self.arguments.read_text()))

    def test_failed_fetch_never_runs_bundle_cli(self):
        self.fetch.write_text("throw 'synthetic download rejection'\n", encoding="utf-8")
        result = self.run_wrapper()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("synthetic download rejection", result.stderr)
        self.assertFalse(self.arguments.exists())

    def test_failed_check_only_verification_never_runs_bundle_cli(self):
        self.fetch.write_text("throw 'synthetic runtime rejection'\n", encoding="utf-8")
        result = self.run_wrapper("-CheckOnly")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("synthetic runtime rejection", result.stderr)
        self.assertFalse(self.arguments.exists())

    def test_nonzero_fetch_exit_never_runs_bundle_cli(self):
        self.fetch.write_text("exit 7\n", encoding="utf-8")
        result = self.run_wrapper()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.arguments.exists())

    def test_bundle_cli_failure_is_reported_as_failure(self):
        (self.tools / "t4_test_bundle.py").write_text("raise SystemExit(9)\n", encoding="utf-8")
        result = self.run_wrapper()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Test-Bundle verweigert", result.stderr)


@unittest.skipUnless(os.name == "nt" and POWERSHELL, "Windows PowerShell entry point")
class PortableBundlePipelineTests(unittest.TestCase):
    def test_real_cached_powershell_pipeline_without_system_python(self):
        runtime = ROOT / "dist/portable-runtime"
        cache = ROOT / "dist/portable-cache"
        if not (runtime / "python.exe").is_file() or not cache.is_dir():
            self.skipTest("Prepare the pinned portable runtime/cache before the full pipeline smoke test")
        with tempfile.TemporaryDirectory(prefix=".bundle-pipeline-", dir=ROOT) as temporary:
            source = Path(temporary) / "T4Source"
            tools = source / "tools"
            tools.mkdir(parents=True)
            (source / "LICENSE").write_bytes(b"fixture T4 license\n")
            (tools / "make_test_zip.ps1").write_text("# fixture catalog\n", encoding="utf-8")
            (tools / "publish_source.py").write_text("# fixture scanner\n", encoding="utf-8")
            (tools / "test_zip.py").write_text(
                "from pathlib import Path\n"
                "def scan_entries(entries):\n"
                "    entries = list(entries)\n"
                "    if entries != [('LICENSE', b'fixture T4 license\\n')]:\n"
                "        raise ValueError('fixture T4 scan refused')\n"
                "    return entries\n"
                "def source_entries(root):\n"
                "    return scan_entries([('LICENSE', (Path(root) / 'LICENSE').read_bytes())])\n",
                encoding="utf-8")
            environment = dict(os.environ)
            environment["PATH"] = str(Path(POWERSHELL).parent)
            result = subprocess.run(
                [POWERSHELL, "-NoProfile", "-NonInteractive", "-File",
                 str(ROOT / "tools/make_t4_test_bundle.ps1"), "-T4Source", str(source),
                 "-RuntimeRoot", str(runtime), "-CacheDirectory", str(cache)],
                cwd=ROOT, env=environment, capture_output=True, text=True, timeout=240)
            archive_lines = [line.removeprefix("Test bundle: ") for line in result.stdout.splitlines()
                             if line.startswith("Test bundle: ")]
            for name in archive_lines:
                archive = Path(name)
                self.assertEqual(archive.parent, ROOT / "dist")
                self.assertTrue(archive.name.startswith("openrecomp-t4-test-"))
                self.addCleanup(archive.unlink, missing_ok=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(len(archive_lines), 1, result.stdout)
            self.assertIn("Portable runtime verified:", result.stdout)
            self.assertIn("Portable runtime: Python 3.12, Qt 6.8.2", result.stdout)
            archive = Path(archive_lines[0])
            with zipfile.ZipFile(archive) as output:
                prefix = "OpenRecomp-FGC/portable/"
                self.assertEqual(output.read(prefix + "python.exe"), (runtime / "python.exe").read_bytes())
                self.assertIn(prefix + "Lib/site-packages/PySide6/QtQuick.pyd", output.namelist())
                self.assertIn(prefix + "LICENSE.txt", output.namelist())
                self.assertIn(prefix + "licenses/PySide6/LICENSES/LGPL-3.0-only.txt", output.namelist())
                self.assertEqual(output.read("T4/LICENSE"), b"fixture T4 license\n")
                guide = output.read("START_HIER.txt").decode("utf-8")
                self.assertIn("run.cmd", guide)
                self.assertNotIn("Python", guide)
                size = "Size: {:,} bytes ZIP; {:,} bytes unpacked; {} files.".format(
                    archive.stat().st_size, sum(info.file_size for info in output.infolist()),
                    len(output.infolist()))
                self.assertIn(size, result.stdout)
                print("Portable bundle smoke (synthetic T4): " + size)
                unpacked = Path(temporary) / "unpacked"
                output.extractall(unpacked)
            launcher = unpacked / "OpenRecomp-FGC"
            smoke = launcher / "tests/test_startup_offscreen.py"
            smoke.parent.mkdir()
            shutil.copyfile(ROOT / "tests/test_startup_offscreen.py", smoke)
            started = subprocess.run(
                [str(launcher / "portable/python.exe"), "-I", "-B", str(smoke), "-v"],
                cwd=launcher, env=environment, capture_output=True, text=True, timeout=90)
            self.assertEqual(started.returncode, 0, started.stdout + started.stderr)
            self.assertIn("Ran 1 test", started.stderr)
            self.assertIn("OK", started.stderr)
            print("Extracted portable bundle: real app.main and Qt/QML controller smoke passed offscreen.")


if __name__ == "__main__":
    unittest.main()
