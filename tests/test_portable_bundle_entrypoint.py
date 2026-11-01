"""Exercise the PowerShell bundle entry point without opening the launcher."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


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


if __name__ == "__main__":
    unittest.main()
