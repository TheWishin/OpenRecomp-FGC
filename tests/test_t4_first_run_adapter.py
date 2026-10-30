"""First-run adapter work uses synthetic text and mock workers; no game or build starts."""
from pathlib import Path
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp.adapters.t4 import T4


MANIFEST = dict(id="t4", short="T4", adapter="t4")


class FirstRunAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext(tempfile.TemporaryDirectory(dir=Path(__file__).parent))
        self.path = Path(self.tmp) / "synthetic-source.txt"
        self.path.write_text("Synthetic verifier input; no disc data.", encoding="utf-8")
        self.core = SimpleNamespace(
            load_settings=lambda: {}, save_settings=mock.Mock(),
            effective_iso=lambda settings: settings.get("iso", ""),
            verify_iso=mock.Mock(return_value=(True, "synthetic success")),
            play_problems=lambda settings: [], build_command=lambda iso: ["synthetic-build", iso],
            STEPS=[("verify", "Verify"), ("runtime", "Compile")],
        )
        self.adapter = T4(MANIFEST, {}, "synthetic-root", core=self.core)

    def check(self):
        self.adapter._check_iso(str(self.path))

    def test_iso_check_is_background_work_and_duplicate_confirm_does_not_start_another(self):
        with mock.patch("openrecomp.adapters.t4.threading.Thread") as thread:
            self.assertEqual(self.adapter.set_source("iso", str(self.path)), "@iso.checking")
            self.assertEqual(self.adapter.source_state(), dict(running=True, result="", id="iso", ok=False))
            self.assertEqual(self.adapter.build_ready(), "@iso.checking")
            self.assertEqual(self.adapter.set_source("iso", "other"), "@iso.checking")
            thread.assert_called_once()
            thread.return_value.start.assert_called_once_with()
            self.core.verify_iso.assert_not_called()

    def test_refusal_is_persistent_names_supported_disc_and_preserves_previous_choice(self):
        self.adapter.s["iso"] = "synthetic-old-choice"
        self.core.verify_iso.return_value = (False, "Unsupported serial: synthetic-other-disc")
        self.check()
        state = self.adapter.source_state()
        self.assertFalse(state["ok"])
        self.assertEqual(state["result"]["_text"], "iso.refused")
        self.assertIn("synthetic-other-disc", state["result"]["_values"]["error"])
        self.assertEqual(self.adapter.sources()[0]["note"], state["result"])
        self.assertEqual(self.adapter.s["iso"], "synthetic-old-choice")
        self.core.save_settings.assert_not_called()

    def test_checker_exception_finishes_with_actionable_failure_without_saving(self):
        self.core.verify_iso.side_effect = OSError("synthetic helper missing")
        self.check()
        self.assertFalse(self.adapter.source_state()["running"])
        self.assertEqual(self.adapter.source_state()["result"]["_text"], "iso.check_failed")
        self.assertNotIn("iso", self.adapter.s)

    def test_worker_start_failure_does_not_leave_source_rows_permanently_busy(self):
        for sid in ("iso", "folder"):
            with self.subTest(source=sid), mock.patch("openrecomp.adapters.t4.threading.Thread") as worker:
                worker.return_value.start.side_effect = RuntimeError("synthetic worker unavailable")
                result = self.adapter.set_source(sid, "synthetic-source")
                self.assertFalse(self.adapter.source_state()["running"])
                self.assertEqual(result["_text"] if isinstance(result, dict) else result,
                                 "iso.check_failed" if sid == "iso" else "@t4.install_failed")

    def test_accepted_iso_is_saved_and_build_refuses_unverified_or_changed_input(self):
        self.assertEqual(self.adapter.build_ready(), "@iso.choose_first")
        self.check()
        self.assertEqual(self.adapter.build_ready(), "")
        self.assertTrue(self.adapter.source_state()["ok"])
        self.core.save_settings.assert_called_once_with(dict(iso=str(self.path)))
        self.path.write_text("Changed synthetic input", encoding="utf-8")
        self.assertEqual(self.adapter.build_ready(), "@iso.choose_first")
        with mock.patch("openrecomp.adapters.t4.ProcessBuild") as process:
            with self.assertRaisesRegex(RuntimeError, "iso.choose_first"):
                self.adapter.build_start()
            process.assert_not_called()

    def test_source_changed_during_verification_is_rejected(self):
        def change(_path):
            self.path.write_text("Changed during synthetic check", encoding="utf-8")
            return True, "synthetic success"
        self.core.verify_iso.side_effect = change
        self.check()
        self.assertEqual(self.adapter.source_state()["result"], "@iso.changed")
        self.core.save_settings.assert_not_called()

    def test_failed_settings_save_does_not_replace_previous_iso(self):
        self.adapter.s["iso"] = "previous-choice"
        self.core.save_settings.side_effect = OSError("synthetic disk full")
        self.check()
        self.assertEqual(self.adapter.s["iso"], "previous-choice")
        self.assertEqual(self.adapter.source_state()["result"]["_text"], "iso.check_failed")

    def test_retry_resets_progress_and_creation_failure_stays_in_build_screen(self):
        self.check()
        self.adapter.build_step_no = (8, 8)
        with mock.patch("openrecomp.adapters.t4.ProcessBuild", side_effect=OSError("synthetic spawn failure")):
            with self.assertRaises(OSError):
                self.adapter.build_start()
        self.assertEqual(self.adapter.build_state()["fraction"], 0)
        self.assertEqual(self.adapter.build_state()["result"]["_text"], "t4.build_start_failed")

    def test_build_failure_keeps_error_inline_and_marks_failed_step(self):
        self.adapter.build = SimpleNamespace(running=lambda: False, cancelled=False, code=17)
        self.adapter._on_line("[2/2] runtime - Compile")
        self.adapter._on_line("ERROR: synthetic compiler failed")
        self.adapter._build_end(self.adapter.build)
        state = self.adapter.build_state()
        self.assertEqual(state["result"]["_text"], "t4.build_failed")
        self.assertEqual(state["result"]["_values"]["error"], "ERROR: synthetic compiler failed")
        self.assertEqual(state["steps"][-1]["v"], "@t4.step_failed")

    def test_build_success_reaches_full_progress_only_when_game_is_ready(self):
        self.adapter.build = SimpleNamespace(running=lambda: False, cancelled=False, code=0)
        self.adapter._on_line("[2/2] runtime - Compile")
        self.adapter._build_end(self.adapter.build)
        self.assertEqual(self.adapter.build_state()["fraction"], 1)
        self.assertEqual(self.adapter.build_state()["result"], "@t4.build_finished")
        self.core.play_problems = lambda settings: ["synthetic missing output"]
        self.adapter._build_end(self.adapter.build)
        self.assertEqual(self.adapter.build_state()["result"], "@t4.build_incomplete")

    def test_game_start_and_build_cannot_overlap(self):
        self.check()
        self.adapter.build = SimpleNamespace(running=lambda: True)
        with self.assertRaisesRegex(RuntimeError, "t4.work_busy"):
            self.adapter.start()
        with self.assertRaisesRegex(RuntimeError, "t4.work_busy"):
            self.adapter.build_start()

    def test_missing_bundled_tools_refuses_build_and_offers_complete_release_by_pad(self):
        self.check()
        self.core.bundled_toolchain = lambda: False
        self.assertEqual(self.adapter.build_ready(), "@t4.portable_required")
        folder = self.adapter.sources()[0]
        self.assertEqual((folder["id"], folder["kind"], folder["exts"]), ("folder", "file_or_folder", [".zip"]))
        with mock.patch("openrecomp.adapters.t4.ProcessBuild") as process:
            with self.assertRaisesRegex(RuntimeError, "t4.portable_required"):
                self.adapter.build_start()
            process.assert_not_called()
        self.assertTrue(self.adapter.ready())

    def test_incomplete_install_can_be_replaced_without_leaving_launcher(self):
        with mock.patch("openrecomp.adapters.t4.install_source", return_value="reload") as install:
            self.assertEqual(self.adapter.set_source("folder", "synthetic.zip"), "@t4.installing")
            self.adapter._source_thread.join(5)
        self.assertEqual(self.adapter.source_state(), dict(running=False, result="reload", id="folder", ok=True))
        install.assert_called_once_with(MANIFEST, self.adapter.config, "synthetic.zip")

    def test_failed_play_record_remains_visible_after_return(self):
        self.adapter.s["last_run"] = dict(ok=False, exit=3, note="synthetic runtime failure")
        detail = self.adapter.status()["detail"]
        self.assertEqual(detail["_text"], "t4.play_failed")
        self.assertEqual(detail["_values"]["error"], "synthetic runtime failure")

    def test_settings_and_play_record_survive_iso_save_in_flight(self):
        for action in ("setting", "aa", "last_run"):
            with self.subTest(action=action):
                self.adapter.s = {}
                iso_entered = threading.Event()
                competing_attempted = threading.Event()
                release_iso = threading.Event()
                lock = threading.RLock()
                disk = {}
                errors = []

                class ObservedLock:
                    def __enter__(self):
                        if threading.current_thread().name == "settings-worker":
                            competing_attempted.set()
                        lock.acquire()
                    def __exit__(self, *_args):
                        lock.release()

                self.adapter._settings_lock = ObservedLock()

                def save(settings):
                    snapshot = dict(settings)
                    if threading.current_thread().name == "iso-worker":
                        iso_entered.set()
                        if not release_iso.wait(2):
                            raise RuntimeError("synthetic save release timed out")
                    disk.clear()
                    disk.update(snapshot)

                self.core.save_settings.side_effect = save
                self.core.release_run_lock = mock.Mock()

                def compete():
                    try:
                        if action == "last_run":
                            self.adapter._wait(SimpleNamespace(wait=lambda: dict(ok=True, exit=0)))
                        else:
                            self.adapter.set_setting("aa" if action == "aa" else "resolution",
                                                     "off" if action == "aa" else "1080p")
                    except Exception as error:
                        errors.append(error)
                    finally:
                        competing_attempted.set()

                with mock.patch("openrecomp.adapters.t4.save_config"):
                    iso_worker = threading.Thread(target=self.check, name="iso-worker")
                    settings_worker = threading.Thread(target=compete, name="settings-worker")
                    iso_worker.start()
                    try:
                        self.assertTrue(iso_entered.wait(2))
                        settings_worker.start()
                        self.assertTrue(competing_attempted.wait(2))
                    finally:
                        release_iso.set()
                        iso_worker.join(2)
                        if settings_worker.ident is not None:
                            settings_worker.join(2)
                self.assertFalse(iso_worker.is_alive())
                self.assertFalse(settings_worker.is_alive())
                self.assertFalse(errors)
                expected = dict(iso=str(self.path))
                if action == "last_run":
                    expected["last_run"] = dict(ok=True, exit=0)
                elif action == "aa":
                    expected["aa"] = False
                else:
                    expected["resolution"] = "1080p"
                self.assertEqual(disk, expected)
                self.assertEqual(self.adapter.s, expected)

    def test_failed_install_replacement_stays_visible_on_source_row(self):
        self.core.bundled_toolchain = lambda: False
        with mock.patch("openrecomp.adapters.t4.install_source", return_value="@t4.install_failed"):
            self.adapter._replace_install("synthetic.zip")
        self.assertEqual(self.adapter.sources()[0]["note"], "@t4.install_failed")


if __name__ == "__main__":
    unittest.main()
