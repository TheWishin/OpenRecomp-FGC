"""Launcher performance contracts, with fake adapters and offscreen QML only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

from PySide6.QtCore import QObject, QUrl, Qt
from PySide6.QtGui import QGuiApplication, QWindow
from PySide6.QtQml import QQmlApplicationEngine

from openrecomp import app
from openrecomp.nav import Game, Nav
from openrecomp.pad import Pads
from test_nav import Fake, manifest
from test_online_nav import Lobby
from test_online_page import lobby_snapshot
from test_ui_loads import FakeBackend, spin


class LauncherPerf(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gui = QGuiApplication.instance() or QGuiApplication([])

    def backend(self):
        adapter = Fake(manifest())
        with mock.patch.object(app.mf, "load_config", return_value={}), \
                mock.patch.object(app, "load_games", return_value=([Game(adapter.m, adapter)], [])), \
                mock.patch.object(app.Backend, "_load_pads", lambda b, games: setattr(b, "pads", Pads([]))), \
                mock.patch.dict(os.environ, OPENRECOMP_NO_GAME_CHECKS="1", OPENRECOMP_STALL_LOG=""):
            backend = app.Backend(windowed=True)
        self.addCleanup(backend.timer.stop)
        self.addCleanup(backend._background_timer.stop)
        self.addCleanup(backend._save_timer.stop)
        return backend, adapter

    def test_network_and_library_modules_wait_until_needed(self):
        result = subprocess.run([sys.executable, "-c", "import sys, json; from openrecomp import app; "
                                 "print(json.dumps(sorted(sys.modules)))"],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        loaded = json.loads(result.stdout)
        for module in ("urllib.request", "openrecomp.game_library", "openrecomp.game_updates",
                       "openrecomp.game_releases", "openrecomp.game_setup"):
            self.assertNotIn(module, loaded)

    def test_release_inventory_includes_the_lazy_loader(self):
        from tools.package_release import SOURCE_GROUPS
        self.assertIn("PageLoader.qml", SOURCE_GROUPS["openrecomp/ui"])

    def test_lazy_services_are_created_once_and_setup_poll_stays_lazy(self):
        backend, _ = self.backend()
        self.assertIsNone(backend._library)
        self.assertIsNone(backend._setup)
        backend._poll_setup(1)
        self.assertIsNone(backend._setup)
        self.assertIs(backend.library, backend.library)
        self.assertIs(backend.setup, backend.setup)

    def test_preferences_are_coalesced_and_quit_flushes_pending_changes(self):
        backend, _ = self.backend()
        with mock.patch.object(app.mf, "save_config") as save:
            for gid in ("a", "b", "c"):
                backend._save_game(gid)
            save.assert_not_called()
            spin(260)
            save.assert_called_once_with(backend.config)
            self.assertEqual(backend.config["last_game"], "c")
            backend._save_language("de")
            with mock.patch.object(app.QGuiApplication, "quit"):
                backend._quit()
            self.assertEqual(save.call_count, 2)
            self.assertFalse(backend._save_timer.isActive())

    def test_failed_deferred_save_is_visible(self):
        backend, _ = self.backend()
        with mock.patch.object(app.mf, "save_config", side_effect=OSError):
            backend._save_game("b")
            backend._flush_config()
        self.assertTrue(backend.view["toast"])

    def test_unchanged_view_neither_stats_logo_nor_notifies_qml(self):
        backend, _ = self.backend()
        signals = []
        backend.viewChanged.connect(lambda: signals.append(True))
        with mock.patch.object(app.os.path, "isfile", side_effect=AssertionError("redraw read the disk")):
            backend.refresh()
            backend.refresh()
        self.assertEqual(signals, [])
        backend.nav.act("confirm", device="xbox")
        backend.refresh()
        self.assertEqual(signals, [True])

    def test_model_polls_are_coalesced_but_pad_input_remains_fast(self):
        backend, _ = self.backend()
        with mock.patch.object(backend.nav, "tick", return_value=False) as tick, \
                mock.patch.object(backend.pads, "poll", return_value=[]) as poll:
            for _ in range(7):
                backend._tick()
        self.assertEqual(tick.call_count, 1)
        self.assertEqual(poll.call_count, 7)

    def test_hidden_minimized_and_running_suspend_fast_polling(self):
        backend, adapter = self.backend()
        backend.window = QWindow()
        self.addCleanup(backend.window.hide)
        backend._sync_timers()
        self.assertFalse(backend.timer.isActive())
        self.assertTrue(backend._background_timer.isActive())
        with mock.patch.object(backend.pads, "poll") as poll:
            backend._background_tick()
            poll.assert_not_called()
        backend.window.show()
        backend._sync_timers()
        self.assertTrue(backend.timer.isActive())
        backend.window.setWindowState(Qt.WindowMinimized)
        backend._sync_timers()
        self.assertFalse(backend.timer.isActive())
        backend.window.setWindowState(Qt.WindowNoState)
        adapter.is_running = True
        backend._sync_timers()
        self.assertFalse(backend.timer.isActive())
        # T4's existing controller return chord remains available while its game runs.
        adapter.m["adapter"] = "t4"
        backend._sync_timers()
        self.assertTrue(backend.timer.isActive())

    def test_idle_pad_ticks_use_cached_window_state(self):
        backend, _ = self.backend()
        backend.window = mock.Mock()
        backend.window.isVisible.return_value = True
        backend.window.windowState.return_value = Qt.WindowNoState
        backend.window.isActive.return_value = True
        backend._sync_timers()
        backend.window.isActive.side_effect = AssertionError("Qt queried on every pad tick")
        backend.window.windowState.side_effect = AssertionError("Qt queried on every pad tick")
        for _ in range(10):
            self.assertTrue(backend._in_front())
        backend.window.isVisible.return_value = False
        backend._sync_timers()
        self.assertFalse(backend._in_front())

    def test_background_maintenance_keeps_tiles_within_five_seconds(self):
        backend, _ = self.backend()
        backend.window = QWindow()
        with mock.patch.object(backend, "_slow_changes", return_value=False) as reconcile:
            backend._background_tick()
            reconcile.assert_not_called()
            backend._background_tick()
            reconcile.assert_called_once_with(False)

    def test_pad_reaches_lazy_pages_and_inactive_items_are_destroyed(self):
        lobby = Lobby()
        lobby.snapshot.update(lobby_snapshot())
        lobby.controls_supported = lambda: True
        lobby.support_available = lambda: True
        nav = Nav([Game(lobby.m, lobby)], language="en")
        backend = FakeBackend(nav)
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
        engine.setInitialProperties({"backend": backend, "wantFull": False})
        engine.load(QUrl.fromLocalFile(str(Path(app.UI_DIR) / "Main.qml")))
        self.assertTrue(engine.rootObjects(), warnings)
        window = engine.rootObjects()[0]
        window.show()
        self.addCleanup(lambda engine=engine: window.hide())

        def settle():
            for _ in range(200):
                spin(5)
                loaders = window.findChildren(QObject, "pageLoader")
                if all(not p.property("active") or p.property("progress") == 1
                       and p.property("item") is not None for p in loaders):
                    break
            else:
                self.fail("A lazy page did not become ready")
            for p in loaders:
                if not p.property("active"):
                    self.assertIsNone(p.property("item"))

        def press(action):
            nav.act(action, device="xbox")
            nav.release(action)
            backend._v = nav.view()
            backend.viewChanged.emit()
            settle()

        settle()
        self.assertEqual(len(window.findChildren(QObject, "pageLoader")), 3)
        press("confirm")
        visited = set()
        for _ in nav.sections():
            visited.add(nav.section())
            if nav.section() == "online":
                self.assertIsNotNone(window.findChild(QObject, "onlineHub"))
                for phase, name in (("offline", "onlineLoginPage"), ("connecting", "onlineCardPage"),
                                    ("logged_in", "onlineHub")):
                    lobby.snapshot["phase"] = phase
                    backend._v = nav.view()
                    backend.viewChanged.emit()
                    settle()
                    self.assertIsNotNone(window.findChild(QObject, name))
            if nav.section() == "build":
                self.assertIsNotNone(window.findChild(QObject, "buildPage"))
            if nav.section() == "settings":
                self.assertIsNotNone(window.findChild(QObject, "settingsHub"))
            press("next")
        self.assertEqual(visited, set(nav.sections()))
        press("social")
        self.assertIsNotNone(window.findChild(QObject, "overlayMask"))
        press("back")
        self.assertIsNone(window.findChild(QObject, "overlayMask"))
        press("back")
        self.assertEqual(nav.screen, "start")
        self.assertEqual(warnings, [])
