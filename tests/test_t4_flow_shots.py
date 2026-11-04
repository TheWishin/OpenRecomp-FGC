"""Synthetic T4 screenshots render the actual shared QML without installed games."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class T4FlowShots(unittest.TestCase):
    def test_synthetic_shared_screens_render_without_qml_warnings(self):
        scratch = ROOT / "build" / "tmp-home"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="t4flow-shots-", dir=scratch) as directory:
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                       OPENRECOMP_HOME=directory)
            result = subprocess.run([sys.executable, str(ROOT / "tools" / "t4_flow_shots.py"), directory,
                                     "--languages", "en"], cwd=ROOT, env=env,
                                    capture_output=True, text=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stderr, "", result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report["synthetic"])
            self.assertEqual(set(report["captures"]), {"en_" + screen + ".png" for screen in
                                                      ("login", "lobby", "challenge", "match_found", "result")})
            for name in report["captures"]:
                with self.subTest(screen=name):
                    image = Path(directory, name).read_bytes()
                    self.assertEqual(image[:8], b"\x89PNG\r\n\x1a\n")
                    self.assertEqual(struct.unpack(">II", image[16:24]), (1920, 1080))
                    self.assertGreater(len(image), 10000)


if __name__ == "__main__":
    unittest.main()
