"""Update UI lifecycle with fake network, runtime and processes."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp import manifest
from openrecomp.update_service import UpdateService


class Service(unittest.TestCase):
    def setUp(self):
        self.api = mock.Mock()
        self.api.check_release.return_value = dict(version="v1.2.3", notes="Changes", size=42)
        self.api.stage_update.return_value = Path("fake-stage")
        self.busy = False
        self.quit = mock.Mock()
        self.service = UpdateService("fake-install", api=self.api, busy=lambda: self.busy,
                                     quit=self.quit, worker=lambda fn: fn())

    def offer(self):
        self.service.check()
        self.assertEqual(self.service.state["phase"], "checking")
        self.service.poll()
        self.assertEqual(self.service.state["phase"], "available")

    def test_check_never_downloads_or_installs_without_confirmation(self):
        self.offer()
        self.api.stage_update.assert_not_called()
        self.api.launch_update.assert_not_called()
        self.quit.assert_not_called()
        self.assertEqual(self.service.state["size"], 42)

    def test_confirm_stages_and_launches_once_before_quitting(self):
        self.offer()
        self.assertTrue(self.service.install())
        self.api.launch_update.assert_not_called()
        self.service.poll()
        self.service.poll()
        self.api.stage_update.assert_called_once()
        self.api.launch_update.assert_called_once_with(Path("fake-install"), Path("fake-stage"))
        self.quit.assert_called_once()

    def test_busy_refuses_confirm_and_defers_helper_when_activity_starts_during_download(self):
        self.offer()
        self.busy = True
        self.assertFalse(self.service.install())
        self.api.stage_update.assert_not_called()
        self.busy = False
        self.assertTrue(self.service.install())
        self.busy = True
        self.service.poll()
        self.api.launch_update.assert_not_called()
        self.busy = False
        self.service.poll()
        self.api.launch_update.assert_called_once()

    def test_failed_stage_or_helper_keeps_launcher_open(self):
        for operation in ("stage_update", "launch_update"):
            with self.subTest(operation=operation):
                self.setUp()
                getattr(self.api, operation).side_effect = OSError("private detail")
                self.offer()
                self.service.install()
                self.service.poll()
                self.assertEqual(self.service.state["phase"], "error")
                self.assertNotIn("private detail", repr(self.service.state))
                self.quit.assert_not_called()

    def test_unconfigured_check_fails_closed_with_localizable_state(self):
        error = RuntimeError("private detail")
        error.key = "updates_unconfigured"
        self.api.check_release.side_effect = error
        self.service.check()
        self.service.poll()
        self.assertEqual(self.service.state["phase"], "unconfigured")
        self.assertFalse(self.service.install())
        self.api.stage_update.assert_not_called()

    def test_duplicate_work_is_ignored(self):
        self.service.check()
        self.service.check()
        self.api.check_release.assert_called_once()
        self.service.poll()
        self.service.install()
        self.service.check()
        self.assertFalse(self.service.install())
        self.api.stage_update.assert_called_once()


class Integration(unittest.TestCase):
    def test_pending_worker_phase_redraws_before_results_arrive(self):
        from openrecomp import app
        for phase in ("checking", "installing"):
            with self.subTest(phase=phase):
                backend = SimpleNamespace(updates=SimpleNamespace(state=dict(phase=phase), poll=lambda: False),
                                          nav=SimpleNamespace(update_state={}), _update_phase="idle")
                self.assertTrue(app.Backend._poll_updates(backend))
                self.assertEqual(backend.nav.update_state["phase"], phase)
                self.assertFalse(app.Backend._poll_updates(backend))

    def test_helper_failures_are_explained_after_restart(self):
        from openrecomp import app, i18n
        for status, key in (("rolled_back", "updates.rolled_back"), ("unchanged", "updates.failed"),
                            ("recovery_required", "updates.recovery")):
            with self.subTest(status=status), mock.patch.object(app.mf, "load_config", return_value={"language": "en"}), \
                    mock.patch.object(app, "load_games", return_value=([], [])), \
                    mock.patch.object(app, "Pads"), mock.patch.object(app, "XInputReader"), \
                    mock.patch.object(app, "QTimer"), \
                    mock.patch.object(app.updater, "update_result", return_value=dict(status=status)):
                backend = app.Backend()
                self.assertEqual(backend.view["toast"], i18n.text("en", key))

    def test_startup_acknowledges_only_after_scene_loaded_and_health_delay(self):
        from openrecomp import app
        backend = mock.Mock()
        backend.updates.root = Path("fake-install")
        backend.nav.fullscreen = False
        callbacks = []
        with mock.patch.object(app, "QGuiApplication"), mock.patch.object(app, "Backend", return_value=backend), \
                mock.patch.object(app, "make_engine") as engine, mock.patch.object(app, "QIcon"), \
                mock.patch.object(app.QTimer, "singleShot", side_effect=lambda delay, fn: callbacks.append((delay, fn))), \
                mock.patch.object(app.updater, "confirm_startup") as confirm, \
                mock.patch.object(app.ctypes, "windll", create=True):
            app.main([])
            engine.assert_called_once()
            confirm.assert_not_called()
            self.assertEqual([delay for delay, _fn in callbacks], [app.updater.CONFIRM_AFTER_MS, 2000])
            callbacks[0][1]()
            confirm.assert_called_once_with(Path("fake-install"))

    def test_failed_scene_does_not_arm_confirmation(self):
        from openrecomp import app
        with mock.patch.object(app, "QGuiApplication"), mock.patch.object(app, "Backend"), \
                mock.patch.object(app, "make_engine", side_effect=RuntimeError("fake QML failure")), \
                mock.patch.object(app, "QIcon"), mock.patch.object(app.QTimer, "singleShot") as timer, \
                mock.patch.object(app.ctypes, "windll", create=True):
            with self.assertRaises(RuntimeError):
                app.main([])
            timer.assert_not_called()

    def test_builtins_are_relocatable_and_t4_is_first(self):
        manifests, problems = manifest.load_all([manifest.BUILTIN_DIR])
        self.assertFalse(problems)
        self.assertEqual(manifests[0]["id"], "t4")
        self.assertTrue(all(not item["locations"] for item in manifests))

    def test_user_settings_live_in_override_not_install_or_working_folder(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"OPENRECOMP_HOME": tmp}):
            config = dict(language="ja", roots={"t4": "player-install"}, reduced_motion=True)
            manifest.save_config(config)
            self.assertEqual(manifest.load_config(), config)
            self.assertEqual(json.loads((Path(tmp) / "config.json").read_text()), config)
        with mock.patch.dict(os.environ, {"OPENRECOMP_HOME": "relative-player-data"}):
            self.assertTrue(os.path.isabs(manifest.user_dir()))


if __name__ == "__main__":
    unittest.main()
