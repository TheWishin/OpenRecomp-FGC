"""Discover the real PowerShell runtime-boundary checks with the Python suite."""
import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "nt", "Windows PowerShell entry point")
class PortableScanBoundaryTests(unittest.TestCase):
    def test_runtime_scan_boundaries_through_fetch_entry_point(self):
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
             str(ROOT / "tests" / "test_portable_scan_boundaries.ps1")],
            cwd=ROOT, capture_output=True, text=True, encoding="oem", errors="replace", timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Portable scan entry-point checks passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
