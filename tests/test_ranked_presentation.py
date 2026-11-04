"""Ranked and ranking UI snapshots never search or infer missing server results."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

from openrecomp import i18n
from openrecomp.adapters import t5_profiles
from test_online_hierarchy import hierarchy_nav
from test_t5_profiles import Owner


class OnlineTableCompilation(unittest.TestCase):
    def test_repeated_table_compiles_and_renders_in_a_bounded_qt_process(self):
        ui = Path(__file__).resolve().parents[1] / "openrecomp/ui"
        script = '''
import sys
from pathlib import Path
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
app = QGuiApplication([])
engine = QQmlApplicationEngine()
warnings = []
engine.warnings.connect(lambda messages: warnings.extend(m.toString() for m in messages))
engine.loadData(b'import QtQuick\\nimport QtQuick.Window\\nimport "."\\nWindow { visible: true; width: 500; height: 500; OnlineStyle.Table { width: 500; line: ({kind: "thead", cols: [{label: "Player", w: 1}]}) } }', QUrl.fromLocalFile(str(Path(sys.argv[1]) / "table-test.qml")))
assert engine.rootObjects(), warnings
QTimer.singleShot(80, app.quit)
app.exec()
assert not warnings, warnings
'''
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QML_DISABLE_DISK_CACHE="1")
        result = subprocess.run([sys.executable, "-c", script, str(ui)], capture_output=True, text=True, timeout=10, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_repeated_table_implementation_is_outside_the_inline_style_namespace(self):
        """Qt can deadlock compiling a Repeater nested inside an external inline component."""
        ui = Path(__file__).resolve().parents[1] / "openrecomp/ui"
        style = (ui / "OnlineStyle.qml").read_text(encoding="utf-8")
        table = (ui / "OnlineTable.qml").read_text(encoding="utf-8")
        self.assertIn("component Table: OnlineTable {}", style)
        self.assertNotIn("Repeater {", style)
        self.assertIn("Repeater {", table)
        self.assertNotIn("OnlineStyle.", table)


class RoomDraftHelp(unittest.TestCase):
    def test_browser_status_does_not_take_space_in_the_creation_form(self):
        adapter, nav = hierarchy_nav()
        nav.click_chapter("rooms")
        self.assertEqual(nav.items()[nav.focus_index(nav.items())]["id"], "room_create_open")
        self.assertEqual(nav.view()["online"]["rooms"]["hint"], "")
        rows = nav.items()
        field = next(n for n, item in enumerate(rows) if item.get("id") == "online_room_name")
        nav.focus_online_row(field)
        self.assertTrue(nav.view()["online"]["rooms"]["hint"])
        self.assertEqual(adapter.calls, [])


class RankedPresentation(unittest.TestCase):
    def test_ranked_opens_without_starting_search_and_uses_available_progress(self):
        adapter, nav = hierarchy_nav()
        adapter.rank_progress = lambda rating: (1500, 1700, "4th Dan")
        nav.open_ranked(nav.game)
        page = nav.view()["online"]
        self.assertEqual(page["chapter"], "ranked")
        self.assertEqual(page["ranked"]["rating"], "1610")
        self.assertAlmostEqual(page["ranked"]["profile"]["progress"], .55)
        self.assertEqual(adapter.calls, [])
        self.assertEqual(nav.items()[nav.focus_index(nav.items())]["id"], "search_ranked")
        nav.click_chapter("rooms")
        self.assertEqual(nav.view()["online"]["chapter"], "rooms")

    def test_ranked_results_require_self_and_an_explicit_ranked_flag(self):
        adapter, nav = hierarchy_nav()
        adapter.snapshot["profile"] = dict(name="Me", history=[dict(opponent="Ranked rival", ranked=True, result="win"),
                                                                dict(opponent="Offline rival", result="win"),
                                                                dict(opponent="Casual rival", ranked=False, result="loss")])
        nav.open_ranked(nav.game)
        recent = nav.view()["online"]["ranked"]["recent"]
        self.assertEqual([row["opponent"] for row in recent], ["Ranked rival"])
        adapter.snapshot["profile"]["name"] = "Other player"
        self.assertEqual(nav.view()["online"]["ranked"]["recent"], [])

    def test_ranked_focus_only_reaches_visible_actions(self):
        _, nav = hierarchy_nav()
        nav.open_ranked(nav.game)
        for _ in range(45):
            nav.act("down")
            item = nav.items()[nav.focus_index(nav.items())]
            self.assertTrue(item.get("region") == "chat" or item.get("id") in
                            {"search_ranked", "ranked_options", "online_fighter", "rules_life", "ranked_strict", "screen_side", "always_left", "netext_options"})
        nav.open_ranked(nav.game)
        nav.act("right")
        self.assertEqual(nav.items()[nav.focus_index(nav.items())]["id"], "search_ranked")

    def test_match_options_are_hidden_until_opened_and_back_restores_toggle(self):
        adapter, nav = hierarchy_nav()
        nav.open_ranked(nav.game)
        self.assertNotIn("online_fighter", [row.get("id") for row in nav.items()])
        next(row for row in nav.items() if row.get("id") == "ranked_options")["run"]()
        self.assertIn("online_fighter", [row.get("id") for row in nav.items()])
        nav.act("back")
        rows = nav.items()
        self.assertEqual(rows[nav.focus_index(rows)]["id"], "ranked_options")
        self.assertNotIn("online_fighter", [row.get("id") for row in rows])
        self.assertEqual(adapter.calls, [])

    def test_placement_uses_placement_progress(self):
        adapter, nav = hierarchy_nav()
        adapter.snapshot["me"]["placement"] = (3, 10)
        nav.open_ranked(nav.game)
        ranked = nav.view()["online"]["ranked"]
        self.assertTrue(ranked["placement"])
        self.assertAlmostEqual(ranked["profile"]["progress"], .3)

    def test_servers_without_ranked_have_explicit_unavailable_state(self):
        adapter, nav = hierarchy_nav(t4=True)
        nav.open_ranked(nav.game)
        ranked = nav.view()["online"]["ranked"]
        self.assertFalse(ranked["available"])
        self.assertIn("unavailable", ranked["labels"]["unavailable"])
        self.assertEqual(adapter.calls, [])


class OfficialLeaderboard(unittest.TestCase):
    def setUp(self):
        self.adapter, self.nav = hierarchy_nav()
        self.adapter.snapshot["leaderboard"] = dict(updated=1700000000, rows=[
            dict(name="Third", place=3, rating=1600, rank="1st Dan", main="A", ranked_wins=3, ranked_losses=2),
            dict(name="Me", place=2, rating=1700, rank="2nd Dan", main="B", ranked_wins=10, ranked_losses=4, casual_wins=7, casual_losses=1),
            dict(name="First", place=1, rating=1800, rank="3rd Dan", main="A", ranked_wins=20, ranked_losses=3)])
        self.nav._t5_profile_pages = {self.nav.game.id: "leaderboard"}
        self.nav.click_chapter("leaderboard")

    def board(self):
        return self.nav.view()["online"]["leaderboard"]

    def test_podium_order_and_pinned_self_are_explicit(self):
        board = self.board()
        self.assertEqual([entry["place"] for entry in board["podium"]], ["1", "2", "3"])
        self.assertEqual(board["own"]["name"], "Me")
        self.assertTrue(board["own"]["own"])
        self.assertEqual(board["own"]["record"], "10W 4L")
        self.assertIn("2023", board["updated"])
        self.assertEqual(self.adapter.calls, [])

    def test_filters_are_local_preserve_places_and_switch_record_mode(self):
        items = self.nav.items()
        next(it for it in items if it.get("id") == "leaderboard_mode")["set"]("casual")
        next(it for it in items if it.get("id") == "leaderboard_fighter")["set"]("B")
        board = self.board()
        self.assertEqual([entry["name"] for entry in board["rows"]], ["Me"])
        self.assertEqual(board["rows"][0]["place"], "2")
        self.assertEqual(board["rows"][0]["record"], "7W 1L")
        self.assertEqual([it["id"] for it in self.nav.items() if it.get("id", "").startswith("profile_board:")], ["profile_board:Me"])
        self.assertEqual(self.adapter.calls, [])

    def test_self_outside_loaded_page_has_unknown_place(self):
        self.adapter.snapshot["leaderboard"]["rows"] = []
        self.assertEqual(self.board()["own"]["place"], "—")
        self.assertEqual(self.board()["own"]["rating"], "1610")

    def test_received_time_is_recorded_only_on_successful_refresh(self):
        owner = Owner()
        with mock.patch.object(t5_profiles.time, "time", return_value=12345):
            owner.action("leaderboard_refresh")
        self.assertEqual(t5_profiles.state(owner)["leaderboard"]["updated"], 12345)
        t5_profiles.completion(owner, t5_profiles.PREFIX + "board", None, RuntimeError("failed"))
        self.assertEqual(t5_profiles.state(owner)["leaderboard"]["updated"], 12345)

    def test_sort_keeps_focus_in_the_ranking_page(self):
        self.nav.dry = False
        item = next(it for it in self.nav.items() if it.get("id") == "leaderboard_sort:rating")
        item["run"]()
        focused = self.nav.items()[self.nav.focus_index(self.nav.items())]
        self.assertEqual(focused["region"], "leaderboard")
        self.assertEqual(self.nav.view()["online"]["chapter"], "leaderboard")

    def test_official_labels_have_complete_seven_language_catalogs(self):
        keys = {key for key in i18n.catalog("en") if key.startswith("official_ui.")}
        self.assertGreater(len(keys), 20)
        for language in i18n.LANGUAGES:
            self.assertTrue(keys <= i18n.catalog(language).keys(), language)
            self.nav.language = language
            self.assertNotIn("@official_ui.", json.dumps(self.nav.view(), ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
