"""Exercise the portable verifier's command-line entry point without a GUI."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]


class PortableRuntimeEntryPointTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "dist").mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "dist")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cache = self.root / "cache"
        self.cache.mkdir()
        self.runtime = self.root / "portable"
        self.runtime.mkdir()
        self.script = self.root / "portable_runtime.py"
        shutil.copyfile(ROOT / "tools" / "portable_runtime.py", self.script)
        self.members = {name: ("fixture " + name).encode() for name in (
            "python.exe", "pythonw.exe", "python312.dll", "python312.zip", "python312._pth",
            "LICENSE.txt", "Lib/site-packages/PySide6/__init__.py",
            "Lib/site-packages/shiboken6/__init__.py")}
        self.archive = self.cache / "fixture.zip"
        with zipfile.ZipFile(self.archive, "w") as output:
            for name, data in self.members.items():
                output.writestr(name, data)
        data = self.archive.read_bytes()
        lock = {"schema": 1, "archives": [{"filename": "fixture.zip",
                "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}]}
        self.lock = self.root / "portable_runtime.lock.json"
        self.lock.write_text(json.dumps(lock), encoding="utf-8")
        for name, data in self.members.items():
            path = self.runtime / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def run_verifier(self, *args):
        return subprocess.run([sys.executable, "-I", "-B", str(self.script),
                               "--cache", str(self.cache), *args],
                              capture_output=True, text=True, timeout=30)

    def test_real_cli_accepts_exact_pinned_archive_members_and_prints_catalog(self):
        result = self.run_verifier("--runtime", str(self.runtime), "--catalog")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("8 files", result.stdout)
        self.assertIn("python.exe", result.stdout)

    def test_real_cli_refuses_extra_executable_inside_runtime(self):
        (self.runtime / "game.exe").write_bytes(b"MZ forbidden fixture")
        result = self.run_verifier("--runtime", str(self.runtime))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unlisted or modified", result.stderr)

    def test_real_cli_refuses_changed_runtime_bytes(self):
        (self.runtime / "python.exe").write_bytes(b"modified")
        result = self.run_verifier("--runtime", str(self.runtime))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unlisted or modified", result.stderr)

    def test_real_cli_refuses_unpinned_archive_before_trusting_members(self):
        with self.archive.open("ab") as output:
            output.write(b"tamper")
        result = self.run_verifier("--runtime", str(self.runtime))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA-256", result.stderr)

    def test_real_cli_refuses_missing_license(self):
        (self.runtime / "LICENSE.txt").unlink()
        result = self.run_verifier("--runtime", str(self.runtime))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing pinned files", result.stderr)

    def add_license_source(self, include_lgpl=True):
        source = self.cache / "source.zip"
        notices = {"project/LICENSES/GPL-3.0-only.txt": b"GNU GENERAL PUBLIC LICENSE\nVersion 3"}
        if include_lgpl:
            notices["project/LICENSES/LGPL-3.0-only.txt"] = b"GNU LESSER GENERAL PUBLIC LICENSE\nVersion 3"
        with zipfile.ZipFile(source, "w") as output:
            for name, data in notices.items():
                output.writestr(name, data)
            output.writestr("project/code.py", b"source fixture")
        data = source.read_bytes()
        lock = json.loads(self.lock.read_text(encoding="utf-8"))
        lock["downloads"] = [{"filename": "source.zip", "sha256": hashlib.sha256(data).hexdigest(),
                              "target": "licenses/sources/source.zip", "licenses_prefix": "licenses/PySide6"}]
        self.lock.write_text(json.dumps(lock), encoding="utf-8")
        archive_target = self.runtime / "licenses/sources/source.zip"
        archive_target.parent.mkdir(parents=True)
        archive_target.write_bytes(data)
        for name, data in notices.items():
            target = self.runtime / "licenses/PySide6" / name.removeprefix("project/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    def test_real_cli_keeps_pinned_license_texts_and_complete_source_archive(self):
        self.add_license_source()
        result = self.run_verifier("--runtime", str(self.runtime), "--catalog")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("licenses/PySide6/LICENSES/LGPL-3.0-only.txt", result.stdout)
        self.assertIn("licenses/sources/source.zip", result.stdout)
        self.assertNotIn("code.py", result.stdout)

    def test_real_cli_refuses_source_with_only_gpl_license_text(self):
        self.add_license_source(include_lgpl=False)
        result = self.run_verifier("--runtime", str(self.runtime))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("lacks LGPLv3/GPLv3", result.stderr)

    def test_real_cli_refuses_windows_device_member(self):
        with zipfile.ZipFile(self.archive, "a") as output:
            output.writestr("CON.txt", b"device fixture")
        lock = json.loads(self.lock.read_text(encoding="utf-8"))
        data = self.archive.read_bytes()
        lock["archives"][0].update(sha256=hashlib.sha256(data).hexdigest(), size=len(data))
        self.lock.write_text(json.dumps(lock), encoding="utf-8")
        result = self.run_verifier()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unsafe portable runtime path", result.stderr)

    def test_real_cli_refuses_case_colliding_archive_members(self):
        with zipfile.ZipFile(self.archive, "a") as output:
            output.writestr("PYTHON.exe", b"collision")
        lock = json.loads(self.lock.read_text(encoding="utf-8"))
        data = self.archive.read_bytes()
        lock["archives"][0].update(sha256=hashlib.sha256(data).hexdigest(), size=len(data))
        self.lock.write_text(json.dumps(lock), encoding="utf-8")
        result = self.run_verifier()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("case-colliding", result.stderr)


if __name__ == "__main__":
    unittest.main()

