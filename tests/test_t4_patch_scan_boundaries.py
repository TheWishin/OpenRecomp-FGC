"""Patch-copy cleanup must leave the source bundle privacy scan intact."""
import importlib.util
import io
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("patch_boundary_bundle", ROOT / "tools/t4_test_bundle.py")
bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundle)


class T4PatchScanBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name, data in (("LICENSE", b"launcher license"), ("run.cmd", b"@echo off\n"),
                           ("requirements.txt", b"PySide6-Essentials==6.8.2.1\n")):
            (self.root / name).write_bytes(data)
        self.source = [("LICENSE", b"T4 license")]
        self.scanner = types.SimpleNamespace(
            source_entries=lambda root: self.source,
            scan_entries=self.scan_entries)
        self.enterContext(mock.patch.object(bundle.package, "source_files",
                                            return_value={"LICENSE": self.root / "LICENSE"}))
        self.enterContext(mock.patch.object(bundle, "load_t4_scanner", return_value=self.scanner))
        self.address = b"synthetic" + b"@" + b"example.invalid"
        self.diff = b"diff --git a/sample.txt b/sample.txt\n--- a/sample.txt\n+++ b/sample.txt\n"

    def scan_entries(self, entries):
        checked = list(entries)
        for name, data in checked:
            bundle.package.scan_stream(io.BytesIO(data), name)
        return checked

    def entries(self):
        return dict(bundle.bundle_entries(self.root, self.root / "source"))

    def test_required_replacement_address_is_still_refused_by_unchanged_scan(self):
        original = (b"From: Synthetic <" + self.address + b">\r\n"
                    b"Co-Authored-By: Synthetic <" + self.address + b">\r\n" + self.diff)
        cleaned = bundle.clean_patch_header(original)
        expected = b"From: T4 test <noreply" + b"@" + b"t5dr-online.invalid>\r\n" + self.diff
        self.assertEqual(cleaned, expected)
        self.assertNotIn(self.address, cleaned)
        base = list(self.entries().items())
        with self.assertRaisesRegex(ValueError, "email"):
            bundle.scan_bundle_entries(base + [("T4/patches/sample.patch", cleaned)])
        self.source.append(("patches/sample.patch", original))
        with self.assertRaisesRegex(ValueError, "email"):
            bundle.create_bundle(self.root, self.root / "source")
        self.assertFalse((self.root / "dist").exists())

    def test_address_in_patch_diff_is_still_refused(self):
        for prefix in (b"+From: ", b"+Co-Authored-By: ", b"+contact "):
            with self.subTest(prefix=prefix):
                self.source[:] = [("LICENSE", b"T4 license"),
                                  ("patches/sample.patch", self.diff + prefix + self.address + b"\n")]
                with self.assertRaisesRegex(ValueError, "email"):
                    self.entries()
                self.assertFalse((self.root / "dist").exists())

    def test_address_in_any_other_file_is_still_refused(self):
        for name in ("README.md", "tools/helper.py", "patches/notes.txt",
                     "other/sample.patch", "patches/nested/sample.patch"):
            with self.subTest(name=name):
                data = b"From: Synthetic <" + self.address + b">\n" + self.diff
                self.source[:] = [("LICENSE", b"T4 license"), (name, data)]
                with self.assertRaisesRegex(ValueError, "email"):
                    self.entries()

    def test_launcher_address_is_still_refused(self):
        (self.root / "run.cmd").write_bytes(b"rem contact " + self.address + b"\n")
        with self.assertRaisesRegex(ValueError, "email"):
            self.entries()

    def test_cleanup_is_limited_to_direct_patch_mail_headers(self):
        # No address here: changes in eligibility can be inspected independently
        # of the scanner's refusal of every complete address token.
        header = b"Co-Authored-By: Synthetic contributor\r\n"
        data = header + self.diff + b"+Co-Authored-By: Diff content stays\r\n"
        names = ("patches/sample.patch", "patches/sample.txt", "other/sample.patch",
                 "patches/nested/sample.patch")
        self.source.extend((name, data) for name in names)
        result = self.entries()
        self.assertEqual(result["T4/patches/sample.patch"], data[len(header):])
        for name in names[1:]:
            self.assertEqual(result["T4/" + name], data)


if __name__ == "__main__":
    unittest.main()
