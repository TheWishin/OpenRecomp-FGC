"""Release layout contracts, inspected without creating a launcher window."""
from pathlib import Path
import re
import unittest


UI = Path(__file__).parents[1] / "openrecomp" / "ui"


def named_text(source, name):
    """Named beta text items deliberately keep their properties in one block."""
    return re.search(r'Text\s*\{[^{}]*objectName:\s*"' + name + r'"[^{}]*\}', source).group()


class BetaLayout(unittest.TestCase):
    def test_check_details_keep_all_words_and_grow_their_rows(self):
        source = (UI / "Hub.qml").read_text(encoding="utf-8")
        for name in ("detailTitle", "detailLead", "detailKey", "detailValue"):
            with self.subTest(name=name):
                item = named_text(source, name)
                self.assertIn("wrapMode: Text.Wrap", item)
                self.assertIn("textFormat: Text.PlainText", item)
                self.assertNotIn("elide:", item)
                self.assertNotIn("maximumLineCount:", item)
        self.assertIn("Math.max(detailKey.implicitHeight, detailValue.implicitHeight) + 12", source)

    def test_detail_fits_above_primary_and_hint_at_both_display_scales(self):
        source = (UI / "Hub.qml").read_text(encoding="utf-8")
        self.assertIn("parent.height - y - (hub.d.primary ? 160 : 32)", source)
        self.assertIn("scale: Math.min(1, parent.height / Math.max(1, implicitHeight))", source)
        self.assertIn("transformOrigin: Item.TopLeft", source)
        # The detail area has 788 design pixels after tabs. Content can grow in
        # translation, but its displayed bottom stays clear of the fixed action.
        for display_scale in (1, 2 / 3):
            for primary in (False, True):
                available = 788 - 32 - (160 if primary else 32)
                limit = 788 - (144 if primary else 0)
                for content in (250, 650, 1200):
                    rendered = content * min(1, available / content)
                    self.assertLessEqual((32 + rendered) * display_scale, limit * display_scale)

    def test_keyboard_actions_and_focus_hint_fit_translated_labels(self):
        overlays = (UI / "Overlays.qml").read_text(encoding="utf-8")
        for name in ("oskTitle", "oskKeyLabel"):
            item = named_text(overlays, name)
            self.assertIn("fontSizeMode: Text.Fit", item)
            self.assertIn("width:", item)
            self.assertIn("height:", item)
            self.assertNotIn("elide:", item)
        hint = named_text((UI / "Main.qml").read_text(encoding="utf-8"), "focusHint")
        self.assertIn("wrapMode: Text.Wrap", hint)
        self.assertNotIn("elide:", hint)

        # Measure real wrapped hints at the output floor, rather than requiring shrink-to-fit typography.
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QFontDatabase, QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
        from openrecomp import i18n
        from test_ui_loads import FakeBackend, spin, wait_pages
        from test_ui_polish import items
        from tools import online_shots
        app = QGuiApplication.instance() or QGuiApplication([])
        for font in (UI / "fonts").glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(font))
        nav = online_shots.scene("t4", "arcade_floor", "en")
        backend = FakeBackend(nav)
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
        engine.setInitialProperties(dict(backend=backend, wantFull=False))
        engine.load(QUrl.fromLocalFile(str(UI / "Main.qml")))
        self.assertTrue(engine.rootObjects(), warnings)
        window = engine.rootObjects()[0]
        window.show()
        wait_pages(window)
        try:
            for width, height in online_shots.SIZES:
                window.setWidth(width)
                window.setHeight(height)
                for language in i18n.LANGUAGES:
                    nav.language, nav.text_size = language, 130
                    backend._v = online_shots.snapshot(nav)
                    backend._v["hint"] = i18n.text(language, "t4.account_both_hint")
                    backend.viewChanged.emit()
                    spin(10)
                    label = next(item for item in items(window.contentItem()) if item.objectName() == "focusHint")
                    self.assertLessEqual(label.property("contentHeight"), label.height() + 1)
                    self.assertLessEqual(label.property("contentWidth"), label.width() + 1)
                    self.assertFalse(label.property("truncated"), (language, width))
                    self.assertGreaterEqual(window.property("hintHeight"), label.property("contentHeight") + 8 - 1)
                    self.assertGreaterEqual(label.property("font").pixelSize() * width / 1920, 14 * 1.3 - .5)
            self.assertEqual(warnings, [])
        finally:
            window.setProperty("allowClose", True)
            window.close()

    def test_long_controller_row_names_have_two_lines(self):
        item = named_text((UI / "Hub.qml").read_text(encoding="utf-8"), "hubRowLabel")
        self.assertIn("wrapMode: Text.Wrap", item)
        self.assertIn("maximumLineCount: 2", item)
        self.assertIn("fontSizeMode: Text.Fit", item)
        self.assertNotIn("elide:", item)


if __name__ == "__main__":
    unittest.main()
