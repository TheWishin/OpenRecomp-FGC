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
        self.api.prepare_update.return_value = Path("fake-plan")
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
        self.api.prepare_update.assert_called_once_with(Path("fake-install"), Path("fake-stage"))
        self.api.launch_update.assert_called_once_with(Path("fake-install"), Path("fake-plan"))
        self.quit.assert_called_once()

    def test_busy_still_downloads_but_defers_the_helper_until_the_activity_ends(self):
        self.offer()
        self.busy = True
        self.assertTrue(self.service.install())          # the download needs no closed game; only the restart does
        self.service.poll()
        self.api.stage_update.assert_called_once()
        self.api.launch_update.assert_not_called()
        self.assertEqual(self.service.state["phase"], "waiting")
        self.busy = False
        self.service.poll()
        self.api.launch_update.assert_called_once()

    def test_busy_defers_helper_when_activity_starts_during_download(self):
        self.offer()
        self.assertTrue(self.service.install())
        self.busy = True
        self.service.poll()
        self.api.launch_update.assert_not_called()
        self.busy = False
        self.service.poll()
        self.api.launch_update.assert_called_once()

    def test_failed_stage_or_helper_keeps_launcher_open(self):
        for operation in ("stage_update", "prepare_update", "launch_update"):
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
            # no loud update check of its own: the quiet one runs with the game checks
            self.assertEqual([delay for delay, _fn in callbacks], [app.updater.CONFIRM_AFTER_MS])
            callbacks[0][1]()
            confirm.assert_called_once_with(Path("fake-install"))

    def test_automatic_check_at_start_is_quiet(self):
        """The start's check (with the game checks) says nothing when the launcher is up to date."""
        from openrecomp import app, app_game_setup
        updates = SimpleNamespace(state=dict(phase="idle"), quiet=False, poll=lambda: False)
        updates.check = mock.Mock(side_effect=lambda quiet=False: (setattr(updates, "quiet", quiet),
                                                                  updates.state.update(phase="current")))
        said = []
        backend = SimpleNamespace(updates=updates, _update_busy=lambda: False, _update_phase="idle",
                                  _offered_update=False,
                                  nav=SimpleNamespace(update_state={}, say=lambda *a: said.append(a)))
        backend._auto_check_updates = lambda: app.Backend._auto_check_updates(backend)
        backend._auto_check_updates()
        updates.check.assert_called_once_with(quiet=True)
        self.assertTrue(app.Backend._poll_updates(backend))
        self.assertEqual(said, [])
        self.assertGreater(app_game_setup.FIRST_CHECK_SECONDS, 0)
        app.Backend._check_updates(backend)                 # Quick access: the player asked, so it answers
        updates.state["phase"] = "checking"
        app.Backend._poll_updates(backend)
        updates.state["phase"] = "current"
        app.Backend._poll_updates(backend)
        self.assertEqual(said, [("@updates.current", 8)])

    def test_automatic_check_waits_for_the_games_check_started_with_it(self):
        """The games' check starts at the same moment and counts as busy: the launcher's check runs right after it."""
        from openrecomp import app
        updates = SimpleNamespace(state=dict(phase="idle"), quiet=False, poll=lambda: False)
        updates.check = mock.Mock(side_effect=lambda quiet=False: setattr(updates, "quiet", quiet))
        busy = [True]
        said = []
        backend = SimpleNamespace(updates=updates, _update_busy=lambda: busy[0], _update_phase="idle",
                                  _offered_update=False,
                                  nav=SimpleNamespace(update_state={}, say=lambda *a: said.append(a)))
        backend._auto_check_updates = lambda: app.Backend._auto_check_updates(backend)
        backend._auto_check_updates()
        app.Backend._poll_updates(backend)
        updates.check.assert_not_called()
        busy[0] = False
        app.Backend._poll_updates(backend)
        updates.check.assert_called_once_with(quiet=True)
        app.Backend._poll_updates(backend)
        updates.check.assert_called_once_with(quiet=True)       # once, not on every tick
        updates.state["phase"] = "current"
        app.Backend._poll_updates(backend)
        self.assertEqual(said, [])

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



class TestVersionAndUpdateAllTests(unittest.TestCase):
    """0.1.4: "up to date -- test version X available" and Update all (install a launcher at or above X)."""

    class Api:
        def __init__(self):
            self.staged = []

        def check_release(self, root, prereleases=False):
            return None

        def release_offers(self, root):
            return None, dict(version="v0.1.4", notes="test", size=5, test=True)

        def release_for(self, root, minimum):
            return dict(version="v0.1.4", size=5, test=True) if minimum == "0.1.4" else None

        def stage_update(self, root, release, **_kw):
            self.staged.append(release["version"])
            return "staged"

        def prepare_update(self, root, staged):
            return "prepared"

        def launch_update(self, root, prepared):
            pass

    def service(self, api):
        from openrecomp.update_service import UpdateService
        return UpdateService(root=".", api=api, worker=lambda fn: fn(), quit=lambda: None)

    def test_current_names_a_newer_test_version_and_take_test_offers_it(self):
        s = self.service(self.Api())
        s.check()
        s.poll()
        self.assertEqual(s.state["phase"], "current")
        self.assertEqual(s.state["test_version"], "v0.1.4")
        self.assertTrue(s.take_test())
        self.assertEqual((s.state["phase"], s.state["version"]), ("available", "v0.1.4"))

    def test_install_for_installs_the_needed_version_without_a_question(self):
        api = self.Api()
        s = self.service(api)
        self.assertTrue(s.install_for("0.1.4"))
        s.poll()
        self.assertEqual(api.staged, ["v0.1.4"])

    def test_install_for_reports_an_error_when_no_release_is_new_enough(self):
        s = self.service(self.Api())
        self.assertTrue(s.install_for("0.1.5"))
        s.poll()
        self.assertEqual(s.state["phase"], "error")
