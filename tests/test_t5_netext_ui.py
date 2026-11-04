"""New online rows and tags render offscreen with fake state in every catalog."""
import os
from pathlib import Path
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QPointF, QUrl
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from openrecomp import i18n, nav_netext
from openrecomp.app import UI_DIR
from test_t5_netext import fake_page
from test_ui_loads import FakeBackend, spin
from test_ui_polish import items


class NetextScene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])
        for font in (Path(UI_DIR) / "fonts").glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(font))

    def test_tags_options_and_confirmations_in_all_languages(self):
        adapter, nav = fake_page()
        backend = FakeBackend(nav)
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
        engine.setInitialProperties({"backend": backend, "wantFull": False})
        engine.load(QUrl.fromLocalFile(str(Path(UI_DIR) / "Main.qml")))
        self.assertTrue(engine.rootObjects(), warnings)
        win = engine.rootObjects()[0]
        win.show()
        self.measurements = []

        def refresh():
            backend._v = nav.view()
            backend._v["reducedMotion"] = True
            backend.viewChanged.emit()
            spin(1)

        try:
            for width, height in ((1920, 1080), (1280, 720)):
                win.setWidth(width)
                win.setHeight(height)
                for language in i18n.LANGUAGES:
                    nav.language = language
                    for chapter, tag in (("lobby", "EU de"), ("rooms", "SA pt-BR")):
                        nav.click_chapter(chapter)
                        refresh()
                        labels = [child for child in items(win.contentItem())
                                  if child.objectName() == "onlineAreaLanguage" and child.isVisible()]
                        self.assertIn(tag, [child.property("text") for child in labels])
                        for label in labels:
                            self.assertGreaterEqual(label.width(), label.implicitWidth())
                            column = label.parentItem()
                            cell = column.parentItem().parentItem()
                            self.assertLessEqual(column.height(), cell.height())
                    for index, row in enumerate(nav.items()):
                        if row.get("id", "").startswith("netext_") and row.get("region") == "account":
                            nav.focus[nav.key()] = index
                            refresh()
                            self.assertNotIn("fake-password", str(backend._v))
                            focused = next(line for line in backend._v["online"]["body"]["lines"]
                                           if line.get("focused"))
                            body = next(child for child in items(win.contentItem()) if child.objectName() == "onlineBody")
                            label = next(child for child in items(body) if child.isVisible()
                                         and child.property("text") == focused["label"]
                                         and child.property("font").pixelSize() == 20)
                            position = label.mapToItem(body, QPointF(0, 0))
                            self.assertGreaterEqual(position.y(), 0)
                            self.assertLessEqual(position.y() + label.height(), body.height())
                            self.assertLessEqual(label.implicitWidth(), label.width())
                            self.measurements.append(dict(language=language, width=width, row=row["id"],
                                                          label_width=label.implicitWidth(), available=label.width()))
                    adapter.snapshot["forget_counts"] = dict(matches=12, sets=4, friends=2)
                    for operation in ("netext_forget_preview", "netext_forget_confirm"):
                        nav_netext.ask(nav, nav.game, operation)
                        refresh()
                        self.assertTrue(backend._v["dialog"]["options"][0]["focused"])
                        text = backend._v["dialog"]["text"]
                        self.assertNotIn("{", text)
                        label = next(child for child in items(win.contentItem())
                                     if child.isVisible() and child.property("text") == text)
                        panel = label.parentItem().parentItem()
                        self.assertGreaterEqual(panel.y(), 0)
                        self.assertLessEqual(panel.y() + panel.height(), 972)
                        self.measurements.append(dict(language=language, width=width, dialog=operation,
                                                      top=panel.y(), height=panel.height()))
                        nav.act("back", device="xbox")
                    adapter.snapshot["forget_counts"] = None
            self.assertEqual(warnings, [])
            self.assertFalse(any(call == ("online", "netext_forget_confirm") for call in adapter.calls))
        finally:
            win.close()
            del engine


if __name__ == "__main__":
    unittest.main()
