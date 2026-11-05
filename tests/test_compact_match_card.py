"""The match offer overlays a compact pair of filled fighter panels beside chat."""
from pathlib import Path
import tempfile
import unittest

from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor, QImage

from tools import online_shots
from openrecomp import i18n
from test_ui_loads import spin
import test_ui_versus_art as versus_art
from PySide6.QtQml import QQmlExpression, qmlContext


class CompactMatchCard(unittest.TestCase):
    setUpClass = classmethod(versus_art.VersusArt.setUpClass.__func__)
    setUp = versus_art.VersusArt.setUp
    tearDown = versus_art.VersusArt.tearDown
    named = versus_art.VersusArt.named
    publish = versus_art.VersusArt.publish

    def use_scene(self, game, language, phase="matched"):
        self.nav = online_shots.scene(game, phase, language)
        self.backend.nav = self.nav
        self.backend._v = online_shots.snapshot(self.nav)
        self.publish()

    def test_card_is_centered_compact_and_preserves_chat_in_both_games_and_languages(self):
        for game in ("t4", "t5"):
            for language in ("de", "en"):
                self.use_scene(game, language)
                for width, height in online_shots.SIZES:
                    with self.subTest(game=game, language=language, size=(width, height)):
                        self.win.setWidth(width); self.win.setHeight(height); spin(30)
                        presentation = self.named("matchPresentation")[0]
                        card = self.named("matchVersusCard")[0]
                        page = presentation.parentItem()
                        self.assertAlmostEqual(card.width() / page.width(), .64)
                        self.assertAlmostEqual(card.height() / page.height(), .55)
                        self.assertAlmostEqual(presentation.x() + presentation.width() / 2, page.width() / 2, delta=.5)
                        self.assertAlmostEqual(presentation.y() + presentation.height() / 2, page.height() / 2, delta=.5)
                        self.assertGreaterEqual(presentation.y(), 0)
                        self.assertLessEqual(presentation.y() + presentation.height(), page.height())
                        dock = self.named("lobbyChatPane")[0]
                        self.assertTrue(dock.isVisible())
                        self.assertTrue(dock.isEnabled())
                        self.assertGreaterEqual(dock.x(), page.width())
                        dimmer = self.named("matchLobbyDimmer")[0]
                        self.assertEqual(dimmer.width(), page.width())
                        self.assertLess(dimmer.width(), 1920)
                        backdrop = self.named("matchLobbyBackdrop")[0]
                        self.assertTrue(backdrop.isVisible())
                        self.assertFalse(backdrop.isEnabled())
                        self.assertTrue(self.named("arcadePlayer", backdrop))
                        info = self.named("versusInfoLine")[0]
                        self.assertFalse(info.property("truncated"), info.property("text"))
                        self.assertIn("42", info.property("text"))
                        status = self.named("versusStatusPlate")[0]
                        for name in self.named("versusPlayerName"):
                            identity = name.parentItem()
                            self.assertGreaterEqual(identity.y(), status.y() + status.height() - 1)

    def test_art_fills_both_halves_with_overlaid_identity_and_no_centre_gutter(self):
        card = self.named("matchVersusCard")[0]
        halves = self.named("versusFighterHalf")
        self.assertEqual(len(halves), 2)
        self.assertAlmostEqual(sum(half.width() for half in halves), card.width() - 4)
        for half in halves:
            portrait = self.named("versusPortrait", half)[0]
            self.assertEqual((portrait.x(), portrait.y()), (0, 0))
            self.assertEqual((portrait.width(), portrait.height()), (half.width(), half.height()))
            picture = self.named("fighterPicture", portrait)[0]
            self.assertTrue(QQmlExpression(qmlContext(picture), picture, "fillMode === 2").evaluate()[0])  # PreserveAspectCrop
            identity = self.named("versusPlayerName", half)[0].parentItem()
            self.assertGreater(identity.y(), 0)
            self.assertLessEqual(identity.y() + identity.height(), half.height())
            self.assertEqual(len(self.named("versusIdentityGradient", half)), 1)
        ring = self.named("versusCountdownRing")[0]
        self.assertAlmostEqual(ring.x() + ring.width() / 2, card.width() / 2, delta=.5)
        info = self.named("versusInfoLine")[0]
        self.assertTrue(info.property("text"))
        self.assertTrue(QQmlExpression(qmlContext(info), info, "wrapMode === 0").evaluate()[0])  # NoWrap
        ready = self.named("versusReady")[0]
        decline = self.named("versusDecline")[0]
        self.assertGreater(ready.width(), decline.width() * 2)
        self.assertGreater(ready.height(), decline.height())
        self.assertEqual(ready.parentItem(), decline.parentItem())
        footer = self.named("versusFooter")[0]
        self.assertGreaterEqual(footer.y(), card.height())
        self.assertLessEqual(info.height() + 10, ready.parentItem().y())

    def test_rank_plates_and_identity_stay_on_art_at_720p(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "build") as temporary:
            path = Path(temporary) / "synthetic-rank.png"
            plate = QImage(180, 30, QImage.Format_RGBA8888)
            plate.fill(QColor("#b39760"))
            self.assertTrue(plate.save(str(path)))
            for game in ("t4", "t5"):
                for language in ("de", "en"):
                    with self.subTest(game=game, language=language):
                        self.use_scene(game, language, "matched_picks")
                        self.win.setWidth(1280); self.win.setHeight(720)
                        for side in ("left", "right"):
                            self.backend._v["matchVersus"][side]["plate"] = QUrl.fromLocalFile(str(path)).toString()
                        self.publish()
                        status = self.named("versusStatusPlate")[0]
                        for half in self.named("versusFighterHalf"):
                            plate_item = self.named("versusRankPlate", half)[0]
                            identity = plate_item.parentItem()
                            self.assertTrue(plate_item.isVisible())
                            self.assertEqual(plate_item.height(), 30)
                            self.assertGreaterEqual(identity.y(), 0)
                            self.assertLessEqual(identity.y() + identity.height(), half.height())
                            self.assertGreaterEqual(identity.y(), status.y() + status.height() - 1)

    def test_local_ready_waits_before_starting_on_the_same_compact_card(self):
        for game in ("t4", "t5"):
            for language in ("de", "en"):
                with self.subTest(game=game, language=language):
                    self.use_scene(game, language)
                    self.win.setWidth(1280); self.win.setHeight(720)
                    card = self.named("matchVersusCard")[0]
                    self.nav.game.a.snapshot["phase"] = "starting"
                    self.backend._v = online_shots.snapshot(self.nav)
                    self.publish()
                    self.assertIs(self.named("matchVersusCard")[0], card)
                    self.assertTrue(card.isVisible())
                    ready = self.named("versusReady")[0].property("b").toVariant()
                    decline = self.named("versusDecline")[0].property("b").toVariant()
                    self.assertTrue(ready["disabled"])
                    self.assertTrue(decline["disabled"])
                    self.assertTrue(decline["label"])
                    waiting = i18n.text(language, "online.waiting_peer_ready")
                    status = self.named("versusStatus")[0]
                    self.assertEqual(status.property("text"), waiting)
                    self.assertFalse(status.property("truncated"))
                    self.assertEqual(ready["label"], waiting)
                    self.nav.game.a.snapshot["match"]["opponent_ready"] = True
                    self.backend._v = online_shots.snapshot(self.nav)
                    self.publish()
                    self.assertIs(self.named("matchVersusCard")[0], card)
                    self.assertTrue(card.isVisible())
                    starting = i18n.text(language, "online.starting")
                    self.assertEqual(self.named("versusStatus")[0].property("text"), starting)
                    self.assertEqual(self.named("versusReady")[0].property("b").toVariant()["label"], starting)


if __name__ == "__main__":
    unittest.main()
