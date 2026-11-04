"""Launcher display preferences, readable theme pairs and shared assistive controls."""
from pathlib import Path
import re
from types import SimpleNamespace
import unittest

from openrecomp import i18n
from openrecomp.nav import Game, Nav
from test_nav import Fake, manifest


ROOT = Path(__file__).resolve().parents[1]


def luminance(colour):
    values = [int(colour[n:n + 2], 16) / 255 for n in (1, 3, 5)]
    linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in values]
    return sum(a * b for a, b in zip(linear, (.2126, .7152, .0722)))


def contrast(a, b):
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + .05) / (low + .05)


class DisplayPreferences(unittest.TestCase):
    def setUp(self):
        adapter = Fake(manifest("a"))
        self.saved = []
        self.preferences = []
        self.nav = Nav([Game(adapter.m, adapter)], language="en",
                       on_accessibility=lambda *v: self.saved.append(v),
                       on_preferences=lambda *v: self.preferences.append(v))
        self.nav.screen = "hub"
        self.nav.sec["a"] = "settings"

    def test_display_rows_apply_to_the_whole_view_and_save(self):
        rows = {row.get("id"): row for row in self.nav.items()}
        size = rows["text_size"]
        self.assertEqual(size["settingsGroup"], "display")
        self.assertEqual([v for v, _ in size["options"]], [100, 115, 130])
        for percent in (115, 130, 100):
            size["set"](percent)
            self.assertEqual(self.nav.view()["textScale"], percent / 100)
            self.assertEqual(self.saved[-1], (percent, False))
        rows["high_contrast"]["set"](True)
        self.assertTrue(self.nav.view()["highContrast"])
        self.assertEqual(self.saved[-1], (100, True))
        rows["reduced_motion"]["set"](True)
        self.assertTrue(self.nav.view()["reducedMotion"])
        self.assertEqual(self.preferences[-1], (True, True))

    def test_saved_preferences_are_restored_and_invalid_sizes_use_normal(self):
        adapter = self.nav.game.a
        for value, expected in ((115, 1.15), (130, 1.3), (999, 1), (True, 1), ("large", 1)):
            nav = Nav([Game(adapter.m, adapter)], text_size=value, high_contrast=True)
            self.assertEqual(nav.view()["textScale"], expected)
            self.assertTrue(nav.view()["highContrast"])

    def test_backend_persists_display_choices(self):
        from openrecomp.app import Backend
        saved = []
        owner = SimpleNamespace(config={}, _save_config=lambda: saved.append(True))
        Backend._save_accessibility(owner, 130, True)
        self.assertEqual(owner.config, {"text_size": 130, "high_contrast": True})
        self.assertEqual(saved, [True])

    def test_every_catalog_names_all_display_choices(self):
        keys = ("text_size", "text_size_hint", "normal", "large", "larger", "high_contrast", "high_contrast_hint")
        import json
        for language in i18n.LANGUAGES:
            catalogue = json.loads((ROOT / "openrecomp/i18n" / (language + ".json")).read_text(encoding="utf-8"))
            for key in keys:
                text = catalogue["accessibility." + key]
                self.assertTrue(text.strip())
                self.assertNotIn("??", text, (language, key))


class ReadableTheme(unittest.TestCase):
    def test_every_theme_text_colour_meets_wcag_aa_on_its_surfaces(self):
        import os
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlExpression, qmlContext
        app = QGuiApplication.instance() or QGuiApplication([])
        engine = QQmlEngine()
        component = QQmlComponent(engine)
        component.setData(b'import QtQuick\nimport "."\nQtObject { property var theme: Theme }',
                          QUrl.fromLocalFile(str(ROOT / "openrecomp/ui/ThemeProbe.qml")))
        probe = component.create()
        self.assertIsNotNone(probe, [error.toString() for error in component.errors()])
        theme = probe.property("theme")
        pairs = [(text, surface) for text in ("text", "muted", "value", "error", "success")
                 for surface in ("ground", "card", "raised", "highlighted")]
        pairs += [("ground", "selected"), ("inkHelp", "selected"), ("focus", "ground")]
        for game in ("", "t5dr", "t4"):
            theme.setProperty("gameKind", game)
            for high_contrast in (False, True):
                theme.setProperty("highContrast", high_contrast)
                for text, surface in pairs:
                    with self.subTest(game=game, text=text, surface=surface, high_contrast=high_contrast):
                        self.assertGreaterEqual(contrast(theme.property(text).name(), theme.property(surface).name()), 4.5)
                expression = QQmlExpression(qmlContext(probe), probe, "Theme.readableAccent(Theme.gameAccent)")
                accent, undefined = expression.evaluate()
                self.assertFalse(undefined, expression.error().toString())
                for surface in ("ground", "card", "raised", "highlighted"):
                    with self.subTest(game=game, text="readableAccent", surface=surface, high_contrast=high_contrast):
                        self.assertGreaterEqual(contrast(accent.name(), theme.property(surface).name()), 4.5)
                self.assertGreaterEqual(contrast(theme.property("ground").name(), accent.name()), 4.5)
        del probe
        del engine

    def test_all_text_sizes_use_the_shared_scale_and_floor(self):
        for path in (ROOT / "openrecomp/ui").glob("*.qml"):
            source = path.read_text(encoding="utf-8")
            for line in source.splitlines():
                for expression in re.findall(r"\bfont\.pixelSize:\s*([^;\n}]+)", line):
                    self.assertRegex(expression, r"Theme\.(px|onlinePx)\(", (path.name, expression))

    def test_shared_interaction_exposes_names_roles_and_noncolour_focus(self):
        source = (ROOT / "openrecomp/ui/Interaction.qml").read_text(encoding="utf-8")
        for feature in ("Accessible.name:", "Accessible.role:", "Accessible.onPressAction:",
                        "HoverHandler", "handler.pressed", "Theme.focusWidth"):
            self.assertIn(feature, source)
        self.assertIn('color: "transparent"', source)
        self.assertIn("Theme.focusWidth + 2", source)
        style = (ROOT / "openrecomp/ui/OnlineStyle.qml").read_text(encoding="utf-8")
        self.assertIn("role: Accessible.ListItem", (ROOT / "openrecomp/ui/OnlineTable.qml").read_text(encoding="utf-8"))
        self.assertIn('receipt.kind === "error"', (ROOT / "openrecomp/ui/ActionReceipt.qml").read_text(encoding="utf-8"))


class DisplayScene(unittest.TestCase):
    from test_ui_polish import ScenePolish
    setUpClass = classmethod(ScenePolish.setUpClass.__func__)
    setUp = ScenePolish.setUp
    tearDown = ScenePolish.tearDown
    named = ScenePolish.named
    wait_pages = ScenePolish.wait_pages
    publish = ScenePolish.publish

    def test_shared_type_and_target_floors_are_measured_in_output_pixels(self):
        from PySide6.QtQml import QQmlExpression, qmlContext
        from test_ui_loads import spin
        for width, height in ((1920, 1080), (1280, 720), (960, 540)):
            self.win.setWidth(width)
            self.win.setHeight(height)
            spin()
            for percent in (100, 115, 130):
                self.nav.text_size = percent
                self.publish()
                for size, floor in ((16, 16), (18, 18), (22, 18), (28, 22), (40, 28)):
                    expression = QQmlExpression(qmlContext(self.win), self.win,
                                               f"Theme.px({size}) * Theme.viewportScale")
                    result, undefined = expression.evaluate()
                    self.assertFalse(undefined, expression.error().toString())
                    self.assertGreaterEqual(result, floor * percent / 100 - .5)
                for size in (14, 18, 22, 28):
                    expression = QQmlExpression(qmlContext(self.win), self.win,
                                               f"Theme.onlinePx({size}) * Theme.viewportScale")
                    result, undefined = expression.evaluate()
                    self.assertFalse(undefined, expression.error().toString())
                    expected = max(size * width / 1920, 14) * percent / 100
                    self.assertAlmostEqual(result, expected, delta=.5)
                expression = QQmlExpression(qmlContext(self.win), self.win,
                                           "Theme.target(44) * Theme.viewportScale")
                result, undefined = expression.evaluate()
                self.assertFalse(undefined)
                self.assertGreaterEqual(result, 44)

    def test_game_and_custom_accents_remain_readable_on_raised_surfaces(self):
        import json
        from PySide6.QtQml import QQmlExpression, qmlContext
        accents = [json.loads(path.read_text(encoding="utf-8"))["accent"]
                   for path in (ROOT / "games").glob("*.json")]
        for colour in accents + ["#000000", "#101F30", "#FFFFFF"]:
            expression = QQmlExpression(qmlContext(self.win), self.win,
                                       'Theme.readableAccent("' + colour + '")')
            result, undefined = expression.evaluate()
            self.assertFalse(undefined, expression.error().toString())
            with self.subTest(colour=colour):
                self.assertGreaterEqual(contrast(result.name(), "#303640"), 4.5)
                self.assertGreaterEqual(contrast(result.name(), "#0E0F11"), 4.5)

    def test_larger_brand_and_long_footer_hint_fit_without_clipping(self):
        from test_ui_loads import spin
        self.nav.text_size = 130
        self.publish()
        brand = self.named("brandFallback")[0]
        self.assertLessEqual(brand.property("contentWidth"), brand.width())
        self.backend._v["hint"] = i18n.text("de", "t4.account_both_hint")
        self.backend.viewChanged.emit()
        spin()
        hint = self.named("focusHint")[0]
        self.assertLessEqual(hint.property("contentHeight"), hint.height())

    def test_saved_scale_and_high_contrast_reach_visible_text_and_focus_ring(self):
        from PySide6.QtQml import QQmlProperty, qmlContext
        label = self.named("brandFallback")[0]
        base_size = label.property("font").pixelSize()
        self.nav.text_size = 130
        self.nav.high_contrast = True
        self.publish()
        self.assertEqual(label.property("font").pixelSize(), round(base_size * 1.3))
        self.assertEqual(self.win.property("textC").name(), "#ffffff")
        rings = [item for item in self.named("focusRing") if item.isVisible()]
        self.assertTrue(rings)
        self.assertTrue(any(QQmlProperty(item, "border.width").read() == 5 for item in rings))
        targets = [item for item in self.named("accessibleTarget") if item.isVisible()]
        self.assertTrue(any(QQmlProperty(item, "Accessible.name", qmlContext(item)).read() for item in targets))


if __name__ == "__main__":
    unittest.main()
