"""Replay headings and cell baselines grow with the viewport-aware type floor."""
import unittest
from openrecomp import i18n
import test_ui_secondary_polish as secondary
from PySide6.QtCore import QObject, QPointF
from test_ui_loads import spin


class ReplayTypography(unittest.TestCase):
    setUpClass = classmethod(secondary.SecondaryCards.setUpClass.__func__)
    setUp = secondary.SecondaryCards.setUp
    tearDown = secondary.SecondaryCards.tearDown
    named = secondary.SecondaryCards.named
    publish = secondary.SecondaryCards.publish

    def test_replay_header_and_cells_fit_720p_larger_text_without_overlap(self):
        self.win.setWidth(1280)
        self.win.setHeight(720)
        self.nav.sec[self.nav.game.id] = "replays"
        self.nav.text_size = 130
        self.nav.focus[self.nav.key()] = next(n for n, row in reversed(list(enumerate(self.nav.items())))
                                             if row.get("replay") is not None)
        for language in i18n.LANGUAGES:
            with self.subTest(language=language):
                self.nav.language = language
                self.publish()
                spin(20)
                header = next(item for item in self.named("replayTableHeader") if item.isVisible())
                captions = [item for item in secondary.scene_items(header) if item.property("text")]
                self.assertEqual(len(captions), 5)
                for caption in captions + self.named("replayTableCell"):
                    if not caption.isVisible():
                        continue
                    self.assertLessEqual(caption.property("contentHeight"), caption.height() + 1)
                    if caption in captions:
                        self.assertFalse(caption.property("truncated"))
                viewport = self.named("sessionViewport")[0]
                self.assertGreaterEqual(viewport.y(), header.y() + header.height() + 8)
                selected = next(row for row in self.named("sessionRow")
                                if row.findChild(QObject, "interactionFeedback").property("selected"))
                position = selected.mapToItem(viewport, QPointF(0, 0))
                self.assertGreaterEqual(position.y(), -.1)
                self.assertLessEqual(position.y() + selected.height(), viewport.height() + .1)
