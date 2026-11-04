"""Source-only beta release checks; no launcher or real runtime is started."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("beta_package", ROOT / "tools/package_release.py")
package = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package)


class BetaPackagingTests(unittest.TestCase):
    def test_current_source_tree_scans_and_includes_runtime_imports_and_beta_guides(self):
        selected = package.source_files(ROOT)
        for name in ("openrecomp/adapters/launch_guard.py", "openrecomp/adapters/t5_match.py",
                     "openrecomp/adapters/t4_support.py", "openrecomp/t4_report.py",
                     "README.md", "docs/T4_FIRST_RUN.md", "docs/T4_ONLINE.md"):
            self.assertIn(name, selected)
        self.assertEqual(set(selected), package.SOURCE_FILES)

    def test_scan_only_checks_this_tree_without_release_inputs_or_assembly(self):
        output = io.StringIO()
        with mock.patch.object(package, "assemble") as assemble, contextlib.redirect_stdout(output):
            package.main(["--scan-only"])
        self.assertEqual(json.loads(output.getvalue()), {"scan": "passed", "source_files": len(package.SOURCE_FILES)})
        assemble.assert_not_called()

    def test_scan_only_rejects_assembly_arguments(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            package.main(["--scan-only", "--out", "unused"])

    def test_assembly_still_requires_all_reviewed_inputs(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            package.main([])

    def test_font_glyph_bytes_do_not_relax_personal_information_scan(self):
        for weight in ("400", "500", "600"):
            name = "openrecomp/ui/fonts/IBMPlexSans-" + weight + ".ttf"
            with self.subTest(name=name):
                package.scan_file(ROOT / name, name)
        package.scan_stream(io.BytesIO(b"@a@b.invalid@"), "synthetic glyph table")
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            font = Path(temporary) / "modified-font"
            # A synthetic contact string, never personal information.
            font.write_bytes(b"font metadata " + b"contact" + b"@" + b"example.invalid")
            with self.assertRaises(package.PackageError):
                package.scan_file(font, "openrecomp/ui/fonts/IBMPlexSans-400.ttf")

    def test_font_handling_does_not_relax_private_key_scan(self):
        with self.assertRaises(package.PackageError):
            package.scan_stream(io.BytesIO(b"-----BEGIN PRIVATE KEY-----"), "font")


if __name__ == "__main__":
    unittest.main()
