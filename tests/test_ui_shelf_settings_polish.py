"""Fake-only shelf and Settings card geometry at both supported display sizes."""
import unittest

from PySide6.QtCore import QPointF

from openrecomp import i18n
import test_ui_polish
from test_ui_loads import spin


class ShelfSettingsPolish(unittest.TestCase):
    setUpClass = classmethod(test_ui_polish.ScenePolish.setUpClass.__func__)
    setUp = test_ui_polish.ScenePolish.setUp
    tearDown = test_ui_polish.ScenePolish.tearDown
    named = test_ui_polish.ScenePolish.named
    wait_pages = test_ui_polish.ScenePolish.wait_pages
    publish = test_ui_polish.ScenePolish.publish

    def test_fallback_brand_has_no_blank_wordmark_space(self):
        self.publish()
        brand = self.named("brandFallback")[0]
        self.assertTrue(brand.isVisible())
        self.assertAlmostEqual(brand.mapToScene(QPointF()).x(), 48)

    def test_all_section_tab_names_fit_in_every_catalog(self):
        self.adapter.controls_supported = lambda: True
        self.adapter.support_available = lambda: True
        self.nav.screen = "hub"
        for language in i18n.LANGUAGES:
            self.nav.language = language
            self.publish()
            for width, height in ((1920, 1080), (1280, 720)):
                self.win.setWidth(width)
                self.win.setHeight(height)
                spin()
                labels = self.named("sectionTabLabel")
                self.assertEqual(len(labels), 7)
                for label in labels:
                    with self.subTest(language=language, size=(width, height), text=label.property("text")):
                        self.assertFalse(label.property("truncated"))
                        self.assertLessEqual(label.property("contentWidth"), label.width() + 1)
                        self.assertLessEqual(label.property("contentHeight"), label.height() + 1)

    def test_shelf_uses_an_inset_card_and_distinct_status(self):
        for language in i18n.LANGUAGES:
            self.nav.language = language
            self.publish()
            for width, height in ((1920, 1080), (1280, 720)):
                with self.subTest(language=language, size=(width, height)):
                    self.win.setWidth(width)
                    self.win.setHeight(height)
                    focused = next(c for c in self.named("shelfContent")
                                   if c.parentItem().property("t").toVariant()["focused"])
                    tile = focused.parentItem()
                    card = next(c for c in self.named("shelfCard") if c.parentItem() == tile)
                    status = next(c for c in self.named("shelfStatus") if c.parentItem() == focused)
                    action = next(c for c in self.named("shelfAction") if c.parentItem() == tile)
                    self.assertGreater(card.x(), 0)
                    self.assertGreater(card.y(), 0)
                    self.assertGreater(status.height(), 0)
                    self.assertLessEqual(focused.y() + focused.height(), action.y() - 16)
                    self.assertLessEqual(action.x() + action.width(), card.x() + card.width())

    def test_settings_exposes_current_value_and_keeps_detail_inside_card(self):
        self.nav.screen = "hub"
        self.nav.sec[self.nav.game.id] = "settings"
        for language in i18n.LANGUAGES:
            self.nav.language = language
            self.publish()
            with self.subTest(language=language):
                value = self.named("settingsCurrentValue")[0]
                self.assertTrue(value.isVisible())
                self.assertEqual(value.height(), 52)
                label = next(c for c in value.childItems() if c.property("text") is not None)
                self.assertLessEqual(label.property("contentHeight"), label.height())
                detail = self.named("settingsDetailContent")[0]
                card = self.named("settingsDetail")[0]
                self.assertLessEqual(detail.y() + detail.height() * detail.scale(), card.height() - 24 + 1)
                strip = self.named("settingsGroups")[0]
                for group in strip.childItems():
                    if group.width():
                        self.assertLessEqual(group.x() + group.width(), strip.width() + 1)


if __name__ == "__main__":
    unittest.main()
