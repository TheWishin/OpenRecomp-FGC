"""Portable test-bundle instructions are shipped through the real source scan."""
from pathlib import Path
import re
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PortableBundleDocsTests(unittest.TestCase):
    def test_documented_file_types_match_real_verified_catalog(self):
        cache = ROOT / "dist/portable-cache"
        if not (cache / "python-3.12.10-embed-amd64.zip").is_file():
            self.skipTest("Pinned dependency cache is needed for the real catalog entry point")
        result = subprocess.run(
            [sys.executable, "-I", "-B", str(ROOT / "tools/portable_runtime.py"),
             "--catalog", "--cache", str(cache)], cwd=ROOT, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        paths = [line.split("  ", 2)[2] for line in result.stdout.splitlines()
                 if re.match(r"^[0-9a-f]{64}  [0-9]+  ", line)]
        self.assertTrue(paths)
        text = (ROOT / "docs/PACKAGING.md").read_text(encoding="utf-8")
        paragraph = text.split("For this lock, the complete suffix set is ", 1)[1].split("\n\n", 1)[0]
        self.assertEqual(set(re.findall(r"`(\.[a-z_]+)`", paragraph)),
                         {Path(path).suffix for path in paths} - {""})
        self.assertIn("extensionless files", paragraph)
        self.assertIn("not an extension allowlist", paragraph)
        for path in re.findall(r"`portable/([^`]+)`", text):
            if not path.endswith("/"):
                self.assertIn(path, paths)

    def test_portable_bundle_instructions_do_not_require_installed_runtime(self):
        text = (ROOT / "docs/T4_FIRST_RUN.md").read_text(encoding="utf-8")
        section = text.split("## Quelltext-Testbundle", 1)[1].split("## Portable release", 1)[0]
        self.assertIn("OpenRecomp-FGC/portable/", section)
        self.assertIn("keine separate Laufzeitinstallation", section)
        self.assertNotIn("Python 3.12 muss bereits installiert sein", section)
        self.assertNotIn("keine portable Python-Installation", section)

    def test_packaging_instructions_retain_exact_catalog_and_license_gate(self):
        text = (ROOT / "docs/PACKAGING.md").read_text(encoding="utf-8")
        section = text.split("## T4 test bundle with a portable runtime", 1)[1].split(
            "## Offline preparation", 1)[0]
        for phrase in ("tools\\make_t4_test_bundle.ps1", "tools\\fetch_portable_runtime.ps1",
                       "tools/portable_runtime.lock.json", "CPython 3.12.10",
                       "PySide6-Essentials", "6.8.2.1", "SHA-256", "exact catalog",
                       "Both existing source catalog scans", "licences/notices",
                       "portable/licenses/PySide6/", "portable/licenses/sources/",
                       "pyside-setup-everywhere-src-6.8.2.1.zip",
                       "The complete Qt corresponding source is not bundled",
                       "unpacked size"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, section)
        result = subprocess.run(
            [sys.executable, "-I", "-B", str(ROOT / "tools/package_release.py"),
             "--scan-only"], cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
