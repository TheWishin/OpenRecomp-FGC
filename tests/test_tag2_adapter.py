"""The TAG2 adapter (openrecomp/adapters/tag2.py) with a Core that only records requests: no process, no network."""
import builtins
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from openrecomp import adapters, i18n, manifest as mf
from openrecomp.adapters.manifest_game import ManifestGame
from openrecomp.adapters.tag2 import FIGHTERS, Tag2
from openrecomp.adapters.tag2_core import Call, CoreError, user_agent
from openrecomp.nav import Game, Nav

SECRET = "not-a-real-password-1"


class RecordingCore:
    """Stands where tag2_core.Core stands: keeps the requests, answers when the test says so."""

    def __init__(self, problem=""):
        self.why = problem
        self.requests = []
        self.calls = []
        self.on_event = None
        self.closed = False

    def problem(self):
        return self.why

    def request(self, op, **fields):
        self.requests.append((op, fields))
        call = Call(op)
        self.calls.append(call)
        return call

    def call(self, op, timeout=30, **fields):
        self.requests.append((op, fields))
        if op == "settings_set" and fields["values"].get("RenderScale") == 3:
            raise CoreError("error", "Rendering settings are invalid.")
        return dict(dict(SkipStartupIntros=False, GraphicsBackend="d3d12", RenderScale=1, PresentVSync=False), **fields["values"])

    def close(self):
        self.closed = True


class Tag2Case(unittest.TestCase):
    LIVE = True                 # the account / online / Ranked rows are switched on for these tests

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        patcher = mock.patch.dict(os.environ, {"OPENRECOMP_HOME": str(self.base / "home"),
                                               "USERPROFILE": str(self.base / "profile"),
                                               "OPENRECOMP_TAG2_ONLINE": "1" if self.LIVE else "0"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.root = self.base / "profile" / "Downloads" / "TAG2-PC"
        (self.root / "local").mkdir(parents=True)
        (self.root / "Tag2Launcher.exe").write_bytes(b"x")
        self.m = next(m for m in mf.load_all()[0] if m["id"] == "tag2")
        self.config = {}
        self.core = RecordingCore()
        self.popen = mock.Mock()
        self.a = Tag2(dict(self.m, adapter="tag2"), self.config, core=self.core, popen=self.popen)
        self.a.audio_output = lambda: True

    def rows(self):
        return {r["id"]: r for r in self.a.online_items() if r.get("id")}

    def answer(self, result=None, error=None, index=-1):
        self.core.calls[index].finish(result=result, error=error)
        self.assertTrue(self.a.section_poll())

    def sign_in(self):
        (self.root / "local" / "account.dat").write_bytes(b"\x01protected")
        self.a._account = None


class Making(Tag2Case):
    def test_the_bundled_manifest_gets_the_adapter_and_stays_a_manifest_game(self):
        a = adapters.make(self.m, {})
        self.assertIsInstance(a, Tag2)
        self.assertIsInstance(a, ManifestGame)
        self.assertEqual(a.root, str(self.root))
        self.assertTrue(a.ready())
        self.assertFalse(a.online_supported())          # its rows are its own; never the lobby pages

    def test_without_an_install_nothing_of_the_core_is_touched(self):
        a = Tag2(dict(self.m, adapter="tag2"), {"roots": {"tag2": str(self.base / "nowhere")}})
        self.assertFalse(a.found())
        self.assertEqual(a.core_problem(), "@tag2.core_missing")
        self.assertEqual(a.settings(), [])

    def test_user_agent_names_openrecomp_and_the_product(self):
        from openrecomp import __version__
        self.assertEqual(user_agent(), f"OpenRecomp-FGC/{__version__} (tag2-pc)")


class LiveRowsOff(Tag2Case):
    LIVE = False

    def test_by_default_the_online_section_is_the_manifests_and_nothing_is_sent(self):
        self.sign_in()
        self.assertEqual([r["id"] for r in self.a.online_items()], ["own"])
        for row in ("tag2_sign_in", "tag2_register", "tag2_play_online", "tag2_ranked", "tag2_progress"):
            self.a.set_text_value("online_name", "name")
            self.a.set_text_value("online_password", "password")
            self.assertEqual(self.a.run_online(row), "")
        self.assertEqual(self.core.requests, [])
        self.assertEqual(self.core.calls, [])

    def test_the_config_switch_turns_the_rows_on(self):
        self.config["tag2"] = {"online": True}
        self.assertIn("tag2_sign_in", self.rows())

    def test_offline_start_still_goes_through_the_core(self):
        self.a.start()
        self.assertEqual(len(self.core.calls), 1)
        self.popen.assert_not_called()


class WithoutTheCore(Tag2Case):
    def test_an_unknown_core_leaves_the_manifest_behaviour(self):
        self.core.why = "@tag2.core_unknown"
        rows = self.a.online_items()
        self.assertEqual([r["id"] for r in rows], ["tag2_core", "own"])
        self.assertEqual(rows[0]["hint"], "@tag2.core_unknown")
        self.assertTrue(rows[0]["disabled"])
        self.a.start()
        self.popen.assert_called_once()                 # TAG2's own launcher, as before
        self.assertEqual(self.core.requests, [])
        self.assertEqual(self.a.status()["detail"], "@tag2.core_unknown")


class Account(Tag2Case):
    def test_not_signed_in_asks_for_name_and_password(self):
        rows = self.rows()
        self.assertEqual(rows["tag2_status"]["value"], "@tag2.not_signed_in")
        self.assertEqual(rows["online_name"]["opens"], "text:online_name")
        self.assertEqual(rows["online_password"]["opens"], "text:online_password")
        self.assertTrue(rows["tag2_sign_in"]["disabled"])
        self.assertNotIn("tag2_play_online", rows)
        self.assertEqual(self.a.run_online("tag2_sign_in"), "@tag2.need_name_password")
        self.assertEqual(self.core.requests, [])

    def test_the_password_goes_to_the_core_once_and_is_shown_nowhere(self):
        self.a.set_text_value("online_name", " Tester ")
        self.a.set_text_value("online_password", SECRET)
        rows = self.rows()
        self.assertEqual(rows["online_password"]["value"], i18n.literal("•" * len(SECRET)))
        self.assertNotIn(SECRET, json.dumps(self.a.online_items(), default=str))
        self.a.run_online("tag2_sign_in")
        self.assertEqual(self.core.requests, [("sign_in", dict(name="Tester", password=SECRET))])
        self.assertEqual(self.a.text_value("online_password"), "")          # the draft is gone at once
        self.assertNotIn(SECRET, json.dumps(self.a.online_items(), default=str))
        self.assertNotIn(SECRET, json.dumps(self.config))
        self.assertTrue(self.rows()["tag2_sign_in"]["disabled"])            # one request at a time
        with self.assertRaises(RuntimeError):
            self.a._request("account", "sign_in", name="x", password="y")
        self.answer(dict(has_account=True, name="Tester"))
        rows = self.rows()
        self.assertEqual(rows["tag2_status"]["value"], i18n.message("tag2.signed_in_as", name=i18n.literal("Tester")))
        self.assertIn("tag2_play_online", rows)
        self.assertNotIn("online_password", rows)
        self.assertEqual(self.a.section_toast(), i18n.message("tag2.signed_in_as", name=i18n.literal("Tester")))

    def test_create_account_is_the_cores_register(self):
        self.a.set_text_value("online_name", "Tester")
        self.a.set_text_value("online_password", SECRET)
        self.a.run_online("tag2_register")
        self.assertEqual(self.core.requests[0][0], "register")

    def test_a_refused_password_shows_the_cores_sentence_and_keeps_the_form(self):
        self.a.set_text_value("online_name", "Tester")
        self.a.set_text_value("online_password", SECRET)
        self.a.run_online("tag2_sign_in")
        self.answer(error=CoreError("error", "The service refused the request (403)."))
        self.assertEqual(self.a.section_toast(), i18n.literal("The service refused the request (403)."))
        self.assertIn("online_name", self.rows())
        self.assertEqual(len(self.core.requests), 1)

    def test_a_rejected_saved_sign_in_asks_to_sign_in_again_and_never_retries(self):
        self.sign_in()
        self.a.run_online("tag2_play_online")
        self.answer(error=CoreError("sign_in", "The service refused the request (401)."))
        self.assertEqual(self.a.section_toast(), "@tag2.sign_in_again")
        rows = self.rows()
        self.assertEqual(rows["tag2_status"]["value"], "@tag2.sign_in_again")
        self.assertIn("online_password", rows)              # the form is back
        self.assertNotIn("tag2_play_online", rows)          # nothing that would use the dead sign-in
        self.assertNotIn("tag2_ranked", rows)
        for _ in range(50):                                 # time passes: no request by itself
            self.a.section_poll()
            self.a.online_items()
        self.assertEqual([op for op, _f in self.core.requests], ["play"])
        self.assertFalse(self.a.running())

    def test_the_protected_account_file_is_never_opened(self):
        self.sign_in()
        real = builtins.open
        opened = []

        def watching(path, *args, **kwargs):
            opened.append(str(path))
            return real(path, *args, **kwargs)
        with mock.patch.object(builtins, "open", watching):
            self.a.online_items()
            self.a.status()
            self.a.settings()
        self.assertFalse([p for p in opened if p.lower().endswith(".dat")])

    def test_another_account_shows_the_form_beside_the_signed_in_rows(self):
        self.sign_in()
        self.assertNotIn("online_name", self.rows())
        self.a.run_online("tag2_other_account")
        rows = self.rows()
        self.assertIn("online_name", rows)
        self.assertIn("tag2_play_online", rows)
        self.assertEqual(self.core.requests, [])


class Playing(Tag2Case):
    def test_offline_start_is_the_cores_offline_play(self):
        self.assertEqual(self.a.start(extra_env={"X": "1"}), 0)
        self.assertEqual(self.core.requests, [("play", dict(mode="offline"))])
        self.popen.assert_not_called()
        self.assertTrue(self.a.running())                   # while the Core prepares shaders
        self.core.calls[0].status = "Preparing portable shader cache..."
        self.assertTrue(self.a.section_poll())
        self.assertEqual(self.a.status()["detail"], i18n.literal("Preparing portable shader cache..."))
        with self.assertRaises(RuntimeError):
            self.a.start()
        self.answer(dict(pid=4242, kind="offline"))
        self.assertTrue(self.a.running())
        self.core.on_event(dict(event="game_exit", pid=1))  # some other process: still ours
        self.assertTrue(self.a.running())
        self.core.on_event(dict(event="game_exit", pid=4242))
        self.assertFalse(self.a.running())
        self.assertTrue(self.a.section_poll())

    def test_a_game_that_is_not_built_says_where_to_build(self):
        self.a.start()
        self.answer(error=CoreError("build", "Use Updates > Build game to compile your own ISO / XEX before playing."))
        self.assertFalse(self.a.running())
        self.assertEqual(self.a.section_toast(), "@tag2.build_needed")
        self.assertEqual(self.a.status()["detail"], "@tag2.build_needed")

    def test_stop_asks_the_window_then_ends_the_game(self):
        self.a.STOP_WAIT = 0.05
        self.a.start()
        self.answer(dict(pid=4242, kind="offline"))
        self.a.stop()
        self.assertEqual(self.core.requests[-1], ("stop", {}))
        deadline = time.time() + 5
        while self.core.requests[-1] != ("stop", dict(force=True)) and time.time() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.core.requests[-1], ("stop", dict(force=True)))

    def test_their_launcher_is_not_opened_beside_our_game(self):
        self.a.start()
        with self.assertRaises(RuntimeError):
            self.a.open_native()
        self.popen.assert_not_called()

    def test_closing_the_launcher_closes_the_host(self):
        self.a.section_close()
        self.assertTrue(self.core.closed)


class Ranked(Tag2Case):
    def setUp(self):
        super().setUp()
        self.sign_in()

    def choose(self, first, second):
        self.a.pick_fighter_slot(0)
        self.a.set_fighter(str(first))
        self.a.pick_fighter_slot(1)
        self.a.set_fighter(str(second))

    def test_ranked_needs_two_different_real_fighters(self):
        self.assertTrue(self.rows()["tag2_ranked"]["disabled"])
        self.assertEqual(self.a.run_online("tag2_ranked"), "@tag2.choose_team")
        self.choose(9, 9)
        self.assertIsNone(self.a.team())
        self.a.set_fighter("random")                        # Random is no TAG2 fighter: the choice stays
        self.assertEqual(self.a.chosen_fighter(), "9")
        self.a.set_fighter(str(len(FIGHTERS)))
        self.assertEqual(self.a.chosen_fighter(), "9")
        self.assertEqual(self.core.requests, [])
        self.choose(9, 14)
        self.assertEqual(self.a.team(), [9, 14])
        rows = self.rows()
        self.assertFalse(rows["tag2_ranked"]["disabled"])
        self.assertEqual(rows["tag2_team_0"]["value"], i18n.literal("Jin Kazama"))
        self.assertEqual(rows["tag2_team_1"]["opens"], "fighters:1")
        self.assertEqual(self.config["tag2"]["team"], [9, 14])

    def test_the_request_carries_the_team_and_only_outfits_the_game_named(self):
        self.choose(9, 14)
        self.assertEqual(self.a.costumes("9"), [])          # before the game named any: the default only
        self.a.run_online("tag2_ranked")
        self.assertEqual(self.core.requests, [("ranked", dict(team=[9, 14], costumes=[-1, -1]))])
        self.assertIn("tag2_ranked_cancel", self.rows())
        self.a.run_online("tag2_ranked_cancel")
        self.assertEqual(self.core.requests[-1], ("ranked_cancel", {}))
        self.answer(dict(pid=7, kind="ranked", outcome="searching", code="", started_game=True,
                         team=[dict(id=9, slots=[0, 2]), dict(id=14, slots=[])]), index=0)
        self.assertEqual(self.a.section_toast(), "@tag2.ranked_searching")
        self.assertTrue(self.a.running())
        self.assertEqual([c["button"] for c in self.a.costumes("9")], [1, 2, 4])
        self.assertEqual(self.a.costumes("14"), [])
        self.a.set_costume("9", 4)
        self.assertEqual(self.a.chosen_costume("9"), 4)
        self.a.run_online("tag2_ranked")                    # again from the menu of the game we own
        self.assertEqual(self.core.requests[-1], ("ranked", dict(team=[9, 14], costumes=[2, -1])))

    def test_a_refusal_of_the_game_is_shown_as_it_is(self):
        self.choose(9, 14)
        self.a.run_online("tag2_ranked")
        self.answer(dict(pid=7, kind="ranked", outcome="refused", code="in_match", team=[]))
        self.assertEqual(self.a.section_toast(), i18n.message("tag2.ranked_answer", answer=i18n.literal("in_match")))

    def test_ranked_is_not_offered_beside_an_offline_game(self):
        self.choose(9, 14)
        self.a.start()
        self.answer(dict(pid=5, kind="offline"))
        self.assertTrue(self.rows()["tag2_ranked"]["disabled"])
        self.assertTrue(self.rows()["tag2_play_online"]["disabled"])

    def test_the_record_is_asked_only_when_pressed(self):
        self.a.online_items()
        self.assertEqual(self.core.requests, [])
        self.a.run_online("tag2_progress")
        self.answer(dict(ranked_wins="3", ranked_losses="1", player_wins="5", player_losses="2",
                         ranks=[dict(character=9, rank=4, points=120)]))
        rows = self.rows()["tag2_progress"]["detail"]["rows"]
        self.assertEqual(rows[0], dict(k="@tag2.record", v=i18n.literal("3 / 1")))
        self.assertEqual(rows[2]["k"], i18n.literal("Jin Kazama"))
        self.assertNotIn("identity", json.dumps(rows))


class Settings(Tag2Case):
    def test_values_come_from_tag2s_file_and_changes_go_through_the_core(self):
        (self.root / "local" / "launcher-settings.json").write_text(
            json.dumps(dict(PlayerName="Tester", GraphicsBackend="vulkan", RenderScale=9)), encoding="utf-8")
        by_id = {s["id"]: s for s in self.a.settings()}
        self.assertEqual(by_id["tag2_backend"]["value"], "vulkan")
        self.assertEqual(by_id["tag2_scale"]["value"], 1)                   # an unknown value shows the default
        self.assertEqual(self.a.quick_settings(), list(by_id))
        self.a.set_setting("tag2_skip_intros", True)
        self.assertEqual(self.core.requests, [("settings_set", dict(values=dict(SkipStartupIntros=True)))])
        self.assertTrue({s["id"]: s for s in self.a.settings()}["tag2_skip_intros"]["value"])
        with self.assertRaises(RuntimeError):
            self.a.set_setting("tag2_backend", "opengl")
        with self.assertRaises(RuntimeError) as refused:
            self.a.set_setting("tag2_scale", 3)
        self.assertEqual(refused.exception.args[0], i18n.literal("Rendering settings are invalid."))
        self.sign_in()
        self.assertEqual(self.rows()["tag2_status"]["value"], i18n.message("tag2.signed_in_as", name=i18n.literal("Tester")))


class InTheLauncher(Tag2Case):
    def nav(self):
        game = Game(self.m, self.a)
        nav = Nav([game], language="en")
        nav.dry = False
        nav.game = game
        return nav, game

    def test_rows_reach_the_online_section_and_the_team_grid_knows_its_place(self):
        self.sign_in()
        nav, game = self.nav()
        items = {it["id"]: it for it in nav._items_online_rows(game) if it.get("id")}
        self.assertIsNone(items["tag2_status"]["run"])
        self.assertIsNone(items["tag2_ranked"]["run"])       # no team yet: a disabled row runs nothing
        items["tag2_team_1"]["run"]()
        self.assertEqual(nav.overlay, "fighters")
        self.assertEqual(self.a._pick, 1)
        self.assertEqual(len(nav._fighter_list()), len(FIGHTERS) + 1)
        items["tag2_progress"]["run"]()
        self.assertEqual(self.core.requests, [("progress", {})])

    def test_an_answer_that_comes_later_is_said_by_the_timer(self):
        self.sign_in()
        nav, game = self.nav()
        self.a.run_online("tag2_play_online")
        self.assertTrue(nav.poll_online())                  # the row now says it is working
        self.assertFalse(nav.poll_online())
        self.core.calls[0].finish(error=CoreError("sign_in", "401"))
        self.assertTrue(nav.poll_online())
        self.assertEqual(nav.toast, "@tag2.sign_in_again")
        self.assertFalse(nav.poll_online())

    def test_no_audio_output_is_a_warning_the_player_can_confirm(self):
        self.sign_in()
        self.a.pick_fighter_slot(0), self.a.set_fighter("9")
        self.a.pick_fighter_slot(1), self.a.set_fighter("14")
        nav, game = self.nav()
        self.a.audio_output = lambda: False
        nav.start_game(game)                                 # Play offline
        self.assertEqual((nav.overlay, nav.confirm_kind), ("dialog", "start_warning"))
        self.assertEqual(nav.view()["dialog"]["title"], i18n.catalog("en")["dialog.start_warning.title"])
        self.assertEqual(nav.view()["dialog"]["text"], i18n.catalog("en")["tag2.no_audio"])
        self.assertEqual(self.core.requests, [])             # nothing started while the question is open
        nav.act("confirm")                                   # No is in focus
        self.assertIsNone(nav.overlay)
        self.assertEqual(self.core.requests, [])
        nav.start_game(game)
        nav.act("right")
        nav.act("confirm")                                   # Yes: the start goes ahead, unchanged
        self.assertEqual(self.core.requests, [("play", dict(mode="offline"))])
        self.answer(error=CoreError("error", "x"))
        for row, request in (("tag2_play_online", ("play", dict(mode="online"))),
                             ("tag2_ranked", ("ranked", dict(team=[9, 14], costumes=[-1, -1])))):
            items = {it["id"]: it for it in nav._items_online_rows(game) if it.get("id")}
            items[row]["run"]()
            self.assertEqual(nav.confirm_kind, "start_warning")
            nav.act("right")
            nav.act("confirm")
            self.assertEqual(self.core.requests[-1], request)
            self.answer(error=CoreError("error", "x"))

    def test_no_warning_with_an_audio_output_or_when_windows_cannot_tell(self):
        self.sign_in()
        nav, game = self.nav()
        for answer in (True, None):
            self.a.audio_output = lambda answer=answer: answer
            nav.start_game(game)
            self.assertIsNone(nav.overlay)
            self.assertEqual(self.core.requests[-1], ("play", dict(mode="offline")))
            self.answer(error=CoreError("error", "x"))
        self.a.audio_output = lambda: False
        items = {it["id"]: it for it in nav._items_online_rows(game) if it.get("id")}
        items["tag2_progress"]["run"]()                      # a row that starts no game asks nothing
        self.assertIsNone(nav.overlay)
        self.assertEqual(self.a.start_warning("tag2_sign_in"), "")
        self.core.why = "@tag2.core_unknown"                 # their launcher starts, not the game: no warning
        self.assertEqual(self.a.start_warning("start"), "")

    def test_every_text_of_the_adapter_is_in_every_catalog(self):
        import re
        source = Path(adapters.__file__).with_name("tag2.py").read_text(encoding="utf-8")
        source += Path(adapters.__file__).with_name("tag2_core.py").read_text(encoding="utf-8")
        keys = set(re.findall(r'"@?(tag2\.[a-z_.]+)"', source))
        self.assertGreater(len(keys), 30)
        for code in ("en", "de", "es", "fr", "ja", "ko", "pt-BR"):
            self.assertFalse(sorted(keys - set(i18n.catalog(code))), code)


if __name__ == "__main__":
    unittest.main()
