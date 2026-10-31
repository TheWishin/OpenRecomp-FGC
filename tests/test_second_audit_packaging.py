"""Output safety with inert local fixtures; no runtime, build or launcher runs."""
import contextlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location("second_audit_package", Path(__file__).parents[1] / "tools/package_release.py")
package = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package)


class SecondPackagingAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parents[1])
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.output = self.root / "output"
        self.starter = self.root / "starter"
        self.starter.write_bytes(b"inert reviewed placeholder")
        self.inventory = self.root / "inventory.json"
        self.inventory.write_text(json.dumps(dict(runtime={"pythonw.exe": "0" * 64}, licenses={},
                                                 starter_sha256="0" * 64)), encoding="utf-8")

    def assemble(self, digest=None):
        # Input classification is covered elsewhere. Only inert bytes are copied
        # here, keeping the real output creation and overwrite checks under test.
        with contextlib.ExitStack() as stack:
            for name, value in (("source_files", {}), ("runtime_files", {"pythonw.exe": self.starter}),
                                ("license_files", {}), ("release_trust", None), ("windows_pe", True),
                                ("scan_file", None)):
                stack.enter_context(mock.patch.object(package, name, return_value=value))
            stack.enter_context(mock.patch.object(package, "digest", side_effect=digest or (lambda path: "0" * 64)))
            return package.assemble(self.root, self.root, self.starter, self.root, self.inventory,
                                    self.output, "v1.2.3", "synthetic-channel")

    def test_linked_output_ancestor_is_refused_before_creating_artifacts(self):
        self.output = self.root / "linked-parent" / "output"
        real_junction = Path.is_junction

        def junction(path):
            return path == self.output.parent or real_junction(path)

        with mock.patch.object(Path, "is_junction", autospec=True, side_effect=junction):
            with self.assertRaises(package.PackageError):
                self.assemble()
        self.assertFalse(self.output.exists())

    def test_dangling_checksum_link_is_refused_before_creating_artifacts(self):
        checksum = self.output / "SHA256SUMS"
        real_link = Path.is_symlink

        def link(path):
            return path == checksum or real_link(path)

        with mock.patch.object(Path, "is_symlink", autospec=True, side_effect=link):
            with self.assertRaises(package.PackageError):
                self.assemble()
        self.assertFalse(self.output.exists())

    def test_checksum_created_during_assembly_is_never_overwritten(self):
        checksum = self.output / "SHA256SUMS"

        def digest(path):
            if Path(path).suffix == ".zip":
                checksum.write_text("keep existing artifact", encoding="ascii")
            return "0" * 64

        with self.assertRaises(FileExistsError):
            self.assemble(digest)
        self.assertEqual(checksum.read_text(encoding="ascii"), "keep existing artifact")

    def test_owner_hand_check_is_part_of_the_exact_source_payload(self):
        for name in package.SOURCE_FILES:
            path = self.root / "source" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"{}" if name.endswith(".json") else b"inert launcher source")
        selected = package.source_files(self.root / "source")
        self.assertIn("docs/HAND_CHECK.md", selected)


if __name__ == "__main__":
    unittest.main()
