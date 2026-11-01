"""Patch mail cleanup affects bundle snapshots, never the source or diff bytes."""
import importlib.util
import io
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("patch_header_bundle", ROOT / "tools/t4_test_bundle.py")
bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundle)

ADDRESS = b"synthetic" + b"@" + b"example.invalid"
REPLACEMENT = b"From: T4 test <" + b"noreply" + b"@" + b"t5dr-online.invalid>"


class T4PatchHeaderTests(unittest.TestCase):
    def patch(self, ending):
        header = ending.join((b"From 123 Mon Sep 17 00:00:00 2001",
                              b"From: Synthetic <" + ADDRESS + b">",
                              b"Date: Thu, 1 Jan 1970 00:00:00 +0000",
                              b"Subject: [PATCH] synthetic text change",
                              b"", b"Co-Authored-By: Synthetic <" + ADDRESS + b">",
                              b"Co-Authored-By: Other <" + ADDRESS + b">", b"", b""))
        diff = ending.join((b"diff --git a/example.txt b/example.txt",
                            b"--- a/example.txt", b"+++ b/example.txt",
                            b"@@ -1 +1 @@", b"-before", b"+after", b""))
        return header, diff

    def test_replaces_sender_drops_all_coauthors_and_preserves_diff_endings(self):
        for ending in (b"\n", b"\r\n"):
            with self.subTest(ending=ending):
                header, diff = self.patch(ending)
                cleaned = bundle.clean_patch_header(header + diff)
                clean_header, marker, clean_diff = cleaned.partition(b"diff --git")
                self.assertEqual(marker + clean_diff, diff)
                self.assertEqual(clean_header,
                                 header.replace(b"From: Synthetic <" + ADDRESS + b">", REPLACEMENT)
                                 .replace(b"Co-Authored-By: Synthetic <" + ADDRESS + b">" + ending, b"")
                                 .replace(b"Co-Authored-By: Other <" + ADDRESS + b">" + ending, b""))
                self.assertNotIn(ADDRESS, cleaned)

    def test_mixed_endings_and_mail_fields_inside_diff_are_byte_identical(self):
        header = (b"From: Synthetic <" + ADDRESS + b">\r\nSubject: mixed\n"
                  b"Co-Authored-By: Synthetic <" + ADDRESS + b">\r\n\n")
        diff = (b"diff --git a/example.txt b/example.txt\r\n"
                b"--- a/example.txt\n+++ b/example.txt\r\n@@ -1 +1,2 @@\n"
                b"-before\r\n+From: unchanged\n+Co-Authored-By: unchanged\r\n")
        self.assertEqual(bundle.clean_patch_header(header + diff),
                         REPLACEMENT + b"\r\nSubject: mixed\n\n" + diff)

    def test_missing_diff_marker_does_not_clean_an_unrecognized_patch(self):
        original = b"From: Synthetic <" + ADDRESS + b">\nCo-Authored-By: Synthetic\n"
        self.assertEqual(bundle.clean_patch_header(original), original)
        with self.assertRaises(ValueError):
            bundle.package.scan_stream(io.BytesIO(original), "patches/unrecognized.patch")

    def test_bundle_cleans_snapshot_without_touching_source_bytes_or_metadata(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = Path(temporary)
            launcher = root / "launcher"
            source = root / "source"
            launcher.mkdir()
            (source / "patches").mkdir(parents=True)
            for name, data in (("LICENSE", b"launcher license"), ("run.cmd", b"@echo off\r\n"),
                               ("requirements.txt", b"PySide6-Essentials==6.8.2.1\n")):
                (launcher / name).write_bytes(data)
            patch = source / "patches/example.patch"
            header, diff = self.patch(b"\r\n")
            original = header + diff
            patch.write_bytes(original)
            before = patch.stat()
            scanned = []

            def scan(entries):
                checked = list(entries)
                self.assertTrue(all(ADDRESS not in data for _, data in checked))
                scanned.append(checked)
                return checked

            scanner = types.SimpleNamespace(scan_entries=scan)
            scanner.source_entries = lambda _: scanner.scan_entries(
                [("LICENSE", b"T4 license"), ("patches/example.patch", patch.read_bytes())])
            with (mock.patch.object(bundle.package, "source_files", return_value={"LICENSE": launcher / "LICENSE"}),
                  mock.patch.object(bundle, "load_t4_scanner", return_value=scanner),
                  mock.patch.object(bundle, "scan_bundle_entries", side_effect=lambda entries: entries)):
                entries = dict(bundle.bundle_entries(launcher, source))
            expected = bundle.clean_patch_header(original)
            self.assertEqual(len(scanned), 2)
            for checked in scanned:
                self.assertEqual(dict(checked)["patches/example.patch"], expected)
            self.assertIs(scanner.scan_entries, scan)
            self.assertEqual(entries["T4/patches/example.patch"], expected)
            self.assertEqual(patch.read_bytes(), original)
            self.assertEqual((patch.stat().st_size, patch.stat().st_mtime_ns),
                             (before.st_size, before.st_mtime_ns))

    def test_original_scanner_is_restored_after_internal_scan_failure(self):
        header, diff = self.patch(b"\n")
        scan = mock.Mock(side_effect=ValueError("synthetic rejection"))
        scanner = types.SimpleNamespace(scan_entries=scan)
        scanner.source_entries = lambda _: scanner.scan_entries(
            [("patches/example.patch", header + diff)])
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = Path(temporary)
            with (mock.patch.object(bundle.package, "source_files", return_value={}),
                  mock.patch.object(bundle, "load_t4_scanner", return_value=scanner),
                  self.assertRaisesRegex(ValueError, "synthetic rejection")):
                bundle.bundle_entries(root, root / "source")
        self.assertIs(scanner.scan_entries, scan)
        scan.assert_called_once_with([("patches/example.patch", bundle.clean_patch_header(header + diff))])


if __name__ == "__main__":
    unittest.main()
