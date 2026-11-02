"""Exercise run.cmd with a harmless module, without opening the launcher."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
EMBEDDED = ROOT / "dist/portable-runtime"


@unittest.skipUnless(os.name == "nt", "run.cmd is a Windows entry point")
class PortableRunTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix=".run-test-", dir=ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        shutil.copyfile(ROOT / "run.cmd", self.root / "run.cmd")
        module = self.root / "openrecomp"
        module.mkdir()
        (module / "__init__.py").write_text("", encoding="utf-8")
        (module / "__main__.py").write_text(
            "import json, pathlib, sys\n"
            "report = {'executable': sys.executable, 'args': sys.argv[1:]}\n"
            "if '--check-qt' in sys.argv[1:]:\n"
            "    from PySide6.QtCore import qVersion\n"
            "    report['qt'] = qVersion()\n"
            "    report['python'] = list(sys.version_info[:2])\n"
            "pathlib.Path(__file__).parents[1].joinpath('started.json').write_text("
            "json.dumps(report), encoding='utf-8')\n", encoding="utf-8")

    def interpreter(self, location, *, console=True, windowed=True):
        folder = self.root / location
        folder.mkdir(parents=True, exist_ok=True)
        excluded = {name for name, included in (("python.exe", console),
                                                ("pythonw.exe", windowed)) if not included}
        if (EMBEDDED / "python312.dll").is_file():
            # Only copy CPython's immediate files, never the Qt payload. The
            # original site-packages stays in the prepared runtime directory.
            for source in EMBEDDED.iterdir():
                if (source.is_file() and source.name not in excluded
                        and source.suffix.lower() in {".exe", ".dll", ".pyd", ".zip"}):
                    shutil.copyfile(source, folder / source.name)
            package_path = os.path.relpath(EMBEDDED / "Lib/site-packages", folder)
            app_path = os.path.relpath(self.root, folder)
            (folder / "python312._pth").write_text(
                "python312.zip\n.\n" + app_path + "\n" + package_path + "\n", encoding="ascii")
            return
        # Normal source checkouts may have only a working venv. Its redirectors
        # also run the harmless fixture module without importing the launcher.
        venv_python = ROOT / ".venv/Scripts/python.exe"
        try:
            checked = subprocess.run([str(venv_python), "-I", "-B", "-c", "pass"],
                                     capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            checked = None
        if checked is None or checked.returncode:
            self.skipTest("Neither a prepared portable runtime nor a working repository venv is available")
        config = folder.parent if folder.name == "Scripts" else folder
        shutil.copyfile(ROOT / ".venv/pyvenv.cfg", config / "pyvenv.cfg")
        for name in ("python.exe", "pythonw.exe"):
            if name not in excluded:
                shutil.copyfile(ROOT / ".venv/Scripts" / name, folder / name)

    def start(self, *, qt=False):
        arguments = ["--windowed", "argument with spaces"]
        if qt:
            arguments.append("--check-qt")
        completed = subprocess.run(
            [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(self.root / "run.cmd"), *arguments],
            cwd=self.root, capture_output=True, text=True, timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        marker = self.root / "started.json"
        deadline = time.monotonic() + 10
        report = None
        while time.monotonic() < deadline:
            try:
                report = json.loads(marker.read_text(encoding="utf-8"))
                break
            except (OSError, ValueError):
                time.sleep(.05)
        self.assertIsNotNone(report, "run.cmd returned without starting its selected interpreter")
        self.assertEqual(report["args"], arguments)
        return report

    def test_portable_interpreter_takes_precedence_over_existing_venv(self):
        self.interpreter("portable")
        self.interpreter(".venv/Scripts")
        self.assertEqual(Path(self.start()["executable"]), self.root / "portable/pythonw.exe")

    def test_portable_runtime_starts_without_creating_a_venv(self):
        self.interpreter("portable")
        self.assertEqual(Path(self.start()["executable"]), self.root / "portable/pythonw.exe")
        self.assertFalse((self.root / ".venv").exists())

    def test_existing_venv_is_used_without_portable_runtime(self):
        self.interpreter(".venv/Scripts")
        self.assertEqual(Path(self.start()["executable"]), self.root / ".venv/Scripts/pythonw.exe")

    def test_incomplete_portable_runtime_keeps_existing_venv_path(self):
        self.interpreter("portable", console=False)
        self.interpreter(".venv/Scripts")
        self.assertEqual(Path(self.start()["executable"]), self.root / ".venv/Scripts/pythonw.exe")

    def test_portable_without_windowed_interpreter_keeps_existing_venv_path(self):
        self.interpreter("portable", windowed=False)
        self.interpreter(".venv/Scripts")
        self.assertEqual(Path(self.start()["executable"]), self.root / ".venv/Scripts/pythonw.exe")

    @unittest.skipUnless((EMBEDDED / "python312.dll").is_file(), "Prepared portable runtime unavailable")
    def test_embedded_batch_entry_point_imports_real_qt_without_a_window(self):
        self.interpreter("portable")
        report = self.start(qt=True)
        self.assertEqual(Path(report["executable"]), self.root / "portable/pythonw.exe")
        self.assertEqual(report["python"], [3, 12])
        self.assertEqual(report["qt"], "6.8.2")


if __name__ == "__main__":
    unittest.main()
