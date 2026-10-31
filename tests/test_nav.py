"""The launcher driven by actions alone, with a fake game: every test records what the game was asked to do."""
import collections
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openrecomp import manifest as mf  # noqa: E402
from openrecomp.adapters.base import Adapter, Generic, Missing  # noqa: E402
from openrecomp.nav import GRID_COLS, Game, Nav, window  # noqa: E402
from openrecomp.pad import Pads, ps_held, xinput_held  # noqa: E402


def manifest(gid="a", sections=("play", "online", "build", "replays", "settings"), **kw):
    return mf.validate(dict(dict(id=gid, title=gid.upper(), numeral="1", accent="#112233", adapter="generic", exe="x.exe", sections=list(sections)), **kw))


class Fake(Adapter):
    native_label = "Fake-Launcher"

    def __init__(self, m, is_ready=True):
        super().__init__(m)
        self.calls = []
        self.is_ready = is_ready
        self.values = dict(res="a")
        self.fighter = "random"
        self.is_running = False
        self.build_problem = ""

    def found(self):
        return True

    def ready(self):
        return self.is_ready

    def status(self):
        return dict(status="Ready" if self.is_ready else "Not built yet", version="v1", players="No", last="heute", detail="Detail")

    def start(self, extra_env=None):
        self.calls.append(("start", extra_env))
        self.is_running = True

    def running(self):
        return self.is_running

    def stop(self):
        self.calls.append(("stop",))
        self.is_running = False

    def open_native(self):
        self.calls.append(("native",))

    def settings(self):
        return [dict(id="res", label="Auflösung", options=[("a", "A"), ("b", "B"), ("c", "C")], value=self.values["res"], hint="h", lead="l")]

    def set_setting(self, sid, value):
        self.values[sid] = value
        self.calls.append(("set", sid, value))

    def quick_settings(self):
        return ["res"]

    def online_items(self):
        return [dict(kind="heading", label="Ich"),
                dict(kind="action", id="fighter", label="Fighter", value=self.fighter, verb="Change", opens="fighters", hint="h", detail=dict(title="c", rows=[])),
                dict(kind="action", id="ranked", label="Ranked", verb="Search", hint="h", detail=dict(title="r", rows=[])),
                dict(kind="action", id="name", label="Name", verb="Change", opens="text:name", hint="h", detail=dict(title="n", rows=[]))]

    def run_online(self, item_id):
        self.calls.append(("online", item_id))
        return "ok"

    def fighters(self):
        return [dict(key=f"f{i}", name=f"F{i}", image="") for i in range(34)]

    def chosen_fighter(self):
        return self.fighter

    def set_fighter(self, key):
        self.fighter = key
        self.calls.append(("fighter", key))

    def main_fighter(self):
        return "F3"

    def replays(self):
        return [dict(id=str(i), label=f"A – B {i}", when="10:00", date="d", group="G" + str(i // 2), opponent="O", netcode="Rollback", result="Sieg 3:1", images=[]) for i in range(12)]

    def play_replay(self, replay_id, extra_env=None):
        self.calls.append(("replay", replay_id))

    def sources(self):
        return [dict(id="iso", label="ISO", value="Missing", ok=False, kind="file", exts=[".iso"], dirs=[], hint="h")]

    def set_source(self, sid, path):
        self.calls.append(("source", sid, path))
        return "gut"

    def build_ready(self):
        return self.build_problem

    def build_start(self, force=False):
        self.calls.append(("build", force))

    def text_value(self, tid):
        return "alt"

    def set_text_value(self, tid, value):
        self.calls.append(("text", tid, value))


class Base(unittest.TestCase):
    def setUp(self):
        self.a = Fake(manifest("a"))
        self.b = Fake(manifest("b", sections=("play", "build", "settings")), is_ready=False)
        self.quit = []
        self.nav = Nav([Game(self.a.m, self.a), Game(self.b.m, self.b)], on_quit=lambda: self.quit.append(1), language="en")

    def press(self, *actions):
        for a in actions:
            self.nav.act(a)
        self.nav.view()         # every state must also draw


class Shelf(Base):
    def test_slots_follow_the_games(self):
        ids = self.nav.tile_ids()
        self.assertEqual(ids[:2], ["a", "b"])
        self.assertEqual(len(ids), mf.TOTAL_SLOTS)

    def test_a_full_shelf_keeps_one_free_slot(self):
        games = [Game(manifest(f"g{i}"), Fake(manifest(f"g{i}"))) for i in range(mf.TOTAL_SLOTS + 2)]
        nav = Nav(games)
        self.assertEqual(len(nav.tile_ids()), mf.TOTAL_SLOTS + 3)
        self.assertTrue(nav.tile_ids()[-1].startswith("slot"))

    def test_the_focused_tile_is_always_on_screen(self):
        games = [Game(manifest(f"g{i}"), Fake(manifest(f"g{i}"))) for i in range(9)]
        nav = Nav(games)
        for _ in range(len(nav.tile_ids())):
            shelf = nav.view()["shelf"]
            left = shelf["x"]
            for t in shelf["tiles"]:
                if t["focused"]:
                    self.assertGreaterEqual(left, 0)
                    self.assertLessEqual(left + t["w"], 1920)
                left += t["w"] + 2
            self.assertEqual(sum(t["w"] for t in shelf["tiles"]) + 2 * (len(shelf["tiles"]) - 1), shelf["w"])
            nav.act("right")

    def test_a_game_not_built_opens_at_build(self):
        self.press("right", "confirm")
        self.assertEqual((self.nav.game.id, self.nav.section()), ("b", "build"))

    def test_start_plays_only_a_ready_game(self):
        self.press("play")
        self.assertEqual(self.a.calls, [("start", None)])

    def test_back_asks_and_no_is_the_default(self):
        self.press("back", "confirm")
        self.assertEqual(self.quit, [])
        self.assertIsNone(self.nav.overlay)
        self.press("back", "right", "confirm")
        self.assertEqual(self.quit, [1])


class Sections(Base):
    def test_only_the_manifests_sections_exist(self):
        self.press("right", "confirm")
        self.assertEqual([t["id"] for t in self.nav.view()["tabs"]], ["play", "build", "settings"])

    def test_tabs_wrap_and_focus_is_remembered(self):
        self.press("confirm", "next")
        self.assertEqual(self.nav.section(), "online")
        self.press("down", "prev", "next")
        self.assertEqual(self.nav.focus["a:online"], 2)
        self.press("prev", "prev")
        self.assertEqual(self.nav.section(), "settings")

    def test_back_returns_to_the_same_game(self):
        self.press("right", "confirm", "back")
        self.assertEqual((self.nav.screen, self.nav.start_focus), ("start", 1))

    def test_a_cycler_changes_the_game_setting_both_ways(self):
        self.press("confirm", "down", "right")
        self.assertEqual(self.a.values["res"], "b")
        self.press("left", "left")
        self.assertEqual(self.a.values["res"], "c")

    def test_headings_can_not_take_the_focus(self):
        self.press("confirm", "next")
        rows = self.nav.view()["rows"]
        self.assertTrue(rows[0]["heading"])
        self.assertTrue(rows[1]["focused"])
        self.press("up")
        self.assertTrue(self.nav.view()["rows"][1]["focused"])

    def test_every_section_of_every_state_draws(self):
        for game_index in (0, 1):
            for _ in range(5):
                self.nav.game = self.nav.games[game_index]
                self.nav.screen = "hub"
                v = self.nav.view()
                self.assertTrue(v["rows"])
                self.assertTrue(v["prompts"])
                self.nav.act("next")

    def test_online_action_reaches_the_game(self):
        self.press("confirm", "next", "down", "confirm")
        self.assertEqual(self.a.calls, [("online", "ranked")])

    def test_a_game_saying_no_becomes_a_message(self):
        def no(extra_env=None):
            raise RuntimeError("Nein.")
        self.a.start = no
        self.press("play")
        self.assertIn("Nein.", self.nav.view()["toast"])
        self.assertIn("try again", self.nav.view()["toast"])


class Fighters(Base):
    def setUp(self):
        super().setUp()
        self.press("confirm", "next", "confirm")

    def test_random_first_then_the_fighters(self):
        cells = self.nav.view()["grid"]["cells"]
        self.assertEqual(len(cells), 35)
        self.assertTrue(cells[0]["random"])
        self.assertTrue(cells[4]["main"])

    def test_it_opens_on_the_chosen_one(self):
        self.a.fighter = "f7"
        self.press("back", "confirm")
        self.assertEqual(self.nav.grid_focus, 8)

    def test_moves_and_picks(self):
        self.press("right", "down", "confirm")
        self.assertEqual(self.a.fighter, f"f{GRID_COLS}")
        self.assertIsNone(self.nav.overlay)

    def test_down_from_above_the_gap_lands_on_the_last(self):
        self.nav.grid_focus = 3 * GRID_COLS - 1
        self.press("down")
        self.assertEqual(self.nav.grid_focus, 34)

    def test_back_changes_nothing(self):
        self.press("right", "back")
        self.assertEqual(self.a.calls, [])


class Replays(Base):
    def test_results_hidden_until_asked(self):
        self.press("confirm", "next", "next", "next")
        self.assertEqual(self.nav.section(), "replays")
        rows = {r["k"]: r["v"] for r in self.nav.view()["detail"]["rows"]}
        self.assertEqual(rows["Result"], "Hidden")
        self.press("x")
        rows = {r["k"]: r["v"] for r in self.nav.view()["detail"]["rows"]}
        self.assertEqual(rows["Result"], "Sieg 3:1")

    def test_a_long_list_scrolls_and_never_ends_on_a_heading(self):
        self.press("confirm", "next", "next", "next")
        for _ in range(20):
            v = self.nav.view()
            self.assertLessEqual(len(v["rows"]), 9)
            self.assertFalse(v["rows"][-1]["heading"])
            self.assertTrue(any(r["focused"] for r in v["rows"]))
            self.press("down")

    def test_confirm_plays_the_focused_one(self):
        self.press("confirm", "next", "next", "next", "down", "confirm")
        self.assertEqual(self.a.calls, [("replay", "1")])


class Build(Base):
    def test_a_missing_file_stops_the_build(self):
        self.a.build_problem = "Fehlt noch."
        self.press("confirm", "next", "next", "down", "confirm")
        self.assertEqual(self.a.calls, [])
        self.assertEqual(self.nav.toast, "Fehlt noch.")

    def test_rebuild_needs_the_whole_hold(self):
        self.press("confirm", "next", "next", "down", "down", "confirm")
        self.nav.tick(1.0)
        self.nav.release("confirm")
        self.nav.tick(1.0)
        self.assertEqual(self.a.calls, [])
        self.press("confirm")
        self.nav.tick(0.8)
        self.nav.tick(0.8)
        self.assertEqual(self.a.calls, [])
        self.assertEqual(self.nav.overlay, "dialog")
        self.press("right", "confirm")
        self.assertEqual(self.a.calls, [("build", True)])

    def test_the_picker_only_shows_matching_files(self):
        with tempfile.TemporaryDirectory(dir=os.path.dirname(os.path.dirname(__file__))) as d:
            for name in ("game.iso", "notes.txt", "SECOND.ISO"):
                open(os.path.join(d, name), "w").close()
            os.mkdir(os.path.join(d, "sub"))
            self.press("confirm", "next", "next", "confirm")
            self.nav.picker["dir"] = d
            names = [r["name"] for r in self.nav.view()["picker"]["rows"]]
            self.assertEqual(names, ["..", "game.iso", "SECOND.ISO", "sub"])
            self.nav.picker["focus"] = 1
            self.press("confirm")
            self.assertEqual(self.a.calls, [("source", "iso", os.path.join(d, "game.iso"))])
            self.assertEqual(self.nav.toast, "gut")


class Keyboard(Base):
    def test_typing_by_pad(self):
        self.press("confirm", "next", "down", "down", "confirm", "x", "x", "x")
        self.assertEqual(self.nav.overlay, "osk")
        self.press("right", "confirm", "down", "confirm", "play")
        self.assertEqual(self.a.calls, [("text", "name", "WS")])

    def test_back_keeps_the_old_text(self):
        self.press("confirm", "next", "down", "down", "confirm", "x", "back")
        self.assertEqual(self.a.calls, [])

    def test_the_action_row_maps_back_to_the_letters(self):
        self.press("confirm", "next", "down", "down", "confirm", "down", "down", "down", "up")
        self.assertEqual(self.nav.osk["row"], 3)


class DryRun(Base):
    def test_a_dry_run_never_reaches_the_game(self):
        self.nav.dry = True
        self.press("play", "confirm", "down", "right", "up", "confirm", "next", "confirm", "confirm", "down", "confirm")
        self.press("next", "confirm", "next", "down", "confirm", "next", "right", "social", "confirm", "back", "back", "back", "right", "confirm")
        self.assertEqual(self.a.calls, [])
        self.assertEqual(self.b.calls, [])
        self.assertEqual(self.quit, [])


class Pad(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.held = set()

        class Reader:
            kind = "xbox"

            def read(inner):
                return set(self.held)
        self.pads = Pads([Reader()], clock=lambda: self.now)

    def test_edges(self):
        self.held = {"A"}
        self.assertEqual(self.pads.poll(), [("confirm", "down")])
        self.assertEqual(self.pads.poll(), [])
        self.held = set()
        self.assertEqual(self.pads.poll(), [("confirm", "up")])

    def test_directions_repeat_buttons_do_not(self):
        self.held = {"DDOWN", "A"}
        self.pads.poll()
        self.now = 0.5
        self.assertEqual(self.pads.poll(), [("down", "down")])
        self.now = 0.55
        self.assertEqual(self.pads.poll(), [])
        self.now = 0.7
        self.assertEqual(self.pads.poll(), [("down", "down")])

    def test_a_press_held_across_the_game_is_not_a_new_one(self):
        self.held = {"A"}
        self.pads.poll()
        self.pads.forget()
        self.assertEqual(self.pads.poll(), [])
        self.held = set()
        self.assertEqual(self.pads.poll(), [("confirm", "up")])

    def test_suppression_without_held_buttons_has_no_release_edges(self):
        self.pads.suppress()
        self.pads.suppress()
        self.assertEqual(self.pads.poll(), [])
        self.held = {"A"}
        self.assertEqual(self.pads.poll(), [("confirm", "down")])

    def test_a_direction_first_held_while_away_requires_release_before_repeating(self):
        self.pads.forget()
        self.held = {"DDOWN"}
        self.assertEqual(self.pads.poll(), [])
        self.now = 1.0
        self.assertEqual(self.pads.poll(), [])
        self.held = set()
        self.assertEqual(self.pads.poll(), [("down", "up")])
        self.held = {"DDOWN"}
        self.assertEqual(self.pads.poll(), [("down", "down")])
        self.now = 1.5
        self.assertEqual(self.pads.poll(), [("down", "down")])

    def test_the_stick_is_a_dpad(self):
        self.assertEqual(xinput_held(0, 30000, 0), {"DRIGHT"})
        self.assertEqual(xinput_held(0, -30000, 30000), {"DLEFT", "DUP"})
        self.assertEqual(xinput_held(0, 5000, -5000), set())
        self.assertEqual(xinput_held(0x1000 | 0x0100, 0, 0), {"A", "LB"})


class PlayStation(unittest.TestCase):
    """The launcher's mapping accepts plain device data, without reading any game install."""

    def held(self, *names):
        Device = collections.namedtuple("Device", "pressed")
        return ps_held([Device(names)])

    def test_cross_confirms_and_circle_goes_back(self):
        self.assertEqual(self.held("B2"), {"A"})
        self.assertEqual(self.held("B3"), {"B"})
        self.assertEqual(self.held("B1"), {"X"})
        self.assertEqual(self.held("B4"), {"Y"})

    def test_hat_and_stick_are_directions(self):
        self.assertEqual(self.held("HAT_UP"), {"DUP"})
        self.assertEqual(self.held("HAT_DOWN"), {"DDOWN"})
        self.assertEqual(self.held("Y-"), {"DUP"})
        self.assertEqual(self.held("X+"), {"DRIGHT"})
        self.assertEqual(self.held(), set())


class Badge(unittest.TestCase):
    def test_each_game_says_what_kind_of_recomp_it_is(self):
        manifests, _problems = mf.load_all([mf.BUILTIN_DIR])
        kinds = {m["id"]: m["platform"] for m in manifests}
        self.assertEqual(kinds, {"t5dr": "PS3", "t4": "PS2"})

    def test_the_shelf_and_the_hub_show_it(self):
        m = manifest("a", platform="PS3")
        nav = Nav([Game(m, Fake(m))])
        self.assertEqual(nav.view()["shelf"]["tiles"][0]["badge"], "PS3 RECOMP")
        self.assertEqual(nav.view()["shelf"]["tiles"][-1]["badge"], "")
        nav.act("confirm")
        self.assertEqual(nav.view()["badge"], "PS3 RECOMP")

    def test_no_platform_no_badge(self):
        m = manifest("a")
        self.assertEqual(Nav([Game(m, Fake(m))]).view()["shelf"]["tiles"][0]["badge"], "")


class Manifests(unittest.TestCase):
    def test_the_shipped_games_are_valid(self):
        manifests, problems = mf.load_all([mf.BUILTIN_DIR])
        self.assertEqual(problems, [])
        self.assertEqual([m["id"] for m in manifests], ["t4", "t5dr"])
        self.assertIn("online", manifests[0]["sections"])
        self.assertIn("online", manifests[1]["sections"])

    def test_manifest_order_takes_priority_over_filename_and_title(self):
        entries = {"a.json": manifest("a", title="A", order=20),
                   "z.json": manifest("z", title="Z", order=10)}
        with mock.patch.object(mf.os, "listdir", return_value=["a.json", "z.json"]), mock.patch.object(
                mf, "load_file", side_effect=lambda path: entries[os.path.basename(path)]):
            manifests, problems = mf.load_all(["games"])
        self.assertEqual(problems, [])
        self.assertEqual([m["id"] for m in manifests], ["z", "a"])

    def test_later_manifest_replaces_the_same_id_before_sorting(self):
        original = manifest("a", title="A", order=10)
        replacement = manifest("a", title="Changed", order=30)
        other = manifest("b", title="B", order=20)
        with mock.patch.object(mf.os, "listdir", side_effect=[["a.json", "b.json"], ["a.json"]]), mock.patch.object(
                mf, "load_file", side_effect=[original, other, replacement]):
            manifests, problems = mf.load_all(["builtin", "user"])
        self.assertEqual(problems, [])
        self.assertEqual(manifests, [other, replacement])

    def test_bad_ones_are_named_not_fatal(self):
        with tempfile.TemporaryDirectory(dir=os.path.dirname(os.path.dirname(__file__))) as d:
            with open(os.path.join(d, "bad.json"), "w", encoding="utf-8") as f:
                f.write("{")
            with open(os.path.join(d, "nofield.json"), "w", encoding="utf-8") as f:
                f.write('{"id": "x"}')
            manifests, problems = mf.load_all([d])
            self.assertEqual(manifests, [])
            self.assertEqual(len(problems), 2)

    def test_install_puts_a_players_game_in_the_user_folder(self):
        with tempfile.TemporaryDirectory(dir=os.path.dirname(os.path.dirname(__file__))) as d:
            os.environ["OPENRECOMP_HOME"] = d
            try:
                src = os.path.join(d, "mine.json")
                with open(src, "w", encoding="utf-8") as f:
                    json.dump(dict(schema_version=1, id="mine", title="Mein Spiel", numeral="M",
                                   accent="#00FF00", adapter="generic", exe="game.exe", platform="PC",
                                   author="Example Author", repository="example/recomp", license="MIT",
                                   credits=["Example Author"]), f)
                m = mf.install(src)
                self.assertEqual(m["sections"], ["play", "settings"])
                self.assertTrue(os.path.isfile(os.path.join(d, "games", "mine.json")))
            finally:
                del os.environ["OPENRECOMP_HOME"]

    def test_unknown_values_are_refused(self):
        base = dict(id="x", title="X", numeral="1", accent="#112233", adapter="generic", exe="x")
        for change in (dict(adapter="nope"), dict(accent="red"), dict(id="a/b"), dict(sections=["nope"])):
            with self.assertRaises(mf.ManifestError):
                mf.validate(dict(base, **change))
        with self.assertRaises(mf.ManifestError):
            mf.validate(dict(base, exe=""))


class Adapters(unittest.TestCase):
    def test_generic_is_ready_when_its_file_is_there(self):
        with mock.patch("openrecomp.adapters.base.os.path.isfile", return_value=True):
            self.assertTrue(Generic(manifest(exe="fake.exe")).ready())
        with mock.patch("openrecomp.adapters.base.os.path.isfile", return_value=False):
            self.assertFalse(Generic(manifest(exe="fake.exe")).ready())

    def test_missing_lets_the_player_point_at_the_folder(self):
        config = {}
        m = Missing(manifest(), config)
        self.assertEqual(m.sources()[0]["kind"], "folder")
        self.assertEqual(m.set_source("folder", "D:\\x"), "reload")
        self.assertEqual(config["roots"]["a"], "D:\\x")

    def test_a_missing_game_still_draws_everywhere(self):
        m = Missing(manifest(), {})
        nav = Nav([Game(m.m, m)])
        nav.act("confirm")
        for _ in range(6):
            nav.view()
            nav.act("next")


class Logo(unittest.TestCase):
    def test_the_logo_needs_no_font_and_no_picture(self):
        assets = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "openrecomp", "ui", "assets")
        for name in ("logo-mark.svg", "logo-mark-light.svg", "logo-wordmark.svg", "logo-wordmark-light.svg", "icon.svg"):
            with open(os.path.join(assets, name), encoding="utf-8") as f:
                text = f.read()
            self.assertTrue(text.startswith("<svg"), name)
            self.assertNotIn("<text", text, name)
            self.assertNotIn("<image", text, name)
        self.assertTrue(os.path.isfile(os.path.join(assets, "icon.ico")))


class Window(unittest.TestCase):
    def test_window(self):
        self.assertEqual(window(5, 3, 9), 0)
        self.assertEqual(window(20, 0, 9), 0)
        self.assertEqual(window(20, 10, 9), 6)
        self.assertEqual(window(20, 19, 9), 11)


if __name__ == "__main__":
    unittest.main()
