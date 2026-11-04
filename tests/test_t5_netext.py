"""T5DR 1.2.1 contracts with inert clients, controller input and local temporary files."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from openrecomp import i18n
from openrecomp.adapters import t5_netext
from openrecomp.adapters.t5_match import T5Match
from openrecomp.nav import Game, Nav
from test_online_adapter import Client as OldClient, Subject
from test_online_nav import Lobby
from test_online_page import lobby_snapshot
from pad_step import pad_step


class Client(OldClient):
    def __init__(self):
        super().__init__()
        self.welcome = dict(features=["mm_filters", "forget_me"])

    def quick_match(self, char=None, options=None):
        self.calls.append(("quick", char, options))

    def ranked_match(self, char=None, strict=False, options=None):
        self.calls.append(("ranked", char, strict, options))

    def forget_me(self, password, dry_run=False):
        self.calls.append(("forget", password, dry_run))
        if dry_run:
            return dict(counts=dict(matches=12, sets=4, friends=2))
        self.session = None
        self.events.put(dict(t="disconnected"))
        return dict(t="forgotten")


class NetextAdapter(unittest.TestCase):
    def setUp(self):
        build = Path(__file__).resolve().parents[1] / "build"
        build.mkdir(exist_ok=True)
        self.directory = self.enterContext(tempfile.TemporaryDirectory(dir=build))
        self.enterContext(mock.patch.dict(os.environ, T5_ONLINE_DIR=self.directory, OPENRECOMP_HOME=self.directory))
        self.enterContext(mock.patch("socket.socket", side_effect=AssertionError("network forbidden")))
        self.enterContext(mock.patch("subprocess.Popen", side_effect=AssertionError("game forbidden")))
        self.a = Subject(self.directory)
        self.a.online_lobby = True
        self.a._online_init()
        self.a._online_game_check = lambda: None
        self.a._online_phase, self.a._online_name, self.a._online_account = "logged_in", "Tester", True
        self.a._online_fields["online_server"] = "local-only"
        self.client = self.a._online_client = Client()
        self.addCleanup(self.a.online_close)

    def do(self, action):
        self.a.online_action(action)
        self.a.online_poll()

    def test_both_queues_send_native_option_keys_and_preserve_strict(self):
        self.do("netext_set:max_ping:100")
        self.do("netext_set:no_wifi:true")
        self.do("netext_set:steady:true")
        expected = dict(max_ping=100, no_wifi=True, steady=True)
        self.do("search_casual")
        self.assertIn(("quick", "random", expected), self.client.calls)
        self.a._online_phase = "logged_in"
        self.a._online_strict = True
        self.do("search_ranked")
        self.assertIn(("ranked", "random", True, expected), self.client.calls)
        self.assertNotIn("steady_only", str(self.client.calls))

    def test_defaults_and_all_ping_choices_survive_reload_without_losing_sessions(self):
        token = self.client.session
        self.a._online_write_session("local-only", "Tester", token)
        self.assertEqual(t5_netext.options(self.a, self.client)["options"],
                         dict(max_ping=None, no_wifi=False, steady=False))
        for ping in (60, 100, 150, None):
            self.do("netext_max_ping")
            self.assertEqual(t5_netext.options(self.a, self.client)["options"]["max_ping"], ping)
        self.do("netext_set:max_ping:100")
        del self.a._netext_preferences
        self.assertEqual(t5_netext.state(self.a)["netext"]["max_ping"], 100)
        with open(self.a.online_cfg_path(), encoding="utf-8") as stream:
            doc = json.load(stream)
        self.assertEqual(doc["sessions"]["local-only"]["token"], token)
        self.assertNotIn("password", doc)

    def test_old_server_or_old_client_keeps_old_queue_signature(self):
        for client in (Client(), OldClient()):
            if isinstance(client, Client):
                client.welcome = dict(features=[])
            else:
                client.welcome = dict(features=["mm_filters"])
            self.a._online_client = client
            self.assertFalse(self.a.online_state()["capabilities"]["search_options"])
            self.assertEqual(t5_netext.options(self.a, client), {})
            self.do("netext_no_wifi")
            self.assertFalse(t5_netext.state(self.a)["netext"]["no_wifi"])
            self.a._online_phase = "logged_in"
            self.do("search_casual")
            self.assertEqual(client.calls[-1], ("quick", "random", None) if isinstance(client, Client)
                             else ("quick", "random"))

    def test_settings_reach_the_match_driver_launch_and_do_not_replace_its_env(self):
        self.do("netext_set:online_feel:smooth")
        self.do("netext_set:net_line:true")
        driver_module = mock.Mock()
        driver_module.game_files.return_value = []
        launchers = []

        def driver(_client, launch, _log_dir, **_options):
            launchers.append(launch)
            return object()

        driver_module.MatchDriver = driver
        self.a._online_driver_module = lambda: driver_module
        self.a._online_authorized = True
        self.a.start = mock.Mock()
        self.a.game = object()
        T5Match._online_make_driver(self.a, self.client, self.a._online_generation)
        launchers[0](dict(T5_RB_NET_DELAY="2", T5_NET_LINE="0"))
        env = self.a.start.call_args.kwargs["extra_env"]
        self.assertEqual(env["T5_RB_NET_FEEL"], "smooth")
        self.assertEqual(env["T5_NET_LINE"], "1")
        self.assertEqual(env["T5_RB_NET_DELAY"], "2")
        self.assertEqual(env["T5_RB_COST_FILE"], os.path.join(self.directory, "rb_cost.txt"))
        self.do("netext_set:net_line:false")
        self.assertEqual(t5_netext.launch_env(self.a)["T5_NET_LINE"], "0")
        for feel in ("responsive", "balanced", "smooth"):
            self.do("netext_set:online_feel:" + feel)
            self.assertEqual(t5_netext.launch_env(self.a)["T5_RB_NET_FEEL"], feel)

    def test_optional_tags_are_bounded_and_preserved_for_players_and_rooms(self):
        self.assertEqual(self.a._online_player(dict(id="p", name="Rival", area="eu", lang="de"))["lang"], "de")
        room = self.a._online_room_view(dict(id="r", owner=dict(name="Host"), area="sa", lang="pt-BR"))
        self.assertEqual((room["area"], room["lang"]), ("sa", "pt-BR"))
        for bad in (dict(area=["eu"], lang="@secret"), dict(area="wrong", lang="x" * 1000), {}):
            self.assertEqual(t5_netext.tags(bad), {})

    def test_forget_requires_preview_password_and_same_session_and_clears_saved_login(self):
        self.a._online_write_session("local-only", "Tester", self.client.session)
        self.do("netext_forget_confirm")
        self.assertEqual(self.client.calls, [])
        self.do("netext_forget_preview")
        self.assertEqual(self.client.calls, [])
        self.a.set_text_value("online_current_password", "fake-password")
        self.do("netext_forget_preview")
        self.assertEqual(self.client.calls, [("forget", "fake-password", True)])
        self.assertEqual(self.a.text_value("online_current_password"), "")
        state = self.a.online_state()
        self.assertEqual(state["forget_counts"], dict(matches=12, sets=4, friends=2))
        self.assertNotIn("fake-password", str(state))
        self.do("netext_forget_confirm")
        self.assertIn(("forget", "fake-password", False), self.client.calls)
        self.assertEqual(self.a.online_state()["phase"], "offline")
        self.assertEqual(self.a.online_state()["message"], "@netext.forgotten")
        self.assertIsNone(self.a._online_relogin)
        self.assertIsNone(self.a._netext_forget)
        self.assertIsNone(self.a._online_saved())
        self.assertTrue(self.a._online_auto_tried)

    def test_cancel_and_replacement_client_invalidate_preview(self):
        for cancel in (True, False):
            self.a.set_text_value("online_current_password", "fake-password")
            self.do("netext_forget_preview")
            if cancel:
                self.do("netext_forget_cancel")
            else:
                self.a._online_client = Client()
            self.do("netext_forget_confirm")
        self.assertFalse(any(call[-1] is False for call in self.client.calls if call[0] == "forget"))

    def test_removal_clears_an_older_saved_login_when_current_login_is_not_remembered(self):
        self.a._online_write_session("local-only", "Tester", "older-fake-session")
        self.client.session = None
        self.a.set_text_value("online_current_password", "fake-password")
        self.do("netext_forget_preview")
        self.do("netext_forget_confirm")
        self.assertIsNone(self.a._online_saved())
        with open(self.a.online_cfg_path(), encoding="utf-8") as stream:
            self.assertNotIn("local-only", json.load(stream)["sessions"])

    def test_missing_feature_guest_or_failed_password_never_removes(self):
        self.client.welcome = dict(features=[])
        self.a.set_text_value("online_current_password", "fake-password")
        self.do("netext_forget_preview")
        self.assertEqual(self.client.calls, [])
        self.client.welcome = dict(features=["forget_me"])
        self.a._online_account = False
        self.assertFalse(self.a.online_state()["capabilities"]["forget_me"])
        self.do("netext_forget_preview")
        self.assertEqual(self.client.calls, [])
        self.a._online_account = True
        self.client.forget_me = mock.Mock(side_effect=RuntimeError("@online.auth_failed"))
        self.do("netext_forget_preview")
        self.assertIsNone(self.a.online_state()["forget_counts"])
        self.do("netext_forget_confirm")
        self.assertEqual(self.client.forget_me.call_count, 1)

    def test_netinfo_is_optional_and_uses_launcher_language(self):
        self.a.config["language"] = "de"
        self.client.send_netinfo = mock.Mock()
        with mock.patch("importlib.import_module", return_value=mock.Mock(on_wifi=lambda: True)):
            t5_netext.logged_in(self.a, self.client)
        self.client.send_netinfo.assert_called_once_with(wifi=True, area="auto", lang="de")
        self.client.welcome = dict(features=[])
        t5_netext.logged_in(self.a, self.client)
        self.assertEqual(self.client.send_netinfo.call_count, 1)


def fake_page():
    adapter = Lobby()
    adapter.snapshot.update(lobby_snapshot())
    adapter.snapshot["capabilities"].update(online_feel=True, search_options=True, forget_me=True)
    adapter.snapshot.update(netext=dict(max_ping=100, no_wifi=True, steady=True, online_feel="balanced", net_line=False),
                            netext_session=1, forget_counts=None)
    adapter.snapshot["players"][0].update(area="eu", lang="de")
    adapter.snapshot["rooms"][0].update(area="sa", lang="pt-BR")
    adapter.texts["online_current_password"] = "fake-password"
    nav = Nav([Game(adapter.m, adapter)], language="en")
    nav.screen = "hub"
    nav.sec[adapter.m["id"]] = "online"
    return adapter, nav


class NetextNavigation(unittest.TestCase):
    def setUp(self):
        self.a, self.nav = fake_page()

    def choose(self, iid):
        items = self.nav.items()
        target = next(n for n, row in enumerate(items) if row.get("id") == iid)
        for _ in range(len(items) * 2):
            if self.nav.focus_index(self.nav.items()) == target:
                self.nav.act("confirm", device="xbox")
                return
            pad_step(self.nav, target)
        self.fail("pad could not reach " + iid)

    def test_shortcut_and_all_options_are_reachable_by_pad(self):
        self.choose("netext_options")
        self.assertEqual(self.nav.items()[self.nav.focus_index(self.nav.items())]["id"], "netext_max_ping")
        for key in ("max_ping", "no_wifi", "steady", "online_feel", "net_line"):
            self.choose("netext_" + key)
            self.assertTrue(any(call[1].startswith("netext_set:" + key + ":") for call in self.a.calls
                                if call[0] == "online"))
            self.assertEqual(self.nav.items()[self.nav.focus_index(self.nav.items())]["id"], "netext_" + key)
        self.assertNotIn("fake-password", str(self.nav.view()))

    def test_two_confirmations_default_to_no_and_show_server_counts(self):
        self.choose("netext_forget_preview")
        self.assertEqual(self.nav.exit_focus, 0)
        self.nav.act("confirm", device="xbox")
        self.assertNotIn(("online", "netext_forget_preview"), self.a.calls)
        self.choose("netext_forget_preview")
        self.nav.act("right", device="xbox")
        self.nav.act("confirm", device="xbox")
        self.assertIn(("online", "netext_forget_preview"), self.a.calls)
        self.a.snapshot["forget_counts"] = dict(matches=12, sets=4, friends=2)
        self.choose("netext_forget_confirm")
        self.assertEqual(self.nav.exit_focus, 0)
        text = self.nav.view()["dialog"]["text"]
        for value in ("12", "4", "2", "Me"):
            self.assertIn(value, text)
        self.nav.act("right", device="xbox")
        self.nav.act("confirm", device="xbox")
        self.assertIn(("online", "netext_forget_confirm"), self.a.calls)

    def test_cancel_and_stale_dialog_do_not_confirm(self):
        for stale in (False, True):
            self.a.snapshot["forget_counts"] = dict(matches=12, sets=4, friends=2)
            self.choose("netext_forget_confirm")
            if stale:
                self.a.snapshot["netext_session"] += 1
                self.nav.act("right", device="xbox")
                self.nav.act("confirm", device="xbox")
            else:
                self.nav.act("back", device="xbox")
            self.assertNotIn(("online", "netext_forget_confirm"), self.a.calls)

    def test_unsupported_features_are_hidden_but_feel_stays(self):
        self.a.snapshot["capabilities"].update(search_options=False, forget_me=False)
        ids = [row.get("id") for row in self.nav.items()]
        for key in ("options", "max_ping", "no_wifi", "steady", "forget_preview", "forget_confirm"):
            self.assertNotIn("netext_" + key, ids)
        self.assertIn("netext_online_feel", ids)
        self.assertIn("netext_net_line", ids)

    def test_area_and_language_reach_both_tables(self):
        table = self.nav.view()["online"]["body"]["lines"]
        self.assertIn("EU de", str(table))
        self.nav.click_chapter("rooms")
        table = self.nav.view()["online"]["body"]["lines"]
        self.assertIn("SA pt-BR", str(table))

    def test_catalogs_cover_every_label_and_preserve_confirmation_fields(self):
        keys = {key for key in i18n.catalog("en") if key.startswith("netext.")}
        self.assertGreaterEqual(len(keys), 19)
        for lang in i18n.LANGUAGES:
            self.assertTrue(keys.issubset(i18n.catalog(lang)))
            text = i18n.text(lang, "netext.forget_final", name="Tester", matches=12, sets=4, friends=2)
            self.assertNotIn("{", text)
            for value in ("Tester", "12", "4", "2"):
                self.assertIn(value, text)


if __name__ == "__main__":
    unittest.main()
