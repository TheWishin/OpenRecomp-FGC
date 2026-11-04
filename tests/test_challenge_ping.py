"""Peer ping in challenge and match cards, with inert lobby clients and offscreen QML."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QRectF, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from openrecomp import i18n
from openrecomp.adapters import t5_challenges
from openrecomp.app import UI_DIR
from openrecomp.nav import Game, Nav
from openrecomp.vendor.t4lobby.client import LobbyClient
from test_online_adapter import Client, Subject
from test_online_nav import Lobby
from test_online_page import lobby_snapshot
from test_t4_online import Subject as T4Subject
from test_t4_online_nav import T4Lobby
from test_ui_loads import FakeBackend, wait_pages
from test_ui_polish import items


class PingClient(Client):
    ping_to = LobbyClient.ping_to
    ping_info = LobbyClient.ping_info
    _peer_key = staticmethod(LobbyClient._peer_key)

    def __init__(self):
        super().__init__()
        self.me = dict(id="me")
        self.server_rtt = 90
        self.relay_rtts = dict(near=20, far=100)
        self.peer_pings = {}
        self._pmap = dict(peer=dict(id="peer", name="XERO", rtt=100, relays=dict(near=28, far=110)))


class ChallengePingAdapter(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / "build" / "tmp-home"
        root.mkdir(parents=True, exist_ok=True)
        self.directory = self.enterContext(tempfile.TemporaryDirectory(dir=root))
        for target in ("socket.socket", "socket.create_connection", "subprocess.Popen", "subprocess.run"):
            self.enterContext(mock.patch(target, side_effect=AssertionError("external I/O denied")))

    def subject(self, factory=Subject):
        owner = factory(self.directory)
        owner.online_lobby = True
        owner._online_init()
        owner._online_client = PingClient()
        owner._online_phase = "logged_in"
        owner._online_players = [owner._online_player(owner._online_client._pmap["peer"])]
        return owner

    def test_incoming_uses_best_relay_estimate_in_both_adapters(self):
        for factory in (Subject, T4Subject):
            with self.subTest(adapter=factory.__name__):
                owner = self.subject(factory)
                owner._online_client.events.put(dict(t="challenged", challenge="incoming",
                    **{"from": dict(id="peer", name="XERO")}, token="private"))
                owner._online_events()
                offer = owner.online_state()["challenge"]
                self.assertEqual(offer["ping"], 48)
                self.assertFalse(offer["ping_measured"])
                self.assertEqual(offer["ping"], owner._online_players[0]["ping"])
                self.assertNotIn("token", offer)

    def test_measured_pair_rtt_and_route_win_over_server_estimate(self):
        owner = self.subject()
        owner._online_client.peer_pings[("xero", False)] = (31.4, "direct", 0)
        event = {"from": dict(id="peer", name="XERO"),
                 "ping": dict(ms=48, kind="estimate", known=True, path="relay")}
        result = owner._online_ping_view(event)
        self.assertEqual(result, dict(ping=31, ping_measured=True, ping_path="direct"))
        match = owner._online_match_view(dict(opponent=event["from"], ping=event["ping"]))
        self.assertEqual(match, dict(opponent="XERO", opponent_info=dict(id="peer", name="XERO"), **result))

    def test_local_best_relay_sum_wins_over_server_estimate(self):
        owner = self.subject()
        event = {"from": dict(id="peer", name="XERO"),
                 "ping": dict(ms=190, kind="estimate", known=True, path="relay")}
        self.assertEqual(owner._online_ping_view(event), dict(ping=48, ping_measured=False, ping_path="relay"))

    def test_unknown_and_invalid_values_do_not_become_zero_ms(self):
        owner = self.subject()
        owner._online_client._pmap.clear()
        owner._online_players = []
        for ping in (None, {}, dict(ms=0, known=False), dict(ms=True), dict(ms=-1), dict(ms=float("nan"))):
            with self.subTest(ping=ping):
                owner._online_client.events.put({"t": "challenged", "challenge": "unknown",
                                                "from": dict(id="unknown", name="XERO"), "ping": ping})
                owner._online_events()
                self.assertNotIn("ping", owner.online_state()["challenge"])

    def test_old_client_uses_sanitized_player_ping_and_event_route(self):
        owner = self.subject()
        owner._online_client = Client()
        event = {"from": dict(id="peer", name="XERO"), "ping": dict(known=False, path="relay")}
        self.assertEqual(owner._online_ping_view(event), dict(ping=48, ping_measured=False, ping_path="relay"))
        self.assertEqual(owner._online_ping_view(dict(ping=dict(ms=27, kind="measured", path="untrusted"))),
                         dict(ping=27, ping_measured=True))

    def test_match_found_keeps_estimate_before_client_is_closed(self):
        owner = self.subject()
        owner._online_client.events.put(dict(t="match_found", opponent=dict(id="peer", name="XERO")))
        owner._online_events()
        self.assertIsNone(owner._online_client)
        self.assertEqual(owner.online_state()["match"], dict(opponent="XERO", opponent_info=dict(id="peer", name="XERO"),
                                                           ping=48, ping_measured=False))

    def test_outgoing_reply_keeps_ping_and_expiry_clears_waiting(self):
        owner = self.subject()
        t5_challenges.completion(owner, t5_challenges.PREFIX + "send",
            dict(reply=dict(challenge="sent"), player="peer", name="XERO", first_to=2, delay=None), None)
        offer = owner.online_state()["open_challenges"][0]
        self.assertEqual(offer["ping"], 48)
        self.assertFalse(offer["ping_measured"])
        owner._online_client.events.put(dict(t="challenge_update", challenge="sent", state="expired"))
        owner._online_events()
        self.assertEqual(owner.online_state()["open_challenges"], [])

    def test_t4_legacy_outgoing_reply_and_expiry(self):
        owner = self.subject(T4Subject)
        owner._online_results.put((owner._online_generation, "challenge:peer", "sent", None))
        owner.online_poll()
        offer = owner.online_state()["outgoing_challenge"]
        self.assertEqual(offer, dict(id="sent", player="peer", name="XERO", ping=48, ping_measured=False))
        owner._online_client.events.put(dict(t="challenge_update", challenge="sent", state="expired"))
        owner._online_events()
        self.assertEqual(owner.online_state()["outgoing_challenge"], {})


class ChallengePingScene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def test_incoming_outgoing_and_match_ping_in_all_languages_and_both_pages(self):
        for factory in (Lobby, T4Lobby):
            adapter = factory()
            adapter.snapshot.update(lobby_snapshot())
            adapter.snapshot["capabilities"]["challenge_preferences"] = True
            adapter.snapshot["challenge_preferences"] = dict(incoming=dict(id="incoming", first_to=2,
                                                                            wish=dict(stage="random")))
            nav = Nav([Game(adapter.m, adapter)], language="en")
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
                    for mode in ("incoming", "outgoing", "legacy_outgoing", "matched"):
                        for ping in ({}, dict(ping=48, ping_measured=False, ping_path="relay"),
                                     dict(ping=31, ping_measured=True, ping_path="direct"),
                                     dict(ping=78), dict(ping=120), dict(ping=180)):
                            with self.subTest(game=adapter.m["id"], language=language, mode=mode, ping=ping):
                                offer = dict(id="incoming", name="XERO" * 16, first_to=2, **ping)
                                adapter.snapshot.update(phase="matched" if mode == "matched" else "logged_in",
                                    challenge=offer if mode == "incoming" else {},
                                    open_challenges=[offer] if mode == "outgoing" else [],
                                    outgoing_challenge=offer if mode == "legacy_outgoing" else {},
                                    match=dict(opponent="XERO", **ping))
                                backend._v = nav.view()
                                backend.viewChanged.emit()
                                wait_pages(win)
                                online = backend._v["online"]
                                key = "online_ui.ping_ms" if ping.get("ping_measured") else "online_ui.ping_est"
                                expected = i18n.text(language, key, ping=ping["ping"]) if ping else i18n.text(language, "online_ui.ping_unknown")
                                conn = backend._v["matchVersus"]["connection"] if mode == "matched" else backend._v["globalOffers"][0]["connection"] if mode == "incoming" else online["find"]["outgoing"]["connection"]
                                self.assertEqual(conn["text"], expected)
                                expected_bars = {48: 4, 31: 4, 78: 3, 120: 2, 180: 1}.get(ping.get("ping"), 0)
                                self.assertEqual(conn["bars"], expected_bars)
                                self.assertEqual(conn["path"], i18n.text(language, "online_ui.path_" + ping["ping_path"]) if ping.get("ping_path") else "")
                                visible = [item for item in items(win.contentItem()) if item.isVisible()]
                                container = next(item for item in visible if item.objectName() ==
                                                 ("matchVersusCard" if mode == "matched" else "globalOfferPing" if mode == "incoming" else "arcadeOfferPing"))
                                text = next(item for item in items(container) if item.isVisible()
                                            and item.objectName() == "peerPingText")
                                self.assertEqual(text.property("text"), expected)
                                self.assertFalse(text.property("truncated"))
                                signal = text.parentItem()
                                self.assertLessEqual(signal.implicitWidth(), signal.parentItem().width())
                                rectangles = [item for item in signal.childItems()[0].childItems()
                                              if item.objectName() == "peerPingBar"]
                                self.assertEqual(len(rectangles), 4)
                                self.assertEqual(sum(item.property("color") == signal.property("ink")
                                                     for item in rectangles), expected_bars)
                                if mode == "matched":
                                    ready = next(item for item in visible if item.objectName() == "versusReady")
                                    ping_rect = signal.mapRectToScene(QRectF(0, 0, signal.width(), signal.height()))
                                    ready_rect = ready.mapRectToScene(QRectF(0, 0, ready.width(), ready.height()))
                                    card_rect = container.mapRectToScene(QRectF(0, 0, container.width(), container.height()))
                                    self.assertLessEqual(ping_rect.bottom(), ready_rect.top())
                                    self.assertTrue(card_rect.contains(ping_rect))
                                if mode == "incoming":
                                    popup = next(item for item in visible if item.objectName() == "globalOffer")
                                    stage = i18n.text(language, "online.challenge_random_stage")
                                    self.assertTrue(any(stage in str(item.property("text") or "") for item in items(popup)))
                                    origin = nav.focus_index(nav.items())
                                    nav.act("offers", device="xbox")
                                    self.assertTrue(nav.view()["globalOffers"][0]["focused"])
                                    self.assertEqual(nav.focus_index(nav.items()), origin)
                                    self.assertEqual(adapter.calls, [])
                                    nav._global_offer_focus = ""
                self.assertEqual(warnings, [])
                self.assertEqual(adapter.calls, [])
            finally:
                win.close()
                del engine

    def test_new_texts_exist_in_every_catalog(self):
        for language in i18n.LANGUAGES:
            catalog = i18n.catalog(language)
            for key in ("ping_unknown", "path", "path_direct", "path_relay", "path_lan", "waiting_for"):
                self.assertIn("online_ui." + key, catalog)
            self.assertIn("XERO", i18n.text(language, "online_ui.waiting_for", name="XERO"))


if __name__ == "__main__":
    unittest.main()
