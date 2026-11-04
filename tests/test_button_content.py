"""Large action content stays centered with device prompts inside synthetic scenes."""
import unittest

from PySide6.QtCore import QPointF

from test_ui_loads import spin
import test_ui_polish as polish
from tools.online_shots import scene, snapshot


class ButtonContent(unittest.TestCase):
    setUpClass = classmethod(polish.ScenePolish.setUpClass.__func__)
    setUp = polish.ScenePolish.setUp
    tearDown = polish.ScenePolish.tearDown
    named = polish.ScenePolish.named
    wait_pages = polish.ScenePolish.wait_pages

    def publish(self, game, state, language, device="xbox"):
        self.nav = scene(game, state, language)
        self.nav.device = device
        self.backend.nav = self.nav
        self.backend._v = snapshot(self.nav)
        self.backend.viewChanged.emit()
        self.wait_pages()
        spin(20)

    def assert_centered(self, button):
        caption = next(item for item in polish.items(button)
                       if item.objectName() == "onlineFieldLabel")
        center = caption.mapToItem(button, QPointF(caption.width() / 2, caption.height() / 2))
        content_height = button.height() - button.property("feedbackHeight")
        self.assertAlmostEqual(center.y(), content_height / 2, delta=.5)
        self.assertGreaterEqual(caption.mapToItem(button, QPointF()).y(), 0)
        self.assertLessEqual(center.y() + caption.height() / 2, button.height())
        # A primary action has no unexplained bottom stripe.
        self.assertFalse(any(child.isVisible() and child.height() == 2
                             for child in button.childItems()))

    def test_matched_labels_and_pad_prompts_are_centered_at_both_output_sizes(self):
        for game in ("t4", "t5"):
            for language in ("de", "en"):
                self.publish(game, "matched", language)
                for width, height in ((1920, 1080), (1280, 720)):
                    with self.subTest(game=game, language=language, width=width):
                        self.win.setWidth(width)
                        self.win.setHeight(height)
                        spin(20)
                        for name, expected in (("versusReady", "A"), ("versusDecline", "B")):
                            button = self.named(name)[0]
                            self.assert_centered(button)
                            glyph = next(item for item in polish.items(button)
                                         if item.objectName() == "onlineButtonGlyph")
                            self.assertTrue(glyph.isVisible())
                            self.assertEqual(glyph.property("g").toVariant()["text"], expected)
                            origin = glyph.mapToItem(button, QPointF())
                            self.assertGreaterEqual(origin.x(), 0)
                            self.assertGreaterEqual(origin.y(), 0)
                            self.assertLessEqual(origin.x() + glyph.width(), button.width())
                            self.assertLessEqual(origin.y() + glyph.height(), button.height())
                            self.assertAlmostEqual(origin.y() + glyph.height() / 2, button.height() / 2, delta=.5)

    def test_shared_button_content_is_centered_throughout_large_action_scenes(self):
        for state in ("searching", "result", "ranked", "rooms_create", "offer_settings"):
            with self.subTest(state=state):
                self.publish("t5", state, "de")
                buttons = [item for item in polish.items(self.win.contentItem())
                           if item.isVisible() and item.property("captionHeight") is not None]
                for button in buttons:
                    self.assert_centered(button)
                labels = [item for item in polish.items(self.win.contentItem())
                          if item.isVisible() and item.objectName() == "arcadeActionLabel"]
                self.assertTrue(buttons or labels, state)
                for label in labels:
                    self.assertAlmostEqual(label.y() + label.height() / 2,
                                           label.parentItem().height() / 2, delta=.5)
                if state == "result":
                    for label in self.named("onlineFieldLabel"):
                        if label.isVisible() and label.property("text") in ("Ich habe gewonnen", "Ich habe verloren", "Kein Ergebnis"):
                            self.assertAlmostEqual(label.y() + label.height() / 2,
                                                   label.parentItem().height() / 2, delta=.5)

    def test_tall_main_menu_actions_center_the_label_and_subtitle_below_the_group(self):
        for width, height in ((1920, 1080), (1280, 720)):
            self.win.setWidth(width)
            self.win.setHeight(height)
            self.publish("t5", "home", "de")
            for label in self.named("mainMenuEntryLabel"):
                button = label.parentItem()
                subtitle = next(child for child in button.childItems()
                                if child.objectName() == "mainMenuEntrySubtitle")
                bottom = subtitle.y() + subtitle.height() if subtitle.isVisible() else label.y() + label.height()
                self.assertAlmostEqual((label.y() + bottom) / 2,
                                       (button.height() + button.property("groupH")) / 2, delta=.5)

    def test_decline_prompt_tracks_the_current_input_device(self):
        for device, expected in (("kb", "Esc"), ("xbox", "B")):
            self.publish("t5", "matched", "en", device)
            glyph = next(item for item in polish.items(self.named("versusDecline")[0])
                         if item.objectName() == "onlineButtonGlyph")
            self.assertEqual(glyph.property("g").toVariant()["text"], expected)

    def test_match_feedback_keeps_its_own_space_below_centered_content(self):
        self.publish("t5", "matched", "en")
        button = self.named("versusReady")[0]
        previous_height = button.height()
        data = button.property("b").toVariant()
        data["feedback"] = dict(kind="error", text="Synthetic reply failed")
        button.setProperty("b", data)
        spin(20)
        self.assertGreater(button.height(), previous_height)
        self.assert_centered(button)
        receipt = next(child for child in button.childItems()
                       if child.property("receipt") is not None)
        content = next(child for child in button.childItems()
                       if any(item.objectName() == "onlineButtonGlyph" for item in child.childItems()))
        self.assertGreater(receipt.y(), content.y() + content.height())
        self.assertLessEqual(receipt.y() + receipt.height(), button.height())


if __name__ == "__main__":
    unittest.main()
