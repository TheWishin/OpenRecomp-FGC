"""Guest-path pins follow original patch bytes, never arbitrary cleaned bytes."""
import hashlib
import importlib.util
from pathlib import Path
import re
import tempfile
import types
import unittest
from unittest import mock
import zipfile


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("guest_path_bundle", ROOT / "tools/t4_test_bundle.py")
bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundle)


class T4GuestPathTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name, data in (("LICENSE", b"launcher license"), ("run.cmd", b"@echo off\n"),
                           ("requirements.txt", b"PySide6-Essentials==6.8.2.1\n")):
            (self.root / name).write_bytes(data)
        self.name = "patches/synthetic.patch"
        self.diff = (b"diff --git a/sample.txt b/sample.txt\n"
                     b"--- a/sample.txt\n+++ b/sample.txt\n@@ -1 +1 @@\n"
                     b"-before\n+guest path: " + bytes((92, 92)) + b"guest-disc/file\n")
        self.original = b"Co-Authored-By: Synthetic contributor\n\n" + self.diff
        self.source = [("LICENSE", b"T4 license"), (self.name, self.original)]
        self.publisher = types.SimpleNamespace(
            GUEST_PATH_SHA256={hashlib.sha256(self.original).hexdigest()},
            PERSONAL=re.compile(r"(?i)(?:\b[a-z]:[\\/]|\\\\[a-z0-9_.-]+[\\/])"))
        self.scanned = []

        def scan_file(name, data):
            self.scanned.append((name, data))
            reasons = []
            if (self.publisher.PERSONAL.search(data.decode("utf-8"))
                    and hashlib.sha256(data).hexdigest() not in self.publisher.GUEST_PATH_SHA256):
                reasons.append("personal or machine-specific path")
            for token, reason in ((b"SYNTHETIC-CREDENTIAL", "credential or private key content"),
                                  (b"SYNTHETIC-ADDRESS", "literal network address"),
                                  (b"SYNTHETIC-GENERATED", "generated game code marker")):
                if token in data:
                    reasons.append(reason)
            return reasons

        self.original_scan_file = scan_file
        self.publisher.scan_file = scan_file

        def scan_entries(entries):
            checked = list(entries)
            findings = [name + ": " + reason for name, data in checked
                        for reason in self.publisher.scan_file(name, data)]
            if findings:
                raise ValueError("Test zip refused:\n" + "\n".join(findings))
            return checked

        self.original_scan_entries = scan_entries
        self.scanner = types.SimpleNamespace(publish_source=self.publisher, scan_entries=scan_entries)
        self.scanner.source_entries = lambda _: self.scanner.scan_entries(self.source)
        self.enterContext(mock.patch.object(bundle.package, "source_files",
                                            return_value={"LICENSE": self.root / "LICENSE"}))
        self.enterContext(mock.patch.object(bundle, "load_t4_scanner", return_value=self.scanner))

    def entries(self):
        return dict(bundle.bundle_entries(self.root, self.root / "source"))

    def pin(self, data):
        self.publisher.GUEST_PATH_SHA256 = {hashlib.sha256(data).hexdigest()}
        self.source[-1] = (self.name, data)

    def assert_restored(self):
        self.assertIs(self.publisher.scan_file, self.original_scan_file)
        self.assertIs(self.scanner.scan_entries, self.original_scan_entries)

    def test_listed_original_passes_cleanup_and_archive_readback(self):
        pins = self.publisher.GUEST_PATH_SHA256.copy()
        cleaned = bundle.clean_patch_header(self.original)
        self.assertNotEqual(cleaned, self.original)
        self.assertNotIn(hashlib.sha256(cleaned).hexdigest(), pins)
        archive, _ = bundle.create_bundle(self.root, self.root / "source")
        with zipfile.ZipFile(archive) as output:
            self.assertEqual(output.read("T4/" + self.name), self.diff)
        self.assertEqual(self.source[-1], (self.name, self.original))
        self.assertEqual(self.publisher.GUEST_PATH_SHA256, pins)
        self.assertTrue(any(name == self.name and data == cleaned for name, data in self.scanned))
        self.assert_restored()

    def test_personal_path_with_unlisted_original_hash_is_refused(self):
        self.publisher.GUEST_PATH_SHA256.clear()
        path = b"C:" + bytes((92,)) + b"Users" + bytes((92,)) + b"synthetic" + bytes((92,)) + b"file"
        self.source[-1] = (self.name, self.original + b"+personal: " + path + b"\n")
        with self.assertRaisesRegex(ValueError, "personal or machine-specific path"):
            bundle.create_bundle(self.root, self.root / "source")
        self.assertFalse((self.root / "dist").exists())
        self.assert_restored()

    def test_removed_only_header_preserves_lf_crlf_and_mixed_diff_bytes(self):
        headers = (b"Co-Authored-By: Synthetic contributor\n\n",
                   b"Co-Authored-By: Synthetic contributor\r\n\r\n",
                   b"Co-Authored-By: Synthetic contributor\r\n"
                   b"co-authored-by: Another contributor\n\r\n")
        diffs = (self.diff, self.diff.replace(b"\n", b"\r\n"),
                 self.diff.replace(b"\n", b"\r\n", 2))
        for header in headers:
            for diff in diffs:
                with self.subTest(header=header, diff=diff[:32]):
                    original = header + diff
                    self.pin(original)
                    pins = self.publisher.GUEST_PATH_SHA256.copy()
                    self.assertEqual(self.entries()["T4/" + self.name], diff)
                    self.assertEqual(self.source[-1], (self.name, original))
                    self.assertEqual(self.publisher.GUEST_PATH_SHA256, pins)
                    self.assert_restored()

    def test_cleanup_preserves_blank_preamble_without_removed_metadata(self):
        for header in (b"\n", b"\r\n\r\n"):
            with self.subTest(header=header):
                original = header + self.diff
                self.assertEqual(bundle.clean_patch_header(original), original)

    def test_listed_original_cannot_authorize_changed_diff(self):
        clean = bundle.clean_patch_header(self.original)
        with mock.patch.object(bundle, "clean_patch_header", return_value=clean + b"+changed diff\n"):
            with self.assertRaisesRegex(ValueError, "changed diff content"):
                self.entries()
        self.assert_restored()

    def test_listed_cleaned_hash_does_not_authorize_unlisted_original(self):
        cleaned = bundle.clean_patch_header(self.original)
        self.publisher.GUEST_PATH_SHA256 = {hashlib.sha256(cleaned).hexdigest()}
        self.assertNotIn(hashlib.sha256(self.original).hexdigest(), self.publisher.GUEST_PATH_SHA256)
        with self.assertRaisesRegex(ValueError, "personal or machine-specific path"):
            self.entries()
        self.assert_restored()

    def test_changed_source_diff_loses_original_hash_pin(self):
        self.source[-1] = (self.name, self.original + b"+changed source diff\n")
        with self.assertRaisesRegex(ValueError, "personal or machine-specific path"):
            self.entries()
        self.assert_restored()

    def test_unchanged_listed_patch_cannot_hide_personal_header_path(self):
        path = b"C:" + bytes((92,)) + b"Users" + bytes((92,)) + b"synthetic" + bytes((92,)) + b"file"
        original = b"Subject: synthetic " + path + b"\n\n" + self.diff
        self.assertEqual(bundle.clean_patch_header(original), original)
        self.pin(original)
        with self.assertRaisesRegex(ValueError, "personal or machine-specific path"):
            self.entries()
        self.assert_restored()

    def test_original_pin_without_real_diff_marker_cannot_authorize_path(self):
        original = b"Co-Authored-By: Synthetic contributor\nnot a diff\n" + bytes((92, 92)) + b"guest-disc/file\n"
        self.pin(original)
        self.assertEqual(bundle.clean_patch_header(original), original)
        with self.assertRaisesRegex(ValueError, "personal or machine-specific path"):
            self.entries()
        self.assert_restored()

    def test_nested_patch_does_not_receive_header_cleanup_exemption(self):
        cleaned = bundle.clean_patch_header(self.original)
        self.publisher.GUEST_PATH_SHA256 = {hashlib.sha256(cleaned).hexdigest()}
        self.name = "patches/nested/synthetic.patch"
        self.source[-1] = (self.name, self.original)
        with mock.patch.object(bundle, "clean_patch_header", side_effect=AssertionError("nested cleanup")):
            with self.assertRaisesRegex(ValueError, "personal or machine-specific path"):
                self.entries()
        self.assert_restored()

    def test_original_pin_cannot_authorize_non_direct_patch_names(self):
        for name in ("patches/nested/synthetic.patch", "runtime/synthetic.patch", "patches/notes.txt"):
            with self.subTest(name=name):
                self.name = name
                self.pin(self.original)
                with self.assertRaisesRegex(ValueError, "personal or machine-specific path"):
                    self.entries()
                self.assert_restored()

    def test_original_pin_preserves_crlf_and_mixed_diff_bytes(self):
        for diff in (self.diff.replace(b"\n", b"\r\n"),
                     self.diff.replace(b"\n", b"\r\n", 2)):
            with self.subTest(diff=diff[:32]):
                original = b"From: Synthetic sender\r\nCo-Authored-By: Synthetic contributor\n\n" + diff
                self.pin(original)
                result = self.entries()["T4/" + self.name]
                self.assertEqual(result, b"From: T4 test\r\n\n" + diff)
                self.assert_restored()

    def test_listed_original_with_personal_path_in_cleaned_header_is_refused(self):
        path = b"C:" + bytes((92,)) + b"Users" + bytes((92,)) + b"synthetic" + bytes((92,)) + b"file"
        original = b"Subject: synthetic " + path + b"\n" + self.original
        self.pin(original)
        with self.assertRaisesRegex(ValueError, "personal or machine-specific path"):
            self.entries()
        self.assert_restored()

    def test_guest_path_pin_does_not_remove_other_cleaned_content_findings(self):
        for token, reason in ((b"SYNTHETIC-CREDENTIAL", "credential or private key content"),
                              (b"SYNTHETIC-ADDRESS", "literal network address"),
                              (b"SYNTHETIC-GENERATED", "generated game code marker")):
            with self.subTest(reason=reason):
                self.pin(self.original + b"+" + token + b"\n")
                with self.assertRaisesRegex(ValueError, reason):
                    self.entries()
                self.assert_restored()

    def test_header_cleanup_does_not_exempt_email_in_diff(self):
        address = b"synthetic" + b"@" + b"example.invalid"
        self.pin(self.original + b"+contact " + address + b"\n")
        with self.assertRaisesRegex(ValueError, "email"):
            self.entries()
        self.assert_restored()


if __name__ == "__main__":
    unittest.main()
