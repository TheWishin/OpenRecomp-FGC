"""Stale pad targets use inert adapters; no window, server or game is opened."""
import unittest
from unittest import mock

from openrecomp.nav import Game, Nav
from test_nav import Fake, manifest
from test_online_nav import Lobby


class SecondAuditNavigation(unittest.TestCase):
    def setUp(self):
        for target in ("socket.socket", "socket.create_connection", "subprocess.Popen", "subprocess.run"):
            self.enterContext(mock.patch(target, side_effect=AssertionError("external I/O denied")))

    def test_history_reply_cannot_replace_focused_replay(self):
        adapter = Lobby()
        adapter.snapshot.update(phase="logged_in", capabilities=dict(lobby=True, profiles=True),
                                profile=dict(name="Fixture", history=[dict(replay_id="first", opponent="First")]))
        nav = Nav([Game(adapter.m, adapter)], language="en")
        nav.screen = "hub"
        nav.sec["lobby"] = "online"
        nav._t5_profile_pages = dict(lobby="profile")
        items = nav.items()
        nav.focus["lobby:online"] = next(i for i, item in enumerate(items)
                                         if item.get("id") == "profile_history_replay:0")
        nav.view()
        adapter.snapshot["profile"]["history"] = [dict(replay_id="replacement", opponent="Another")]
        nav.act("confirm", device="xbox")
        self.assertEqual(adapter.calls, [])
        self.assertEqual(nav.focus["lobby:online"], 0)

    def drawer(self):
        adapters = [Fake(manifest(gid)) for gid in ("first", "second")]
        nav = Nav([Game(adapter.m, adapter) for adapter in adapters], language="en")
        nav.act("social", device="xbox")
        return adapters, nav

    def test_failed_direct_disconnect_keeps_session_screen_visible(self):
        adapter = Lobby()
        adapter.m["adapter"] = "t4"
        adapter.snapshot["capabilities"] = dict(direct_ip=True)
        nav = Nav([Game(adapter.m, adapter)], language="en")
        nav.screen = "hub"
        nav.sec["lobby"] = "online"
        with mock.patch.object(adapter, "online_action", side_effect=RuntimeError("private failure")) as action:
            nav.act("back", device="xbox")
        action.assert_called_once_with("disconnect")
        self.assertEqual(nav.screen, "hub")
        self.assertEqual(nav.toast, "@online.failure")
        self.assertEqual(nav.section(), "online")

    def test_removed_native_launcher_does_not_retarget_pad_confirm(self):
        for action in ("confirm", "left", "right"):
            with self.subTest(action=action):
                adapters, nav = self.drawer()
                saved = []
                nav.on_language = saved.append
                nav.drawer_focus = 4
                nav.view()
                adapters[0].found = lambda: False
                nav.act(action, device="xbox")
                self.assertEqual(adapters[1].calls, [])
                self.assertEqual(nav.drawer_focus, 0)
                self.assertEqual(nav.language, "en")
                self.assertEqual(saved, [])
                for _ in range(4):
                    nav.act("down", device="xbox")
                nav.act("confirm", device="xbox")
                self.assertEqual(adapters[1].calls, [("native",)])

    def test_removed_last_native_launcher_keeps_drawer_drawable(self):
        adapters, nav = self.drawer()
        nav.drawer_focus = 5
        nav.view()
        adapters[1].found = lambda: False
        view = nav.view()
        self.assertEqual(nav.drawer_focus, 0)
        self.assertEqual(sum(row["focused"] for row in view["drawer"]["rows"]), 1)


if __name__ == "__main__":
    unittest.main()
