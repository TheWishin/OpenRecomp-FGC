"""Global offers use synthetic adapter snapshots and preserve their originating operation."""
import unittest

from openrecomp import i18n, nav_feedback, ui_sound
from openrecomp.nav import Game, Nav
from test_action_feedback import FeedbackLobby


class GlobalOffers(unittest.TestCase):
    def setUp(self):
        self.a = FeedbackLobby()
        self.b = FeedbackLobby()
        self.b.m = dict(self.b.m, id="second", short="Second")
        self.nav = Nav([Game(self.a.m, self.a), Game(self.b.m, self.b)], language="en")

    def offer(self, adapter=None, identity="incoming", **kwargs):
        adapter = adapter or self.a
        adapter.snapshot["challenge"] = dict(id=identity, name="Long rival identity", rank="3rd Dan", ping=72, seconds=30, **kwargs)
        game = next(g for g in self.nav.games if g.a is adapter)
        nav_feedback.observe(self.nav, game, adapter.online_state())
        return nav_feedback.global_view(self.nav)[0]

    def test_popups_exist_on_shelf_main_settings_build_replays_and_other_game_without_focus_theft(self):
        for screen, section in (("start", "play"), ("hub", "settings"), ("hub", "build"), ("hub", "replays"), ("hub", "online")):
            with self.subTest(screen=screen, section=section):
                self.nav.screen = screen
                self.nav.game = self.nav.games[1]
                self.nav.sec[self.nav.game.id] = section
                self.nav.focus = {"second:" + section: 4}
                before = (self.nav.game, self.nav.screen, dict(self.nav.focus), self.nav.overlay)
                row = self.offer()
                self.assertEqual(i18n.localize(row, "en")["name"], "Long rival identity")
                self.assertFalse(row["focused"])
                self.assertEqual((self.nav.game, self.nav.screen, self.nav.focus, self.nav.overlay), before)
                self.assertEqual(self.a.calls, [])

    def test_newest_on_top_notify_once_and_countdown_does_not_notify(self):
        self.offer()
        self.assertEqual(self.nav.take_sound(), ui_sound.NOTIFY)
        self.offer()
        self.assertIsNone(self.nav.take_sound())
        self.offer(self.b, "second-offer")
        rows = nav_feedback.global_view(self.nav)
        self.assertTrue(rows[0]["identity"].endswith("second-offer"))
        self.nav.take_sound()
        nav_feedback.tick(self.nav, 3)
        self.assertEqual(nav_feedback.global_view(self.nav)[0]["countdown"], "0:27")
        self.assertIsNone(self.nav.take_sound())

    def test_accept_from_another_game_routes_to_online_and_cannot_answer_twice(self):
        row = self.offer()
        self.nav.game = self.nav.games[1]
        self.nav.screen = "start"
        self.assertTrue(nav_feedback.click_global(self.nav, row["identity"], True))
        self.assertIs(self.nav.game.a, self.a)
        self.assertEqual(self.nav.screen, "hub")
        self.assertEqual(self.nav.sec[self.nav.game.id], "online")
        self.assertFalse(nav_feedback.click_global(self.nav, row["identity"], False))
        self.assertEqual(self.a.calls, [("online", "accept_challenge")])

    def test_stale_click_and_held_confirmation_do_not_answer_replacement(self):
        row = self.offer()
        self.assertFalse(nav_feedback.global_action(self.nav, "confirm"))
        self.offer(identity="replacement")
        self.assertFalse(nav_feedback.click_global(self.nav, row["identity"], True))
        self.assertEqual(self.a.calls, [])

    def test_late_identical_offer_cannot_reissue_even_after_receipt_expires(self):
        row = self.offer()
        nav_feedback.click_global(self.nav, row["identity"], True)
        self.a.snapshot.update(challenge={}, busy=False, message="@online.challenge_answered")
        nav_feedback.observe(self.nav, self.nav.games[0], self.a.online_state())
        nav_feedback.tick(self.nav, 10)
        self.offer()
        self.assertTrue(nav_feedback.global_view(self.nav)[0]["disabled"])
        self.assertFalse(nav_feedback.click_global(self.nav, row["identity"], True))
        self.nav._online_action(self.nav.games[0], "accept_challenge")
        self.assertEqual(self.a.calls.count(("online", "accept_challenge")), 1)

    def test_explicit_new_connection_releases_bounded_answer_tombstones(self):
        self.a.snapshot["netext_session"] = 1
        row = self.offer()
        nav_feedback.click_global(self.nav, row["identity"], True)
        self.a.snapshot.update(netext_session=2, busy=False)
        nav_feedback.observe(self.nav, self.nav.games[0], self.a.online_state())
        self.assertFalse(nav_feedback.global_view(self.nav)[0]["disabled"])
        nav_feedback.click_global(self.nav, row["identity"], False)
        self.assertEqual(self.a.calls[-1], ("online", "decline_challenge"))
        for number in range(300):
            nav_feedback._mark_answer(self.nav, self.nav.game.id, "synthetic/" + str(number))
        self.assertEqual(len(self.nav._global_offer_answers), 256)

    def test_explicit_pad_review_answers_once_and_binding_and_editing_retain_input(self):
        row = self.offer()
        self.nav.overlay = "binding"
        self.assertFalse(nav_feedback.global_action(self.nav, "offers"))
        self.assertFalse(nav_feedback.click_global(self.nav, row["identity"], True))
        self.nav.overlay = None
        self.nav.native_edit = "online_chat"
        self.assertFalse(nav_feedback.global_action(self.nav, "offers"))
        self.nav.native_edit = ""
        self.assertTrue(nav_feedback.global_action(self.nav, "offers"))
        self.assertTrue(nav_feedback.global_action(self.nav, "back"))
        self.assertEqual(self.a.calls, [("online", "decline_challenge")])

    def test_running_game_uses_ingame_panel_and_never_a_launcher_offer(self):
        self.offer()
        self.a.running = lambda: True
        self.assertEqual(nav_feedback.global_view(self.nav), [])
        self.nav.take_sound()
        self.nav.pending_attention = False
        self.a.snapshot["challenge"] = dict(id="in-game", name="Rival")
        nav_feedback.observe(self.nav, self.nav.games[0], self.a.online_state())
        self.assertIsNone(self.nav.take_sound())
        self.assertFalse(self.nav.pending_attention)

    def test_missing_server_countdown_stays_honest_and_failed_answer_can_retry(self):
        self.a.snapshot["challenge"] = dict(id="legacy", name="Rival")
        nav_feedback.observe(self.nav, self.nav.games[0], self.a.online_state())
        row = nav_feedback.global_view(self.nav)[0]
        self.assertIsNone(row["seconds"])
        self.assertEqual(row["countdown"], "")
        nav_feedback.click_global(self.nav, row["identity"], True)
        self.a.snapshot.update(busy=False, message="@online.failure")
        nav_feedback.observe(self.nav, self.nav.games[0], self.a.online_state())
        self.assertFalse(nav_feedback.global_view(self.nav)[0]["disabled"])
        nav_feedback.click_global(self.nav, row["identity"], False)
        self.assertEqual(self.a.calls[-1], ("online", "decline_challenge"))

    def test_invite_and_ready_use_only_existing_adapter_actions(self):
        self.a.snapshot.update(invites=[dict(id="invite", name="Friend")], challenge={})
        nav_feedback.observe(self.nav, self.nav.games[0], self.a.online_state())
        invite = nav_feedback.global_view(self.nav)[0]
        nav_feedback.click_global(self.nav, invite["identity"], False)
        self.assertEqual(self.a.calls[-1], ("online", "decline_invite:invite"))
        self.a.snapshot.update(invites=[], busy=False, phase="matched", match=dict(id="match", opponent="Rival", ping=31, delay=2))
        nav_feedback.observe(self.nav, self.nav.games[0], self.a.online_state())
        ready = nav_feedback.global_view(self.nav)[0]
        self.assertEqual(ready["kind"], "match")
        self.assertEqual(i18n.localize(ready, "en")["selfName"], "Me")
        nav_feedback.click_global(self.nav, ready["identity"], True)
        nav_feedback.click_global(self.nav, ready["identity"], True)
        self.assertEqual(self.a.calls.count(("online", "start_match")), 1)

    def test_incoming_uses_supplied_challenger_rank_from_player_identity(self):
        self.a.snapshot["challenge"] = dict(id="incoming", player="p1", name="Rival", ping=42)
        nav_feedback.observe(self.nav, self.nav.games[0], self.a.online_state())
        row = i18n.localize(nav_feedback.global_view(self.nav)[0], "en")
        self.assertEqual(row["rank"], "2nd Dan")
        self.assertEqual(row["rating"], "1580")

    def test_ready_popup_uses_adapter_public_opponent_without_a_roster_entry(self):
        self.a.snapshot.update(phase="matched", match=dict(id="public-match", opponent="New rival",
            opponent_info=dict(name="New rival", rank="4th Dan", rating=1710)))
        nav_feedback.observe(self.nav, self.nav.games[0], self.a.online_state())
        row = i18n.localize(nav_feedback.global_view(self.nav)[0], "en")
        self.assertEqual((row["name"], row["rank"], row["rating"]), ("New rival", "4th Dan", "1710"))

    def test_return_activity_preserves_search_identity_and_never_reissues_search(self):
        self.nav._online_action(self.nav.games[0], "search_casual")
        self.nav.screen = "start"
        self.nav.game = self.nav.games[1]
        calls = list(self.a.calls)
        self.assertEqual(nav_feedback.activity_view(self.nav)["phase"], "searching")
        self.assertTrue(nav_feedback.return_activity(self.nav))
        self.assertEqual(self.a.calls, calls)
        nav_feedback.tick(self.nav, 42)
        receipt = nav_feedback.view(self.nav, self.nav.game.id, "search_casual")
        self.assertEqual(receipt["clock"], "0:42")
        self.a.snapshot.update(phase="cancelling")
        nav_feedback.observe(self.nav, self.nav.game, self.a.online_state())
        self.assertEqual(nav_feedback.view(self.nav, self.nav.game.id, "search_casual")["phase"], "cancelling")

    def test_vs_projection_uses_supplied_identity_terms_and_never_invents_ready_or_delay(self):
        self.a.snapshot.update(phase="matched", match=dict(opponent="Rival", ranked=False, ping=42))
        value = i18n.localize(nav_feedback.match_view(self.nav, self.nav.games[0]), "en")
        self.assertEqual(value["right"]["name"], "Rival")
        self.assertEqual(value["right"]["rating"], "1580")
        self.assertEqual(value["right"]["rank"], "2nd Dan")
        self.assertEqual(value["opponentStatus"], "")
        self.assertIsNone(value["seconds"])
        self.assertIn("unknown", [detail["v"] for detail in value["details"]])
        self.a.snapshot["match"].update(delay=dict(auto=True, frames=2), first_to=3, opponent_ready=True, seconds=20)
        nav_feedback.observe(self.nav, self.nav.games[0], self.a.online_state())
        value = i18n.localize(nav_feedback.match_view(self.nav, self.nav.games[0]), "en")
        self.assertIn("2", [detail["v"] for detail in value["details"]])
        self.assertEqual(value["seconds"], 20)
        self.assertEqual(self.a.calls, [])

    def test_global_offer_announces_identity_once_and_countdown_ticks_stay_quiet(self):
        import copy
        from types import SimpleNamespace
        from unittest import mock
        from PySide6.QtCore import QObject
        from openrecomp import app
        current = dict(globalOffers=[], online={})
        backend = SimpleNamespace(window=QObject(), _view=current)
        messages = []
        def record(event):
            messages.append(event.message())
        with mock.patch.object(app.QAccessible, "isActive", return_value=True), mock.patch.object(app.QAccessible, "updateAccessibility", side_effect=record):
            previous = copy.deepcopy(current)
            current["globalOffers"] = [dict(identity="game/challenge:one", title="Challenge", name="Synthetic rival", rank="3rd Dan", seconds=30)]
            app.Backend._announce_view(backend, previous)
            for seconds in (29, 28, 27):
                previous = copy.deepcopy(current)
                current["globalOffers"][0]["seconds"] = seconds
                current["globalOffers"][0]["countdown"] = "0:" + str(seconds)
                app.Backend._announce_view(backend, previous)
            self.assertEqual(messages, ["Challenge. Synthetic rival. 3rd Dan"])
            previous = copy.deepcopy(current)
            current["globalOffers"][0]["identity"] = "game/challenge:two"
            app.Backend._announce_view(backend, previous)
            self.assertEqual(len(messages), 2)


class OfferScene(unittest.TestCase):
    def test_incoming_fixture_is_compact_centered_below_lobby_cards_and_has_only_server_timer(self):
        import os
        from pathlib import Path
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
        from PySide6.QtCore import QObject, QPointF, QUrl
        from PySide6.QtGui import QFontDatabase, QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
        from openrecomp.app import UI_DIR
        from test_ui_loads import FakeBackend, spin, wait_pages
        from tools.online_shots import scene
        gui = QGuiApplication.instance() or QGuiApplication([])
        for path in (Path(UI_DIR) / "fonts").glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(path))
        nav = scene("t5", "challenge_incoming", "en")
        backend = FakeBackend(nav)
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda rows: warnings.extend(row.toString() for row in rows))
        engine.setInitialProperties(dict(backend=backend, wantFull=False))
        engine.load(QUrl.fromLocalFile(str(Path(UI_DIR) / "Main.qml")))
        self.assertTrue(engine.rootObjects(), warnings)
        window = engine.rootObjects()[0]
        for language in ("en", "de", "fr"):
            for width, height in ((1920, 1080), (1280, 720)):
                with self.subTest(language=language, size=(width, height)):
                    window.setWidth(width)
                    window.setHeight(height)
                    nav.language = language
                    backend.refresh()
                    wait_pages(window)
                    spin()
                    popup = window.findChild(QObject, "globalOffer")
                    self.assertTrue(popup.isVisible())
                    stage = popup.parentItem()
                    self.assertAlmostEqual(popup.x() + popup.width() / 2, stage.width() / 2, delta=.5)
                    self.assertAlmostEqual(popup.y() + popup.height() / 2, stage.height() / 2, delta=.5)
                    if language == "en" and width == 1920:
                        self.assertLess(popup.width(), 600)
                    for name in ("onlineProfile", "onlineFind"):
                        card = window.findChild(QObject, name)
                        self.assertTrue(card.isVisible())
                        bottom = card.mapToItem(stage, QPointF(0, card.height())).y()
                        self.assertGreaterEqual(popup.y(), bottom + 8)
                    countdown = window.findChild(QObject, "globalOfferCountdown")
                    self.assertFalse(countdown.isVisible())
                    self.assertEqual(countdown.property("text"), "")
        # A legacy/fallback label must never appear in the deadline slot.
        backend._v["globalOffers"][0]["countdown"] = "No deadline supplied"
        backend.viewChanged.emit()
        spin()
        self.assertFalse(countdown.isVisible())
        self.assertEqual(countdown.property("text"), "")
        nav.game.a.snapshot["challenge"].update(id="timed-challenge", seconds=19)
        nav_feedback.observe(nav, nav.game, nav.game.a.online_state())
        backend.refresh()
        spin()
        self.assertTrue(countdown.isVisible())
        self.assertEqual(countdown.property("text"), "0:19")
        self.assertEqual(nav.game.a.calls, [])
        self.assertEqual(warnings, [])
        window.setProperty("allowClose", True)
        window.close()
        engine.deleteLater()
        gui.processEvents()

    def test_actual_global_popup_and_vs_actions_stay_inside_their_presentations(self):
        import os
        from pathlib import Path
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
        from PySide6.QtCore import QObject, QPointF, QUrl
        from PySide6.QtGui import QFontDatabase, QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
        from openrecomp.app import UI_DIR
        from test_ui_loads import FakeBackend, spin, wait_pages
        gui = QGuiApplication.instance() or QGuiApplication([])
        for path in (Path(UI_DIR) / "fonts").glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(path))
        adapter = FeedbackLobby()
        nav = Nav([Game(adapter.m, adapter)], language="en")
        adapter.snapshot["challenge"] = dict(id="incoming", name="Synthetic challenger", rank="3rd Dan", ping=42, seconds=30)
        nav_feedback.observe(nav, nav.game, adapter.online_state())
        backend = FakeBackend(nav)
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda rows: warnings.extend(row.toString() for row in rows))
        engine.setInitialProperties(dict(backend=backend, wantFull=False))
        engine.load(QUrl.fromLocalFile(str(Path(UI_DIR) / "Main.qml")))
        self.assertTrue(engine.rootObjects(), warnings)
        window = engine.rootObjects()[0]
        for screen, section in (("start", "play"), ("hub", "settings"), ("hub", "play")):
            nav.screen = screen
            nav.sec[nav.game.id] = section
            backend.refresh()
            wait_pages(window)
            spin()
            popup = window.findChild(QObject, "globalOffer")
            self.assertIsNotNone(popup)
            self.assertGreater(popup.property("height"), 0)
            self.assertLess(popup.width(), 900)
            self.assertAlmostEqual(popup.x() + popup.width() / 2, popup.parentItem().width() / 2, delta=.5)
            self.assertAlmostEqual(popup.y() + popup.height() / 2, popup.parentItem().height() / 2, delta=.5)
            countdown = window.findChild(QObject, "globalOfferCountdown")
            self.assertTrue(countdown.property("visible"))
            self.assertEqual(countdown.property("text"), "0:30")
            for name in ("globalOfferAccept", "globalOfferDecline", "globalOfferReview"):
                button = window.findChild(QObject, name)
                origin = button.mapToItem(popup, QPointF())
                self.assertGreaterEqual(origin.x(), 0)
                self.assertGreaterEqual(origin.y(), 0)
                self.assertLessEqual(origin.x() + button.width(), popup.width())
                self.assertLessEqual(origin.y() + button.height(), popup.height())
        adapter.snapshot["challenge"].pop("seconds")
        adapter.snapshot["challenge"]["id"] = "no-deadline"
        nav_feedback.observe(nav, nav.game, adapter.online_state())
        backend.refresh()
        spin()
        self.assertFalse(window.findChild(QObject, "globalOfferCountdown").property("visible"))
        adapter.snapshot.update(challenge={}, phase="matched", match=dict(opponent="Rival", ping=42, delay=dict(frames=2), first_to=2))
        nav.sec[nav.game.id] = "online"
        nav_feedback.observe(nav, nav.game, adapter.online_state())
        backend.refresh()
        wait_pages(window)
        spin()
        card = window.findChild(QObject, "matchVersusCard")
        self.assertIsNotNone(card)
        self.assertFalse(window.findChild(QObject, "globalOffer").property("visible"))
        presentation = window.findChild(QObject, "matchPresentation")
        self.assertIsNotNone(presentation)
        art_bottom = card.mapToItem(presentation, QPointF()).y() + card.height()
        positions = []
        for name in ("versusReady", "versusDecline"):
            button = window.findChild(QObject, name)
            origin = button.mapToItem(presentation, QPointF())
            self.assertGreaterEqual(origin.x(), 0)
            self.assertGreater(origin.y(), art_bottom)
            self.assertLessEqual(origin.x() + button.width(), presentation.width())
            self.assertLessEqual(origin.y() + button.height(), presentation.height())
            positions.append((origin, button))
        ready_origin, ready = positions[0]
        decline_origin, decline = positions[1]
        self.assertLess(ready_origin.x() + ready.width(), decline_origin.x())
        self.assertAlmostEqual(ready_origin.y() + ready.height() / 2,
                               decline_origin.y() + decline.height() / 2, delta=.5)
        self.assertEqual(warnings, [])
        window.setProperty("allowClose", True)
        window.close()
        engine.deleteLater()
        gui.processEvents()


if __name__ == "__main__":
    unittest.main()
