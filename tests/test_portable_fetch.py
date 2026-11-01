"""Run the real PowerShell downloader entry point without network or a window."""
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PortableFetchTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("powershell.exe"), "Windows PowerShell is required")
    def test_cached_download_and_refusal_entry_points(self):
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-File",
             str(ROOT / "tests" / "portable_fetch_entrypoint.ps1")],
            cwd=ROOT, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Portable fetch entry-point checks passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
