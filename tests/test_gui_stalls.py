"""The window must never wait for the disk: things asked on every redraw are answered from memory."""
import os
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp import stall
from openrecomp.adapters import t5_coexist


class NativeSettings(dict):
    def __init__(self):
        super().__init__(nickname="")
        self.path = None
        self.out_dir = None


class CoexistPaths(unittest.TestCase):
    def setUp(self):
        base = tempfile.TemporaryDirectory()
        self.addCleanup(base.cleanup)
        self.root = os.path.join(base.name, "install")
        self.home = os.path.join(base.name, "home")
        os.makedirs(self.root)
        os.makedirs(self.home)
        env = mock.patch.dict(os.environ, OPENRECOMP_HOME=self.home)
        env.start()
        self.addCleanup(env.stop)
        core = SimpleNamespace(Settings=NativeSettings, DEFAULTS={})
        self.settings = t5_coexist.load_settings(core, self.root)

    def test_private_paths_are_checked_once(self):
        first = self.settings.online_config_path
        with mock.patch.object(t5_coexist.os.path, "realpath", side_effect=AssertionError("disk asked again")):
            for _ in range(50):
                self.assertEqual(self.settings.online_config_path, first)
        self.assertTrue(first.startswith(self.home))

    def test_a_new_home_or_protected_folder_is_checked_again(self):
        first = self.settings.online_config_path
        other = self.home + "-2"
        os.makedirs(other)
        with mock.patch.dict(os.environ, OPENRECOMP_HOME=other):
            self.assertTrue(self.settings.online_config_path.startswith(other))
        self.settings._coexist_protected.append(self.home)       # e.g. a settings copy inside the home
        with self.assertRaises(ValueError):
            self.settings.online_config_path
        self.settings._coexist_protected.pop()
        self.assertEqual(self.settings.online_config_path, first)


class StallWatchTests(unittest.TestCase):
    def test_late_beat_is_one_stall_with_tag(self):
        now = [0.0]
        watch = stall.StallWatch(100, clock=lambda: now[0])
        watch.tag = "lobby"
        for step in (0.01, 0.01, 0.25, 0.01, 0.12):
            now[0] += step
            watch.beat()
        self.assertEqual([(ms, tag) for ms, tag, _ in watch.stalls], [(250, "lobby"), (120, "lobby")])
        self.assertEqual(watch.summary("lobby"), dict(count=2, worst=250, total=370))
        self.assertEqual(watch.summary("other")["count"], 0)

    def test_watcher_names_where_the_gui_thread_was(self):
        with tempfile.TemporaryDirectory() as folder:
            log = os.path.join(folder, "stalls.log")
            watch = stall.StallWatch(60, log).start()
            self.addCleanup(watch.stop)

            def slow_disk_read():
                time.sleep(0.2)

            watch.beat()
            # Scheduling before the initial beat is outside the controlled pause below.
            watch.stalls.clear()
            slow_disk_read()
            watch.beat()
            self.assertEqual(len(watch.stalls), 1)
            self.assertIn("slow_disk_read", watch.stalls[0][2])
            with open(log, encoding="utf-8") as f:
                self.assertIn("slow_disk_read", f.read())

    def test_off_without_the_variable(self):
        self.assertIsNone(stall.from_env({}))
        watch = stall.from_env(dict(OPENRECOMP_STALL_LOG=os.devnull, OPENRECOMP_STALL_MS="x"))
        self.addCleanup(watch.stop)
        self.assertEqual(watch.threshold, 0.1)
        self.assertNotEqual(watch.main, None)
        self.assertTrue(any(t.name == "openrecomp-stallwatch" for t in threading.enumerate()))


if __name__ == "__main__":
    unittest.main()
