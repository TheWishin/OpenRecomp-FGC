"""Offline regression checks using synthetic release inputs, never a real build."""
import importlib.util
import json
from pathlib import Path
import stat
import struct
import tempfile
import unittest
from unittest import mock
import zipfile


SPEC = importlib.util.spec_from_file_location("audit_package", Path(__file__).parents[1] / "tools/package_release.py")
package = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package)


class PackagingAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parents[1])
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def write(self, name, data=b"synthetic reviewed input"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def runtime(self):
        # A header-shaped fixture; no executable code is included or run.
        pe = bytearray(158)
        pe[:2] = b"MZ"
        struct.pack_into("<I", pe, 60, 64)
        pe[64:68] = b"PE\0\0"
        struct.pack_into("<H", pe, 68, 0x8664)
        struct.pack_into("<H", pe, 88, 0x20b)
        struct.pack_into("<H", pe, 156, 2)
        for name in package.REQUIRED_RUNTIME - {"python312.zip"}:
            self.write("runtime/" + name, pe)
        with zipfile.ZipFile(self.root / "runtime/python312.zip", "w") as archive:
            archive.writestr("synthetic.pyc", b"synthetic stdlib input")
        contract = {"python": "3.12", "pyside6": "6.8.2.1"}
        self.inventory(contract, "runtime")
        return contract, bytes(pe)

    def inventory(self, contract, name):
        contract[name] = {n: package.digest(p) for n, p in package.checked_files(self.root / name).items()}

    def release_inputs(self):
        contract, pe = self.runtime()
        for name in package.SOURCE_FILES:
            self.write("source/" + name, b"{}" if name.endswith(".json") else b"synthetic launcher input")
        for name in ("LICENSE", "docs/PACKAGING.md", "docs/INSTALLING.md", "docs/UPDATES.md"):
            self.write("source/" + name)
        for name in package.REQUIRED_LICENSES:
            self.write("licenses/" + name, b"synthetic license text " * 4)
        contract["sources"] = {}
        for name, version in package.REQUIRED_SOURCES.items():
            rel = "sources/" + name + ".tar.xz"
            self.write("licenses/" + rel)
            contract["sources"][name] = {"version": version, "path": rel}
        self.inventory(contract, "licenses")
        starter = self.write("starter", pe)
        contract["starter_sha256"] = package.digest(starter)
        self.write("inventory.json", json.dumps(contract).encode())

    def changed_copy_is_refused(self, relative, data):
        self.release_inputs()
        changed = self.root / relative
        copy = package.shutil.copyfile

        def replace_before_copy(source, target):
            if source == changed:
                changed.write_bytes(data)
            return copy(source, target)

        # Only trust configuration is bypassed. The inventories, scans, copies
        # and refusal use the actual implementation and local fixture files.
        with mock.patch.object(package, "release_trust"), mock.patch.object(package.shutil, "copyfile", side_effect=replace_before_copy):
            with self.assertRaises(package.PackageError):
                package.assemble(self.root / "source", self.root / "runtime", self.root / "starter",
                                 self.root / "licenses", self.root / "inventory.json", self.root / "output",
                                 "v1.2.3", "synthetic-channel")
        self.assertFalse((self.root / "output/OpenRecomp-v1.2.3.zip").exists())

    def test_runtime_cannot_change_between_review_and_copy(self):
        self.changed_copy_is_refused("runtime/pythonw.exe", b"changed after checksum validation")

    def test_source_is_scanned_after_copy(self):
        self.changed_copy_is_refused("source/openrecomp/app.py", b"-----BEGIN PRIVATE KEY-----")

    def test_embedded_stdlib_rejects_special_and_reparse_members(self):
        contract, _ = self.runtime()
        for mode, dos in ((stat.S_IFIFO, 0), (stat.S_IFREG, 0x400)):
            with self.subTest(mode=mode, dos=dos):
                entry = zipfile.ZipInfo("synthetic.pyc")
                entry.external_attr = (mode << 16) | dos
                with zipfile.ZipFile(self.root / "runtime/python312.zip", "w") as archive:
                    archive.writestr(entry, b"synthetic stdlib input")
                self.inventory(contract, "runtime")
                with self.assertRaises(package.PackageError):
                    package.runtime_files(self.root / "runtime", contract)

    def test_non_object_game_manifest_is_a_package_error(self):
        path = self.write("manifest", b"[]")
        with self.assertRaises(package.PackageError):
            package.scan_file(path, "games/t4.json")

    def test_linked_documentation_is_refused(self):
        for name in package.SOURCE_FILES:
            self.write("source/" + name, b"{}" if name.endswith(".json") else b"synthetic source")
        self.write("source/LICENSE")
        for name in ("PACKAGING.md", "INSTALLING.md", "UPDATES.md"):
            self.write("documents/" + name)
        try:
            (self.root / "source/docs").symlink_to(self.root / "documents", target_is_directory=True)
        except OSError:
            self.skipTest("Creating directory symlinks is unavailable")
        with self.assertRaises(package.PackageError):
            package.source_files(self.root / "source")


if __name__ == "__main__":
    unittest.main()
