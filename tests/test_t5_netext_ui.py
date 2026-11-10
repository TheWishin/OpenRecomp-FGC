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
from test_ui_loads import FakeBackend, spin, wait_pages
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
            wait_pages(win)
            spin(40)  # Repeater layout and its deferred controller-focus reveal complete on the next frame.

        try:
            for width, height in ((1920, 1080), (1280, 720)):
                win.setWidth(width)
                win.setHeight(height)
                for language in i18n.LANGUAGES:
                    nav.language = language
                    for chapter, tag in (("lobby", "EU de"), ("rooms", "SA pt-BR")):
                        nav.click_chapter(chapter)
                        refresh()
                        if chapter == "lobby":
                            # The compact table preserves area/language in its accessible player summary.
                            summaries = [child for child in items(win.contentItem())
                                         if child.isVisible() and tag in (child.property("name") or "")]
                            self.assertTrue(summaries, (chapter, tag))
                            continue
                        labels = [child for child in items(win.contentItem())
                                  if child.objectName() in ("onlineAreaLanguage", "arcadePlayerStatus")
                                  and child.isVisible() and tag in (child.property("text") or "")]
                        self.assertTrue(labels, (chapter, tag))
                        for label in labels:
                            self.assertGreaterEqual(label.width(), label.implicitWidth())
                            container = label.parentItem()
                            while container and container.objectName() not in ("arcadePlayer", "arcadeRoom"):
                                container = container.parentItem()
                            if container is None:
                                column = label.parentItem()
                                container = column.parentItem()
                                self.assertLessEqual(column.height(), container.height())
                            position = label.mapToItem(container, QPointF(0, 0))
                            self.assertGreaterEqual(position.x(), 0)
                            self.assertGreaterEqual(position.y(), 0)
                            self.assertLessEqual(position.x() + label.width(), container.width())
                            self.assertLessEqual(position.y() + label.height(), container.height() + .5)
                    nav.click_chapter("lobby")
                    nav.focus[nav.key()] = next(index for index, row in enumerate(nav.items())
                                              if row.get("id") == "arcade_options")
                    nav.act("confirm", device="xbox")
                    refresh()
                    self.assertTrue(backend._v["online"]["arcade"]["optionsOpen"])
                    shortcut = next(button for button in backend._v["online"]["arcade"]["options"]
                                    if button["id"] == "netext_options")
                    nav.focus[nav.key()] = shortcut["index"]
                    refresh()
                    drawer = next(child for child in items(win.contentItem())
                                  if child.objectName() == "arcadeOptionsDrawer" and child.isVisible())
                    label = next(child for child in items(drawer) if child.isVisible()
                                 and child.property("text") == shortcut["label"]
                                 and child.objectName() == "onlineFieldLabel")
                    position = label.mapToItem(drawer, QPointF(0, 0))
                    self.assertGreaterEqual(position.x(), 0)
                    self.assertGreaterEqual(position.y(), 0)
                    self.assertLessEqual(position.x() + label.width(), drawer.width())
                    self.assertLessEqual(position.y() + label.height(), drawer.height())
                    self.assertLessEqual(label.property("contentHeight"), label.height() + 1)
                    nav.act("confirm", device="xbox")
                    refresh()
                    self.assertEqual(backend._v["online"]["chapter"], "profile")      # Account sits under Profile (0.1.7)
                    self.assertEqual(nav.items()[nav.focus_index(nav.items())]["id"], "netext_max_ping")
                    for index, row in enumerate(nav.items()):
                        if row.get("id", "").startswith("netext_") and row.get("origin") == "account":
                            nav.focus[nav.key()] = index
                            refresh()
                            self.assertNotIn("fake-password", str(backend._v))
                            focused = next(line for line in backend._v["online"]["body"]["lines"]
                                           if line.get("focused"))
                            body = next(child for child in items(win.contentItem()) if child.objectName() == "onlineBody")
                            label = next(child for child in items(body) if child.isVisible()
                                         and child.property("text") == focused["label"]
                                         and child.objectName() == "onlineFieldLabel")
                            position = label.mapToItem(body, QPointF(0, 0))
                            self.assertGreaterEqual(position.y(), 0)
                            self.assertLessEqual(position.y() + label.height(), body.height())
                            self.assertLessEqual(label.property("contentHeight"), label.height() + 1)
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
                    nav.click_chapter("lobby")
                    if nav.view()["online"]["arcade"]["optionsOpen"]:
                        nav.act("back", device="xbox")
                        refresh()
                    self.assertFalse(nav.view()["online"]["arcade"]["optionsOpen"])
            self.assertEqual(warnings, [])
            self.assertFalse(any(call == ("online", "netext_forget_confirm") for call in adapter.calls))
        finally:
            win.close()
            del engine


if __name__ == "__main__":
    unittest.main()
