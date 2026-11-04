"""Two offscreen T4 launchers sharing an inert lobby; no install, socket or game process."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from openrecomp.adapters.t4_online import T4Online
from openrecomp.app import UI_DIR
from openrecomp.nav import Game, Nav
from openrecomp.vendor.t4lobby import t4game
from pad_step import pad_step
from test_nav import manifest
from test_t4_game_result import game_file
from test_t4_online import MatchClient, Subject, ticket
from test_ui_loads import FakeBackend, spin, wait_pages


class FakeLobby:
    def __init__(self):
        self.players = {}
        self.offers = {}
        self.reports = {}
        self.votes = set()
        self.number = 0

    def snapshot(self):
        return dict(t="lobby_state", players=[dict(c.me) for c in self.players.values()],
                    rooms=[dict(id="room", name="Practice", players=1, max_players=2)])

    def publish(self):
        for client in self.players.values():
            client.events.put(self.snapshot())

    def match(self, origin="challenge"):
        self.number += 1
        self.match_id = "pair-%d" % self.number
        clients = list(self.players.values())
        for slot, client in enumerate(clients):
            peer = clients[1 - slot]
            client.events.put(dict(t="match_found", match=self.match_id, ready_check=False,
                                   origin=origin,
                                   slot=slot, you=client.me, opponent=peer.me,
                                   ping=dict(ms=24, kind="measured", path="direct")))
            client.events.put(dict(t="match_start", ticket=ticket(
                "host" if slot == 0 else "join", match_id=self.match_id, rtt_ms=24,
                local_port=30001 + slot, peer=("127.0.0.1", 30002 - slot))))


class PairedClient(MatchClient):
    def __init__(self, lobby, **kwargs):
        super().__init__(**kwargs)
        self.lobby = lobby
        self.welcome = dict(ranked_queue=True)

    def enter(self, name, guest):
        self.me = dict(id=name.lower(), name=name, guest=guest, tier=0, rating=1000, status="online")
        self.lobby.players[self.me["id"]] = self
        self.lobby.publish()
        return self.me

    def login_guest(self, name):
        super().login_guest(name)
        return self.enter(name, True)

    def login(self, name, password, remember):
        super().login(name, password, remember)
        return self.enter(name, False)

    def refresh(self):
        return self.lobby.snapshot()

    def challenge(self, player):
        self.calls.append(("challenge", player))
        cid = "offer"
        self.lobby.offers[cid] = self
        self.lobby.players[player].events.put(dict(t="challenged", challenge=cid,
            **{"from": self.me}, ping=dict(ms=24, kind="measured", path="direct")))
        return dict(challenge=cid)

    def answer_challenge(self, challenge, accept=True):
        self.calls.append(("answer", challenge, accept))
        if accept and challenge in self.lobby.offers:
            self.lobby.match()

    def chat(self, text):
        self.calls.append(("chat", text))
        for client in self.lobby.players.values():
            client.events.put(dict(t="chat", **{"from": self.me}, text=text))

    def report_result(self, **values):
        super().report_result(**values)
        reports = self.lobby.reports.setdefault(values["match_id"], {})
        reports[self.me["id"]] = values
        if len(reports) == 2:
            for client in self.lobby.players.values():
                client.events.put(dict(t="match_result", match=values["match_id"], status="confirmed",
                                       rematch_window=True))

    def rematch(self, *args, **kwargs):
        self.calls.append(("rematch", args, kwargs))
        if kwargs.get("accept") is False:
            return
        self.lobby.votes.add(self.me["id"])
        if len(self.lobby.votes) == 2:
            self.lobby.votes.clear()
            self.lobby.match(origin="rematch")


class Launcher(Subject):
    # Use the shipping mode selection, unlike the older opt-in lobby fixture.
    online_direct_ip = T4Online.online_direct_ip
    other_launcher_game = ""
    native_label = ""

    def __init__(self, directory, lobby):
        self.lobby = lobby
        super().__init__(directory)
        self.core.STEPS = []
        self.m.update(manifest("t4", sections=("play", "online", "settings"), adapter="t4"))
        self._online_api.update(game_env=t4game.game_env,
                                game_result=(t4game.read_game_result, t4game.game_result_report))

    def make_client(self, **kwargs):
        client = PairedClient(self.lobby, **kwargs)
        self.clients.append(client)
        return client

    def online_cfg_path(self):
        return os.path.join(self.root, "online-t4.json")

    def hero(self):
        return ""

    def fighters(self):
        return []

    def rank_plate(self, tier):
        return ""


class TwoLauncherFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        root = Path(__file__).resolve().parents[1] / "build" / "tmp-home"
        root.mkdir(parents=True, exist_ok=True)
        self.directory = self.enterContext(tempfile.TemporaryDirectory(dir=root))
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_HOME=self.directory))
        self.enterContext(mock.patch("openrecomp.adapters.t4_online.game_process_running", return_value=False))
        self.enterContext(mock.patch("openrecomp.adapters.t4_online.save_config"))
        for target in ("socket.socket", "socket.create_connection", "subprocess.Popen", "subprocess.run"):
            self.enterContext(mock.patch(target, side_effect=AssertionError("external I/O denied")))
        self.lobby = FakeLobby()
        self.launchers = []
        self.engines = []
        self.warnings = []
        for name in ("Alice", "Bob"):
            directory = Path(self.directory) / name
            directory.mkdir()
            with mock.patch.dict(os.environ, OPENRECOMP_HOME=str(directory)):
                adapter = Launcher(str(directory), self.lobby)
                adapter.online_state()
            self.addCleanup(adapter.online_close)
            nav = Nav([Game(adapter.m, adapter)], language="en", ui_sounds=False)
            nav.screen = "hub"
            nav.sec["t4"] = "online"
            backend = FakeBackend(nav)
            engine = QQmlApplicationEngine()
            engine.warnings.connect(lambda ws: self.warnings.extend(w.toString() for w in ws))
            engine.setInitialProperties({"backend": backend, "wantFull": False})
            engine.load(QUrl.fromLocalFile(str(Path(UI_DIR) / "Main.qml")))
            self.assertTrue(engine.rootObjects(), self.warnings)
            engine.rootObjects()[0].show()
            wait_pages(engine.rootObjects()[0])
            self.engines.append(engine)
            self.launchers.append((adapter, nav, backend))
        self.addCleanup(self.close_windows)

    def close_windows(self):
        for engine in self.engines:
            for window in engine.rootObjects():
                window.close()
            engine.deleteLater()
        self.engines.clear()
        spin(10)

    def pump(self):
        for _ in range(8):
            for adapter, nav, backend in self.launchers:
                nav.tick(.016)
                backend._v = nav.view()
                backend.viewChanged.emit()
            spin(1)

    def choose(self, index, iid):
        adapter, nav, backend = self.launchers[index]
        for _ in range(300):
            rows = nav.items()
            target = next((i for i, row in enumerate(rows) if row.get("id") == iid), None)
            self.assertIsNotNone(target, (iid, [row.get("id") for row in rows]))
            if nav.focus_index(rows) == target:
                nav.view()  # record the exact row before controller confirmation
                nav.act("confirm", device="xbox")
                self.pump()
                return
            pad_step(nav, target)
        self.fail("Controller could not reach " + iid)

    def test_fake_queues_keep_account_ranked_and_guest_casual_rules(self):
        for index, name in enumerate(("Alice", "Bob")):
            adapter = self.launchers[index][0]
            adapter.set_text_value("online_name", name)
            adapter.set_text_value("online_password", "fixture")
            self.choose(index, "login_account" if index == 0 else "login_guest")
        alice, bob = (launcher[0] for launcher in self.launchers)
        self.choose(0, "search_ranked")
        self.assertEqual(alice.online_state()["phase"], "searching")
        self.assertIn(("ranked", "random"), alice.clients[-1].calls)
        self.assertEqual(alice.starts, [])
        self.choose(0, "cancel")
        self.assertEqual(alice.online_state()["phase"], "logged_in")
        self.assertFalse(alice.clients[-1].closed.is_set())
        self.choose(1, "search_ranked")
        self.assertEqual(bob.online_state()["phase"], "logged_in")
        ranked = next(row for row in self.launchers[1][1].items() if row.get("id") == "search_ranked")
        self.assertTrue(ranked["disabled"])
        self.assertEqual(ranked["hint"], "@online_ui.ranked_account")
        self.assertNotIn(("ranked", "random"), bob.clients[-1].calls)
        self.choose(1, "search_casual")
        self.assertEqual(bob.online_state()["phase"], "searching")
        self.assertIn(("quick", "random"), bob.clients[-1].calls)
        self.assertEqual(bob.starts, [])
        self.choose(1, "cancel")
        self.assertEqual(bob.online_state()["phase"], "logged_in")
        self.assertFalse(bob.clients[-1].closed.is_set())
        self.assertEqual(self.warnings, [])

    def test_login_challenge_fight_result_rematch_and_leave(self):
        for index, name in enumerate(("Alice", "Bob")):
            adapter, nav, backend = self.launchers[index]
            self.assertEqual(backend._v["online"]["layout"], "login")
            self.assertNotIn("host", [r.get("id") for r in nav.items()])
            adapter.set_text_value("online_name", name)
            adapter.set_text_value("online_password", "fixture")
            self.choose(index, "login_account" if index == 0 else "login_guest")
            self.assertEqual(adapter.online_state()["phase"], "logged_in")
            self.assertTrue(adapter.clients[-1].kwargs["relays"])
            self.assertEqual(backend._v["online"]["layout"], "lobby")
            self.assertTrue({"search_casual", "search_ranked", "join_room:room", "online_chat"}
                            <= {r.get("id") for r in nav.items()})
        alice, bob = (launcher[0] for launcher in self.launchers)
        self.assertTrue(alice.online_state()["account"])
        self.assertFalse(bob.online_state()["account"])
        alice.set_text_value("online_chat", "Ready?")
        self.choose(0, "send_chat")
        self.assertEqual(bob.online_state()["chat"][-1]["text"], "Ready?")
        self.choose(0, "challenge:bob")
        incoming = bob.online_state()["challenge"]
        self.assertEqual((incoming["name"], incoming["ping"], incoming["ping_path"]),
                         ("Alice", 24, "direct"))
        bob_nav = self.launchers[1][1]
        self.assertEqual((bob_nav.overlay, bob_nav.confirm_kind), ("dialog", "online_challenge"))
        self.assertEqual(bob_nav.exit_focus, 0)
        dialog = bob_nav.view()["dialog"]
        self.assertIn("Alice", dialog["title"])
        self.assertIn("24", dialog["text"])
        bob_nav.act("right", device="xbox")
        bob_nav.act("confirm", device="xbox")
        self.pump()
        for adapter, nav, backend in self.launchers:
            self.assertEqual(adapter.online_state()["phase"], "matched")
            self.assertEqual(adapter.starts, [])
            self.assertEqual(adapter.online_state()["match"]["ping"], 24)
        for index in range(2):
            self.choose(index, "start_match")
        for index, (adapter, nav, backend) in enumerate(self.launchers):
            self.assertEqual(adapter.online_state()["phase"], "playing")
            env = adapter.starts[-1]
            self.assertEqual(env["TEKKEN4_NET"], "host:30001" if index == 0 else "join:127.0.0.1:30001")
            self.assertEqual(env["TEKKEN4_NET_MATCH"], self.lobby.match_id)
            self.assertEqual(env["TEKKEN4_NET_BUILD"], "fake-build")
            self.assertEqual(env["TEKKEN4_NET_SEED"], "42")
            self.assertEqual(env["TEKKEN4_NET_AUTO_VS"], "1")
            self.assertIn("TEKKEN4_NET_RESULT", env)
            self.assertFalse(any(key.startswith("T5_") for key in env))
            game_file(env["TEKKEN4_NET_RESULT"], match=self.lobby.match_id)
        self.pump()
        for slot, (adapter, nav, backend) in enumerate(self.launchers):
            self.assertEqual(adapter.online_state()["phase"], "result_sent")
            self.assertEqual(adapter.online_state()["message"], "@online.result_confirmed")
            self.assertEqual(adapter.online_state()["result"],
                             dict(winner=1, score=[1, 2], slot=slot, source="game"))
            reports = [call[1] for call in adapter.clients[-1].calls
                       if isinstance(call, tuple) and call[0] == "result"]
            self.assertEqual(len(reports), 1)
            self.assertEqual(reports[0]["source"], "game")
            self.assertEqual(reports[0]["score"], [1, 2])
        for index in range(2):
            self.choose(index, "rematch")
        for index, (adapter, nav, backend) in enumerate(self.launchers):
            self.assertEqual(adapter.online_state()["phase"], "playing")
            self.assertEqual(adapter.online_state()["result"], {})
            self.assertEqual(len(adapter.starts), 2)
            self.assertEqual(adapter.starts[-1]["TEKKEN4_NET_MATCH"], "pair-2")
            adapter.child_exit = 0
        self.pump()
        for index in range(2):
            self.choose(index, "result_none")
        for index in range(2):
            self.choose(index, "return_lobby")
            adapter, nav, backend = self.launchers[index]
            self.assertEqual(adapter.online_state()["phase"], "logged_in")
            self.assertFalse(adapter.clients[-1].closed.is_set())
            self.assertEqual(adapter.online_state()["match"], {})
            self.assertEqual(adapter.online_state()["result"], {})
            self.choose(index, "logout")
            self.assertTrue(adapter.clients[-1].closed.is_set())
        self.assertEqual(self.warnings, [])


if __name__ == "__main__":
    unittest.main()
