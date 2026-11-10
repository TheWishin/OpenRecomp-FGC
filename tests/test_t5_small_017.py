"""0.1.7 small items: the game-start support line, pictures in a child process, the unlock-items hint."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from openrecomp import t5_startlog
from openrecomp.adapters.t5dr import T5DR
import openrecomp.i18n as i18n


class Settings(dict):
    out_dir = r"C:\Users\Alice Smith\T5\native"

    def env_overrides(self):
        return {"PS3_NICKNAME": self["nickname"], "PS3_REPLAY_DIR": r"C:\Users\Alice Smith\Videos\rep", "PS3_VSYNC": "0"}


def adapter(core_log):
    a = T5DR.__new__(T5DR)
    a.s = Settings(nickname="Zorbax")
    a.game = SimpleNamespace(log_path=r"C:\Users\Alice Smith\T5\native\logs\game-1.log", running=lambda: False)
    a.core = SimpleNamespace(log=core_log)
    a.root = tempfile.gettempdir()
    return a


class StartLine(unittest.TestCase):
    def test_line_has_process_log_settings_and_launcher_env_names(self):
        lines = []
        a = adapter(lines.append)
        with mock.patch.object(T5DR, "_support_import", side_effect=ImportError, create=True):
            text = t5_startlog.write(a, 4242, {"T5_NET_MODE": "rollback", "T5_NET_PEER": "1.2.3.4:5"})
        self.assertEqual(lines, [text])
        self.assertTrue(text.startswith("game started: process 4242, log game-1.log, settings give "))
        self.assertIn("PS3_VSYNC=0", text)
        self.assertIn("asked for by the launcher: T5_NET_MODE, T5_NET_PEER", text)
        self.assertNotIn("1.2.3.4", text)           # launcher env is named, never valued

    def test_private_values_are_masked_without_the_installs_scrubber(self):
        lines = []
        with mock.patch.object(T5DR, "_support_import", side_effect=ImportError, create=True):
            text = t5_startlog.write(adapter(lines.append), 1)
        self.assertNotIn("Alice Smith", text)
        self.assertNotIn("Zorbax", text)
        self.assertIn(r"C:\Users\<user>\Videos\rep", text)
        self.assertIn("PS3_NICKNAME=<player>", text)

    def test_installs_scrubber_is_used_when_present(self):
        seen = {}

        class Scrubber:
            def __init__(self, **kw):
                seen.update(kw)

            def text(self, s):
                return s.replace("Zorbax", "<player>")
        a = adapter(lambda t: None)
        with mock.patch.object(T5DR, "_support_import", return_value=SimpleNamespace(Scrubber=Scrubber), create=True):
            text = t5_startlog.write(a, 1)
        self.assertIn("Zorbax", seen["player_names"])
        self.assertNotIn("Zorbax", text)

    def test_a_failing_log_never_stops_the_start(self):
        a = adapter(mock.Mock(side_effect=OSError("disk full")))
        self.assertEqual(t5_startlog.write(a, 1), "")

    def test_start_writes_the_line(self):
        a = adapter(lambda t: None)
        game = mock.Mock(running=lambda: True, proc=None)
        game.start.return_value = 77
        a.core.GameRun = lambda *args: game
        a.ready = lambda: True
        a.running = lambda: False
        with mock.patch("openrecomp.adapters.t5dr.game_process_running", return_value=False), \
             mock.patch("openrecomp.adapters.t5dr.LaunchGuard"), \
             mock.patch.object(a, "_track_playtime"), mock.patch.object(t5_startlog, "write") as write:
            a.start({"X": "1"})
        write.assert_called_once_with(a, 77, {"X": "1"})


class ArtChild(unittest.TestCase):
    def fake_install(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        package = root / "lobby" / "t5lobby"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("")
        (package / "rank_art.py").write_text(
            "import os\n"
            "def folder_for(out): return os.path.join(out, 'cache', 'ranks')\n"
            "def is_ready(folder): return False\n"
            "def extract(out):\n"
            "    os.makedirs(folder_for(out), exist_ok=True)\n"
            "    open(os.path.join(folder_for(out), 'rank_00.png'), 'wb').write(b'x')\n")
        return root

    def test_plates_are_read_by_a_separate_process(self):
        root = self.fake_install()
        out = root / "out"
        a = T5DR.__new__(T5DR)
        a.root, a.s = str(root), SimpleNamespace(out_dir=str(out))
        with mock.patch("openrecomp.t5_art_child.subprocess.run", wraps=subprocess.run) as run:
            code, last = a._art_child({"job": "plates"})
        self.assertEqual((code, last), (0, ""))
        self.assertEqual(run.call_args.args[0][1], "-I")                   # isolated: no user site, no PYTHONPATH
        self.assertTrue((out / "cache" / "ranks" / "rank_00.png").is_file())
        self.assertNotIn("t5lobby", sys.modules)                           # nothing was imported into this process

    def test_child_failure_is_reported_by_exit_code_and_last_line(self):
        a = T5DR.__new__(T5DR)
        a.root, a.s = tempfile.gettempdir(), SimpleNamespace(out_dir=tempfile.gettempdir())
        code, last = a._art_child({"job": "plates"})
        self.assertEqual(code, 1)
        self.assertTrue(last)

    def test_plates_wait_while_a_game_or_online_match_runs(self):
        a = T5DR.__new__(T5DR)
        a.state = lambda: {"built": True}
        a.game = SimpleNamespace(running=lambda: True)
        with mock.patch("openrecomp.adapters.t5dr.threading.Thread") as thread:
            a._start_rank_plates()
            thread.assert_not_called()
            self.assertFalse(a.__dict__.get("_plates_tried"))          # asked again later
            a.game = SimpleNamespace(running=lambda: False)
            a._online_driver = object()
            a._start_rank_plates()
            thread.assert_not_called()
            a._online_driver = None
            a._start_rank_plates()
            thread.assert_called_once()

    def test_renders_wait_for_idle_and_are_not_marked_tried(self):
        a = T5DR.__new__(T5DR)
        a._fighters = [dict(id=9, key="jin")]
        a.state = lambda: {"built": True}
        a.game = SimpleNamespace(running=lambda: True)
        with mock.patch("openrecomp.adapters.t5dr.art_dir", return_value=tempfile.gettempdir() + "/nope-017"):
            self.assertEqual(a.fighter_render("jin"), "")
        self.assertEqual(a._render_tried, set())

    def test_the_package_ships_the_child_file(self):
        from tools import package_release
        listed = [f for f in package_release.SOURCE_FILES]
        if "openrecomp/adapters/t5dr.py" in listed:
            self.assertIn("openrecomp/t5_art_child.py", listed)
            self.assertIn("openrecomp/t5_startlog.py", listed)


class UnlockHint(unittest.TestCase):
    def test_every_catalog_names_the_greyed_out_costume_parts(self):
        folder = Path(i18n.__file__).parent
        catalogs = sorted(folder.glob("*.json"))
        self.assertGreaterEqual(len(catalogs), 7)
        en = json.loads((folder / "en.json").read_text(encoding="utf-8"))["free_items.hint"]
        self.assertIn("greyed out", en)
        for path in catalogs:
            text = json.loads(path.read_text(encoding="utf-8"))["free_items.hint"]
            self.assertTrue(text.strip())
            if path.stem != "en":
                self.assertNotEqual(text, en)


if __name__ == "__main__":
    unittest.main()
