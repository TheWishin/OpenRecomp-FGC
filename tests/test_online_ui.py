"""The online screens rendered offscreen with fake state and no installed game."""
import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from openrecomp import i18n
from openrecomp.app import UI_DIR
from openrecomp.nav import Game, Nav
from test_nav import Fake, manifest
from test_ui_loads import FakeBackend, spin


class OnlineScene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])
        for font in (Path(UI_DIR) / "fonts").glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(font))

    def test_online_states_and_password_keyboard_in_every_language(self):
        adapter = Fake(manifest())
        state = dict(phase="offline", message="@online.offline", name="Player", account=False,
                     queue="", match={}, saved_available=True)
        adapter.online_supported = lambda: True
        adapter.online_state = lambda: dict(state)
        adapter.text_value = lambda tid: "aA !" if tid == "online_password" else "Player"
        nav = Nav([Game(adapter.m, adapter)], language="en")
        nav.dry = True
        nav.screen = "hub"
        nav.sec[nav.game.id] = "online"
        backend = FakeBackend(nav)
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
        engine.setInitialProperties({"backend": backend, "wantFull": False})
        engine.load(QUrl.fromLocalFile(str(Path(UI_DIR) / "Main.qml")))
        self.assertTrue(engine.rootObjects(), warnings)
        try:
            for language in i18n.LANGUAGES:
                nav.language = language
                for phase, message in (("offline", "online.offline"), ("connecting", "online.connecting"),
                                       ("logged_in", "online.logged_in"), ("searching", "online.searching_casual"),
                                       ("cancelling", "online.cancelling"), ("kicked", "online.kicked"),
                                       ("error", "online.unavailable"), ("matched", "online.matched")):
                    with self.subTest(language=language, phase=phase):
                        state.update(phase=phase, message="@" + message,
                                     match=dict(opponent="Other player", ping=42) if phase == "matched" else {})
                        backend._v = nav.view()
                        backend.viewChanged.emit()
                        spin(1)
                        title = "online.match_found" if phase == "matched" else "online.status"
                        self.assertEqual(backend._v["detail"]["title"], i18n.text(language, title))
                        self.assertEqual(backend._v["hint"], i18n.text(language, message))
                nav._open_osk("online_password")
                for _page in range(3):
                    backend._v = nav.view()
                    backend.viewChanged.emit()
                    spin(1)
                    self.assertEqual(backend._v["osk"]["text"], "••••_")
                    nav.act("social")
                nav.act("back")
            self.assertEqual(warnings, [])
            self.assertEqual(adapter.calls, [])
        finally:
            del engine


if __name__ == "__main__":
    unittest.main()
