"""Navigation areas keep one shared state and the public plain-dict view."""
import ast
import importlib
import unittest
from pathlib import Path
from unittest import mock

from openrecomp import nav
from test_nav import Fake, manifest


ROOT = Path(__file__).parents[1] / "openrecomp"
AREAS = {
    "shelf": ("tile_ids", "game_by_id", "set_games", "_start", "_view_start", "click_tile"),
    "hub": ("sections", "section", "key", "items", "focus_index", "_hub", "_cycle", "_activate",
            "_finish_hold", "_view_hub", "click_row", "click_tab", "click_primary"),
    "sections": ("_items_play", "_go", "_native_item", "_option_label", "_cycler_item", "_items_online",
                 "_items_replays", "_play_replay", "_items_build", "_items_settings"),
    "dialog": ("_ask", "_dialog", "_view_dialog"),
    "drawer": ("_drawer_items", "_drawer", "_cycle_language", "_view_drawer"),
    "grid": ("_fighter_list", "_open_fighters", "_fighters", "_view_fighters", "click_cell"),
    "keyboard": ("_open_osk", "_osk", "type_text", "_osk_done", "_view_osk", "click_key"),
    "picker": ("_open_picker", "_picker_first_file", "_picker_entries", "_picker", "_picked", "_view_picker"),
}
VIEW_FIELDS = {
    "screen", "overlay", "toast", "device", "inputMode", "nativeEdit", "nativeField", "trail", "social", "prevG", "nextG", "confirmInk", "backG",
    "shelf", "tabs", "rows", "detail", "hint", "prompts", "accent", "badge", "gameShort", "numeral",
    "topline", "hold", "more", "grid", "osk", "dialog", "picker", "drawer", "quickAccess", "recentSets",
    "folder", "file", "pick", "mainLabel", "fighterTitle", "fighterMain", "fullscreen", "reducedMotion", "build", "online", "settingsPage",
    "bindingsPage", "bindCapture", "ctlPreset",
    "discord", "sessionPage", "loading", "loadError", "textScale", "highContrast", "mainMenu",
    "globalOffers", "activity", "matchVersus", "gameTheme",
}


class Layout(unittest.TestCase):
    def test_each_area_owns_its_input_and_view_methods(self):
        for area, methods in AREAS.items():
            for name in methods:
                with self.subTest(area=area, method=name):
                    self.assertEqual(getattr(nav.Nav, name).__module__, "openrecomp.nav_" + area)
        for name in ("__init__", "act", "release", "tick", "say", "view", "click_entry"):
            self.assertIn(name, nav.Nav.__dict__)

    def test_public_constants_and_helpers_remain_available(self):
        common = importlib.import_module("openrecomp.nav_common")
        for name in ("SECTION_TITLES", "GLYPHS", "TRAIL", "DEVICE_LABEL", "OSK", "OSK_ACTIONS",
                     "ROWS_VISIBLE", "PICKER_VISIBLE", "SCREEN_W", "WIDE", "SPINE_GAME", "SPINE_SLOT",
                     "GAP", "GRID_COLS", "HOLD_SECONDS", "FRIENDLY_RESULT", "uri", "window", "badge"):
            self.assertIs(getattr(nav, name), getattr(common, name), name)

    def test_navigation_modules_have_no_qt_or_concrete_adapter_imports(self):
        for path in (ROOT / "nav.py", *ROOT.glob("nav_*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [node.module or ""] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names]
                    for name in names:
                        self.assertFalse(any(part in name.lower() for part in ("qt", "pyside", "adapter")), path.name)

    def assert_plain(self, value):
        self.assertIn(type(value), (dict, list, str, bool, int, float, type(None)))
        if isinstance(value, dict):
            for key, child in value.items():
                self.assertIs(type(key), str)
                self.assert_plain(child)
        elif isinstance(value, list):
            for child in value:
                self.assert_plain(child)

    def test_view_fields_and_plain_values_survive_every_area(self):
        adapter = Fake(manifest())
        state = nav.Nav([nav.Game(adapter.m, adapter)], language="en")

        def check():
            view = state.view()
            self.assert_plain(view)
            self.assertEqual(set(view), VIEW_FIELDS | ({"hero"} if state.screen == "hub" else set()))
            self.assertEqual(len(view["trail"]), 16)
            self.assertTrue(view["prompts"])
            for prompt in view["prompts"]:
                self.assertEqual(set(prompt), {"action", "label", "g"})
                self.assertEqual(set(prompt["g"]), {"text", "round", "ink", "key", "symbol"})
            return view

        check()
        state.act("confirm")
        for _ in adapter.m["sections"]:
            check()
            state.act("next")
        state.act("social")
        self.assertEqual(set(check()["drawer"]), {"rows"})
        state.act("back")
        state._ask("exit")
        self.assertEqual(set(check()["dialog"]), {"title", "text", "options"})
        state.act("back")
        state._open_fighters()
        self.assertEqual(set(check()["grid"]), {"main", "cells", "mosaic"})
        state.act("back")
        state._open_osk("name")
        self.assertEqual(check()["osk"]["text"], "alt_")
        state.act("back")
        with mock.patch.object(state, "_picker_entries", return_value=[]):
            state._open_picker("manifest", "@choose_manifest", [".json"], [], "file")
            self.assertEqual(set(check()["picker"]), {"rows", "title", "path", "up", "down", "message"})
        self.assertEqual(adapter.calls, [])


if __name__ == "__main__":
    unittest.main()
