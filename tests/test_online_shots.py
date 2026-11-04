"""Online review images are synthetic and cannot load player art or contact services."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import online_shots


class SyntheticOnlineScreenshots(unittest.TestCase):
    def test_targeted_recapture_replaces_only_its_exact_locale_game_scene_size(self):
        original = [dict(language="en", game="t5", scene="searching", size="1920x1080", overflow=["old"]),
                    dict(language="de", game="t5", scene="searching", size="1920x1080", overflow=[]),
                    dict(language="en", game="t4", scene="rooms", size="1280x720", overflow=[])]
        refreshed = dict(original[0], overflow=[])
        result = online_shots.merge_captures(original, [refreshed])
        self.assertEqual(result, [refreshed] + original[1:])

    def test_parallel_capture_variants_have_separate_private_homes(self):
        homes = {online_shots.capture_home("after", "normal"),
                 online_shots.capture_home("after", "large"),
                 online_shots.capture_home("after", "larger", True),
                 online_shots.capture_home("after", "larger", True, platform="windows"),
                 online_shots.capture_home("after", "normal", batch="final")}
        self.assertEqual(len(homes), 5)
        for home in homes:
            self.assertTrue(home.is_relative_to(online_shots.ROOT / "build" / "tmp-home"))

    def test_every_online_chapter_in_both_games_and_all_catalogs_is_safe(self):
        with mock.patch("socket.socket", side_effect=AssertionError("Network")), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("External process")):
            for language in online_shots.i18n.LANGUAGES:
                for game in ("t5", "t4"):
                    for chapter in online_shots.SCENES:
                        with self.subTest(language=language, game=game, chapter=chapter):
                            nav = online_shots.scene(game, chapter, language)
                            view = online_shots.snapshot(nav)
                            self.assertTrue(nav.dry)
                            if chapter in online_shots.OFFER_SCENES:
                                self.assertEqual(len(view["globalOffers"]), 1)
                                self.assertEqual(view["globalOffers"][0]["name"], "Rival")
                                self.assertEqual(view["screen"], "start" if chapter == "offer_shelf" else "hub")
                            elif chapter in online_shots.ACTIVITY_SCENES:
                                self.assertEqual(view["activity"]["phase"], "searching")
                                self.assertEqual(view["mainMenu"]["show"], chapter == "activity_home")
                                if chapter == "activity_rooms":
                                    self.assertEqual(view["online"]["chapter"], "rooms")
                            elif chapter == "home":
                                self.assertTrue(view["mainMenu"]["show"])
                            elif chapter == "settings":
                                self.assertEqual(view["settingsPage"]["layout"], "groups")
                            elif chapter == "controls":
                                self.assertEqual(nav.section(), "controls")
                            elif chapter == "ranked_select":
                                self.assertEqual(view["online"]["chapter"], "ranked")
                                self.assertEqual(view["overlay"], "fighters")
                                self.assertTrue(view["grid"]["cells"])
                            else:
                                if chapter in ("searching", "cancelling", "matched", "matched_picks", "starting", "playing", "result", "reporting", "disconnect_retry"):
                                    self.assertEqual(nav.game.a.snapshot["phase"], {"matched_picks": "matched", "reporting": "result_sent", "disconnect_retry": "error"}.get(chapter, chapter))
                                else:
                                    expected = "rooms" if chapter in ("rooms_create", "community_room") else "lobby" if chapter == "feedback" or chapter in online_shots.ARCADE_SCENES + online_shots.COMMUNITY_SCENES else chapter.removesuffix("_empty")
                                    self.assertEqual(view["online"]["chapter"], expected)
                            self.assertEqual(nav.game.a.calls, [])
                            self.assertFalse(view["online"].get("profile", {}).get("face"))
                            self.assertFalse(view["online"].get("profile", {}).get("plate"))

    def test_sanitizer_removes_profile_art_and_nested_art(self):
        view = dict(profile=dict(face="private.png", plate="private.png"),
                    nested=[dict(image="private.png", images=["private.png"], portrait="private.png", render="private.png")])
        online_shots.strip_art(view)
        self.assertNotIn("private", str(view))

    def test_new_states_have_real_fixture_data_and_never_execute_actions(self):
        history = online_shots.scene("t5", "chat_history", "en")
        self.assertEqual(len(history.game.a.snapshot["chat"]), 48)
        private = online_shots.scene("t5", "private_chat", "en")
        self.assertEqual(private.game.a.snapshot["private_chat"]["selected"], "p1")
        self.assertEqual(len(private.game.a.snapshot["private_chat"]["threads"]), 2)
        mentions = online_shots.scene("t4", "mentions", "de")
        self.assertTrue(mentions.game.a.snapshot["chat"][0]["mentioned"])
        self.assertIn("<b>", mentions.game.a.snapshot["chat"][2]["text"])
        native = online_shots.scene("t5", "native_composer", "en")
        self.assertEqual(native.device, "kb")
        self.assertIsNone(native.overlay)
        pad = online_shots.scene("t4", "pad_osk", "en")
        self.assertEqual(pad.overlay, "osk")
        self.assertEqual(pad.osk["tid"], "online_chat")
        room = online_shots.scene("t5", "community_room", "en")
        self.assertEqual(room.game.a.snapshot["community"]["room"]["line"], ["p1", "me", "p6"])
        for nav in (history, private, mentions, native, pad, room):
            self.assertEqual(nav.game.a.calls, [])
        controls = online_shots.scene("t5", "controls", "en")
        self.assertEqual([item["value"] for item in controls.items() if item.get("id", "").startswith("pad1:")],
                         ["A", "B", "X", "Y", "Start", "Back"])

    def test_dense_lobby_fixture_can_prove_the_requested_visible_player_count(self):
        for game in ("t5", "t4"):
            nav = online_shots.scene(game, "lobby_dense", "en")
            players = online_shots.snapshot(nav)["online"]["arcade"]["players"]
            self.assertEqual(len(players), 40)
            self.assertEqual(len({player["id"] for player in players}), len(players))
            self.assertTrue(all(player["name"] for player in players))
            self.assertEqual(sum(player["own"] for player in players), 1)
            self.assertEqual(nav.game.a.calls, [])

    def test_review_batches_are_explicit_complete_scene_sets(self):
        for state in ("challenge_incoming", "challenge_sent", "challenge_waiting", "challenge_cancelled",
                      "challenge_declined", "challenge_expired", "searching", "cancelling", "matched", "starting",
                      "disconnect_retry", "native_composer", "pad_osk", "chat_history"):
            self.assertIn(state, online_shots.COMMUNITY_SCENES)
            self.assertIn(state, online_shots.SCENES)
        self.assertTrue(set(online_shots.FINAL_SCENES).issubset(online_shots.SCENES))
        self.assertEqual(len(online_shots.SCENES), len(set(online_shots.SCENES)))

    def test_terminal_challenges_show_named_recoverable_nearby_result(self):
        for terminal in ("cancelled", "declined", "expired"):
            nav = online_shots.scene("t5", "challenge_" + terminal, "en")
            result = online_shots.snapshot(nav)["online"]["arcade"]["result"]
            self.assertIn("Rival", result["text"])
            self.assertEqual(result["error"], terminal in ("declined", "expired"))
            self.assertEqual(nav.game.a.calls, [])

    def test_empty_room_scene_really_has_no_open_rooms(self):
        nav = online_shots.scene("t5", "rooms_empty", "en")
        self.assertEqual(nav.game.a.snapshot["rooms"], [])
        self.assertIn("no_rooms", [row.get("id") for row in nav.items()])

    def test_create_room_fixture_displays_the_supplied_first_to_preference(self):
        for game in ("t5", "t4"):
            for language in ("en", "de"):
                with self.subTest(game=game, language=language):
                    nav = online_shots.scene(game, "rooms_create", language)
                    self.assertEqual(nav.game.a.snapshot["community"]["preferences"]["first_to"], 2)
                    fields = online_shots.snapshot(nav)["online"]["rooms"]["draft"]
                    ft = next(field for field in fields if field.get("id") == "community_option:first_to")
                    self.assertTrue(ft["value"])
                    self.assertIn("2", ft["value"])
                    self.assertEqual(nav.game.a.calls, [])

    def test_baseline_mixin_precedes_current_navigation_without_replacing_it(self):
        with tempfile.TemporaryDirectory(dir=online_shots.ROOT) as directory:
            source = Path(directory) / "baseline.py"
            source.write_text('class OnlineLayout:\n    baseline_marker = "preserved"\n', encoding="utf-8")
            nav_type = online_shots.baseline_nav(source)
            nav = online_shots.scene("t5", "rooms", "en", nav_type=nav_type)
            self.assertEqual(nav.baseline_marker, "preserved")
            self.assertTrue(issubclass(nav_type, online_shots.Nav))
            self.assertFalse(hasattr(online_shots.Nav, "baseline_marker"))

    def test_vertical_scrolling_does_not_hide_horizontal_clipping(self):
        self.assertEqual(online_shots.clip_reason(0, -60, 300, 40, 300, 200, True), "")
        self.assertEqual(online_shots.clip_reason(0, 180, 300, 240, 300, 200, True), "")
        self.assertEqual(online_shots.clip_reason(0, 180, 320, 240, 300, 200, True), "horizontal-clip")
        self.assertEqual(online_shots.clip_reason(0, 180, 300, 240, 300, 200), "vertical-clip")

    def test_geometry_detects_notice_and_pane_overlap_at_output_scale(self):
        panes = [dict(name="lobbyPlayersPane", x=24, y=120, width=1100, height=860),
                 dict(name="lobbyChatPane", x=1140, y=120, width=756, height=860),
                 dict(name="lobbyNotice", x=24, y=40, width=1872, height=64)]
        self.assertEqual(online_shots.layout_problems(panes), [])
        panes[-1]["y"] = 252
        overlaps = online_shots.layout_problems(panes)
        self.assertEqual(len(overlaps), 2)
        self.assertTrue(all(problem["reason"] == "pane-overlap" for problem in overlaps))

    def test_only_declared_scroll_viewports_allow_bounded_horizontal_content(self):
        from PySide6.QtCore import QPointF

        class Item:
            def __init__(self, name, width, height, parent=None, **properties):
                self.name, self.w, self.h, self.parent, self.props = name, width, height, parent, properties
                self.children = []
                if parent:
                    parent.children.append(self)
            def childItems(self): return self.children
            def isVisible(self): return True
            def opacity(self): return 1
            def width(self): return self.w
            def height(self): return self.h
            def objectName(self): return self.name
            def property(self, key): return self.props.get(key)
            def parentItem(self): return self.parent
            def clip(self): return bool(self.children)
            def mapToItem(self, parent, point): return QPointF(point.x() + self.props.get("x", 0), point.y())

        root = Item("root", 300, 200)
        viewport = Item("rankingCompactControls", 300, 80, root, contentWidth=800, contentX=100)
        label = Item("onlineFieldLabel", 100, 40, viewport, x=450, text="Rating", contentWidth=100, contentHeight=40)
        window = mock.Mock(contentItem=lambda: root)
        self.assertEqual(online_shots.geometry(window), ([], []))
        for name in ("onlineChapters", "chatTabsViewport"):
            viewport.name = name
            self.assertEqual(online_shots.geometry(window), ([], []))
        viewport.name = "unrelatedPanel"
        self.assertEqual(online_shots.geometry(window)[0][0]["reason"], "horizontal-clip")
        viewport.name = "rankingCompactControls"
        label.props["x"] = 750
        self.assertEqual(online_shots.geometry(window)[0][0]["reason"], "scroll-content-overflow")
        label.props.update(x=450, contentWidth=130)
        self.assertEqual(online_shots.geometry(window)[0][0]["reason"], "text-width")

    def test_accessibility_and_feedback_scenes_stay_inert(self):
        for game in ("t5", "t4"):
            nav = online_shots.scene(game, "feedback", "en", text_size=130, high_contrast=True)
            view = online_shots.snapshot(nav)
            self.assertEqual(view["textScale"], 1.3)
            self.assertTrue(view["highContrast"])
            self.assertIn("0:27 remaining", str(view["online"]["body"]))
            self.assertEqual(nav.game.a.calls, [])
            home = online_shots.snapshot(online_shots.scene(game, "home", "en"))
            self.assertEqual(any(row["id"] == "ranked" for row in home["mainMenu"]["entries"]), game != "t4")

    def test_arcade_review_scenes_cover_cards_cabinet_and_options_without_actions(self):
        with mock.patch("socket.socket", side_effect=AssertionError("Network")), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("External process")):
            for game in ("t5", "t4"):
                for name in online_shots.ARCADE_SCENES:
                    with self.subTest(game=game, scene=name):
                        nav = online_shots.scene(game, name, "en")
                        arcade = online_shots.snapshot(nav)["online"]["arcade"]
                        self.assertGreaterEqual(len(arcade["players"]), 7)
                        self.assertEqual(sum(p["own"] for p in arcade["players"]), 1)
                        self.assertTrue(arcade["cabinets"])
                        self.assertEqual(arcade["cabinets"][0]["score"], "2 : 1")
                        self.assertEqual(arcade["optionsOpen"], name == "arcade_options")
                        self.assertEqual(arcade["moreOpen"], name == "arcade_cabinet")
                        if name == "arcade_selected":
                            self.assertTrue(next(p for p in arcade["players"] if p["id"] == "p1")["focused"])
                        elif name == "arcade_cabinet":
                            self.assertTrue(arcade["cabinets"][0]["focused"])
                        self.assertFalse(any(p["face"] or p["plate"] for p in arcade["players"]))
                        self.assertFalse(any(p["face"] for cabinet in arcade["cabinets"] for p in cabinet["players"]))
                        self.assertEqual(nav.game.a.calls, [])


if __name__ == "__main__":
    unittest.main()
