"""Search status stays visible and cancellable; no installed code or network."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from openrecomp import i18n
from openrecomp.nav import Game, Nav
from test_online_adapter import Subject
from test_online_nav import Lobby
from test_online_page import lobby_snapshot


class SearchPageTests(unittest.TestCase):
    def setUp(self):
        self.a = Lobby()
        self.a.snapshot.update(lobby_snapshot())
        self.nav = Nav([Game(self.a.m, self.a)], language="en")
        self.nav.screen = "hub"
        self.nav.sec[self.a.m["id"]] = "online"

    def test_search_has_top_banner_timer_cancel_and_changed_buttons(self):
        self.a.snapshot.update(phase="searching", queue="casual", search=dict(elapsed=42),
                               message="@online.searching_casual")
        page = self.nav.view()["online"]
        self.assertEqual(page["layout"], "lobby")
        self.assertTrue(page["search"]["active"])
        self.assertEqual(page["search"]["elapsed"], "0:42")
        self.assertEqual(page["search"]["label"], i18n.text("en", "online.searching_casual"))
        self.assertEqual(page["find"]["quick"]["label"], page["search"]["label"])
        self.assertTrue(page["find"]["quick"]["disabled"])
        self.assertTrue(page["find"]["ranked"]["disabled"])
        cancel = page["search"]["cancel"]
        self.nav.focus[self.nav.key()] = cancel["index"]
        self.nav.act("confirm", device="xbox")
        self.assertIn(("online", "cancel"), self.a.calls)

    def test_cancelling_cannot_submit_again_and_leaves_lobby_on_screen(self):
        self.a.snapshot.update(phase="cancelling", queue="ranked", search=dict(elapsed=73))
        page = self.nav.view()["online"]
        self.assertEqual(page["search"]["elapsed"], "1:13")
        self.assertTrue(page["search"]["cancel"]["disabled"])
        self.assertTrue(all(not item.get("run") for item in self.nav.items()
                            if item.get("id") in ("cancel", "search_casual", "search_ranked", "ranked_strict")))

    def test_failed_start_notice_is_visible_without_a_result_screen(self):
        self.a.snapshot.update(match_failure=dict(message="The match could not start: Rival left.", remaining=3))
        page = self.nav.view()["online"]
        self.assertEqual(page["notice"], "The match could not start: Rival left.")
        self.assertFalse(page["search"]["active"])

    def test_offscreen_search_banner_loads_and_disappears_after_cancel(self):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
        from openrecomp.app import UI_DIR
        from test_ui_loads import FakeBackend, wait_pages
        from test_ui_polish import items as scene_items

        app = QGuiApplication.instance() or QGuiApplication([])
        self.a.snapshot.update(phase="searching", queue="casual", search=dict(elapsed=42))
        backend = FakeBackend(self.nav)
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
        engine.setInitialProperties({"backend": backend, "wantFull": False})
        engine.load(QUrl.fromLocalFile(str(Path(UI_DIR) / "Main.qml")))
        self.assertTrue(engine.rootObjects(), warnings)
        try:
            window = engine.rootObjects()[0]
            window.show()
            wait_pages(window)
            banner = next(item for item in scene_items(window.contentItem())
                          if item.objectName() == "onlineSearchBanner")
            self.assertTrue(banner.property("visible"))
            self.a.snapshot.update(phase="logged_in")
            backend._v = self.nav.view()
            backend.viewChanged.emit()
            app.processEvents()
            self.assertFalse(banner.property("visible"))
            self.assertEqual(warnings, [])
        finally:
            del engine


class SearchSnapshotTests(unittest.TestCase):
    def setUp(self):
        home = Path(__file__).resolve().parents[1] / "build" / "tmp-home" / "search-tests"
        home.mkdir(parents=True, exist_ok=True)
        self.directory = self.enterContext(tempfile.TemporaryDirectory(dir=home))
        self.enterContext(mock.patch.dict(os.environ, T5_ONLINE_DIR=self.directory))
        self.enterContext(mock.patch("openrecomp.adapters.t5_online.game_process_running", return_value=False))
        self.a = Subject(self.directory)
        self.addCleanup(self.a.online_close)
        self.a.online_action("login_guest")
        self.a.online_poll()

    def test_elapsed_uses_monotonic_and_restarts_for_each_search(self):
        with mock.patch("openrecomp.adapters.t5_online.time.monotonic", return_value=100):
            self.a.online_action("search_casual")
            self.a.online_poll()
        with mock.patch("openrecomp.adapters.t5_online.time.monotonic", return_value=142.9):
            self.assertEqual(self.a.online_state()["search"]["elapsed"], 42)
        self.a.online_action("cancel")
        self.a.online_poll()
        with mock.patch("openrecomp.adapters.t5_online.time.monotonic", return_value=300):
            self.a.online_action("search_casual")
            self.assertEqual(self.a.online_state()["search"]["elapsed"], 0)

    def test_queue_reason_requires_authoritative_counts(self):
        self.a.online_action("search_casual")
        self.a.online_poll()
        self.a._online_lobby_snapshot(dict(queue=dict(quick=1, ranked=1)))
        self.assertEqual(self.a.online_state()["search"]["reason"], "")
        self.a._online_me = dict(status="queue")
        self.assertEqual(self.a.online_state()["search"]["reason"], "@online.search_separate_guest")
        self.a._online_account = True
        self.assertEqual(self.a.online_state()["search"]["reason"], "@online.search_separate_queue")
        self.a._online_lobby_snapshot(dict(queue=dict(quick=2, ranked=1)))
        self.assertEqual(self.a.online_state()["search"]["reason"], "")
        self.a._online_lobby_snapshot(dict(queue=dict(quick=True, ranked=-1)))
        self.assertEqual(self.a.online_state()["search"]["queues"], {})

    def test_incompatible_build_reason_survives_as_search_explanation(self):
        self.a.online_action("search_casual")
        self.a.online_poll()
        self.a._online_other_builds = 1
        self.assertEqual(self.a.online_state()["search"]["reason"]["_text"], "online.searching_other_build")


if __name__ == "__main__":
    unittest.main()
