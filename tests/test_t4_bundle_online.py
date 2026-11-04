"""Source-bundle online details, with metadata and fake tools only."""
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock
import zipfile

from openrecomp.adapters.t4_online import DirectCheckError
from test_t4_beta_network import Subject, setUpModule, tearDownModule  # noqa: F401 -- no shipped server here


class BundleOnlineTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.a = Subject(str(self.root))
        self.a.online_action("mode_direct")
        self.a.online_state()

    def stamp(self, value):
        folder = self.root / "runtime"
        folder.mkdir(exist_ok=True)
        (folder / "t4net_build.json").write_text(json.dumps(value), encoding="utf-8")

    def test_build_and_compiler_are_visible_before_peer_checks(self):
        self.stamp(dict(id="0123456789abcdef", toolchain=["CXX_ID=MSVC", "CXX_VERSION=19.44.35221"]))
        with mock.patch.object(self.a, "_direct_process", side_effect=AssertionError("No tool on read")):
            state = self.a.online_state()
        self.assertEqual(state["build_id"], "0123456789abcdef")
        self.assertEqual(state["compiler"], "MSVC 19.44.35221")
        self.assertTrue(all(check["ok"] is None for check in state["checks"]))
        self.assertEqual(self.a.starts, [])

    def test_untrusted_or_incomplete_stamp_does_not_reach_the_view(self):
        for value in ([1], {}, dict(id="0123456789abcdef", toolchain=["CXX_ID=MSVC"]),
                      dict(id="0123456789abcdef", toolchain=["CXX_ID=MSVC", "CXX_VERSION=@bad"]),
                      dict(id="not-a-build", toolchain=["CXX_ID=MSVC", "CXX_VERSION=19.44"]),
                      dict(id="0123456789abcdef", toolchain=["CXX_ID=MSVC", "CXX_ID=other", "CXX_VERSION=19.44"])):
            with self.subTest(value=value):
                self.stamp(value)
                state = self.a.online_state()
                self.assertEqual((state["build_id"], state["compiler"]), ("", ""))

    def test_collector_success_without_a_zip_is_refused(self):
        self.a._direct_last_run = dict(run_dir=str(self.root))
        with mock.patch.object(self.a, "_direct_user_folder", return_value=str(self.root)), \
                mock.patch.object(self.a, "_direct_process", return_value=0):
            with self.assertRaisesRegex(DirectCheckError, "@t4.direct_logs_failed"):
                self.a._direct_collect_logs(threading.Event())

    def test_collector_reports_only_its_new_valid_zip(self):
        self.a._direct_last_run = dict(run_dir=str(self.root))
        stale = self.root / "T4-test-logs-old.zip"
        with zipfile.ZipFile(stale, "x"):
            pass

        def collect(command, cancel):
            target = Path(command[command.index("-OutputDirectory") + 1], "T4-test-logs-new.zip")
            with zipfile.ZipFile(target, "x"):
                pass
            return 0

        with mock.patch.object(self.a, "_direct_user_folder", return_value=str(self.root)), \
                mock.patch.object(self.a, "_direct_process", side_effect=collect):
            self.a.online_action("collect_logs")
            self.a.online_poll()
        path = Path(self.a.online_state()["log_path"])
        self.assertTrue(path.is_file())
        self.assertEqual(path.name, "T4-test-logs-new.zip")
        self.assertNotEqual(path.parent, self.root)
        self.assertEqual(self.a.online_state()["message"], "@t4.direct_logs_saved")

    def test_collector_rejects_renamed_non_archive(self):
        self.a._direct_last_run = dict(run_dir=str(self.root))

        def collect(command, cancel):
            target = Path(command[command.index("-OutputDirectory") + 1], "T4-test-logs-fake.zip")
            target.write_text("not an archive", encoding="utf-8")
            return 0

        with mock.patch.object(self.a, "_direct_user_folder", return_value=str(self.root)), \
                mock.patch.object(self.a, "_direct_process", side_effect=collect):
            self.a.online_action("collect_logs")
            self.a.online_poll()
        self.assertEqual(self.a.online_state()["log_path"], "")
        self.assertEqual(self.a.online_state()["message"], "@t4.direct_logs_failed")

    def test_source_direct_start_uses_the_human_test_profile(self):
        self.a.core.source_only = True
        verified = dict(paths=(), stamps=(), build="0123456789abcdef", checked_at=time.monotonic())
        self.a._direct_verified = verified
        self.a._direct_phase = "checked"
        with mock.patch.object(self.a, "_online_game_check", return_value=""), \
                mock.patch.object(self.a, "_direct_log_stamps", return_value={}):
            self.a.online_action("start_match")
        env = self.a.starts[0]
        self.assertEqual(env["TEKKEN4_NET_COALESCE"], "1")
        self.assertEqual(env["TEKKEN4_NET_DIAG"], "1")
        self.assertEqual(env["TEKKEN4_NET_AUTO_VS"], "0")
        self.assertEqual(env["TEKKEN4_NET_MAXPRED"], "8")
        self.assertEqual(env["TEKKEN4_RB_AUDIO_TIMELINE"], "0")


if __name__ == "__main__":
    unittest.main()
