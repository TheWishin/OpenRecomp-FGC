"""Fake online match and social scenes fit the controller viewport offscreen."""
import os
from pathlib import Path
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from openrecomp import i18n
from openrecomp.app import UI_DIR
from openrecomp.nav import Game, Nav
from test_social_nav import SocialLobby
from test_ui_loads import FakeBackend, spin
from test_ui_polish import items


class OnlineMatchSocialScene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])
        for font in (Path(UI_DIR) / "fonts").glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(font))

    def test_match_and_social_details_fit_in_every_language(self):
        adapter = SocialLobby()
        adapter.snapshot["capabilities"].update(match_flow=True, rematch=True)
        adapter.snapshot.update(name="Player", account=True, rank="Checked rank",
                                match=dict(opponent="Opponent" * 8, ping=42))
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
        win = engine.rootObjects()[0]
        win.show()
        try:
            for language in i18n.LANGUAGES:
                nav.language = language
                for phase in ("matched", "starting", "playing", "result", "result_sent", "logged_in"):
                    adapter.snapshot["phase"] = phase
                    adapter.snapshot["message"] = "@online.ready_hint" if phase != "logged_in" else "@online.friends_hint"
                    for index, item in enumerate(nav.items()):
                        if item.get("kind") == "heading":
                            continue
                        with self.subTest(language=language, phase=phase, item=item.get("id")):
                            nav.focus[nav.key()] = index
                            backend._v = nav.view()
                            backend._v["reducedMotion"] = True
                            backend.viewChanged.emit()
                            spin(1)
                            scene_items = list(items(win.contentItem()))
                            area = next(child for child in scene_items if child.objectName() == "hubList")
                            content = next(child for child in scene_items if child.objectName() == "detailContent")
                            self.assertLessEqual(content.y() + content.height(), content.parentItem().height())
                            for row in (child for child in scene_items if child.objectName() == "hubRow"):
                                self.assertLessEqual(row.y() + row.height() + row.parentItem().y(), area.height() + 1)
                            for label in (child for child in scene_items if child.objectName() == "hubRowLabel"):
                                self.assertGreater(label.width(), 0)
            self.assertEqual(adapter.calls, [])
            self.assertEqual(warnings, [])
        finally:
            del engine


if __name__ == "__main__":
    unittest.main()
