"""Calm interface (0.1.7): one accent on grey surfaces by default, no page for one or two rows."""
import unittest

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine

from openrecomp import i18n
from openrecomp.nav import Game, Nav
from openrecomp.nav_online_layout import CHAPTERS
from openrecomp.nav_settings_page import TAB_OF
from test_accessibility import ROOT, contrast
from test_nav import Fake, manifest
from tools.online_shots import scene as online_scene


def theme():
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(b'import QtQuick\nimport "."\nQtObject { property var theme: Theme }',
                      QUrl.fromLocalFile(str(ROOT / "openrecomp/ui/ThemeProbe.qml")))
    probe = component.create()
    return app, engine, probe, probe.property("theme")


class CalmTheme(unittest.TestCase):
    def test_calm_is_the_default_with_grey_surfaces_and_readable_text_for_every_game(self):
        _app, engine, probe, t = theme()
        self.assertTrue(t.property("calm"))
        for kind in ("t5dr", "t4", ""):
            t.setProperty("gameKind", kind)
            for token in ("ground", "card", "raised", "highlighted", "border", "value", "rankGold"):
                colour = t.property(token)
                spread = max(colour.red(), colour.green(), colour.blue()) - min(colour.red(), colour.green(), colour.blue())
                self.assertLessEqual(spread, 10, (kind, token))    # grey, not tinted
            # no warm gradient: the selection is the plain highlighted surface
            self.assertEqual(t.property("highlightStart"), t.property("highlighted"))
            self.assertEqual(t.property("highlightEnd"), t.property("highlighted"))
            for surface in ("ground", "card", "raised", "highlighted"):
                self.assertGreaterEqual(contrast(t.property("text").name(), t.property(surface).name()), 4.5, (kind, surface))
                self.assertGreaterEqual(contrast(t.property("value").name(), t.property(surface).name()), 4.5, (kind, surface))
            for surface in ("ground", "card", "raised"):
                self.assertGreaterEqual(contrast(t.property("muted").name(), t.property(surface).name()), 4.5, (kind, surface))
            self.assertGreaterEqual(contrast(t.property("primaryFill").name(), t.property("primaryText").name()), 4.5, kind)
            self.assertGreaterEqual(contrast(t.property("focus").name(), t.property("ground").name()), 3, kind)
            self.assertLess(t.property("artStrength"), .58)
        t.setProperty("gameKind", "t5dr")
        t.setProperty("calm", False)                        # vivid = the 0.1.6 palette
        self.assertEqual(t.property("ground").name(), "#100c10")
        self.assertEqual(t.property("highlightStart").name(), "#8d2f12")
        t.setProperty("calm", True)
        t.setProperty("highContrast", True)                 # high contrast wins over both
        self.assertEqual(t.property("ground").name(), "#000000")
        t.setProperty("highContrast", False)
        del probe, engine

    def test_interface_colours_is_a_display_setting_that_is_saved(self):
        adapter = Fake(manifest("a"))
        saved = []
        nav = Nav([Game(adapter.m, adapter)], language="en", on_colours=saved.append)
        nav.screen = "hub"
        nav.sec["a"] = "settings"
        self.assertEqual(nav.view()["colours"], "calm")
        row = next(it for it in nav.items() if it.get("id") == "colours")
        self.assertEqual(row["settingsGroup"], "display")
        self.assertEqual([value for value, _ in row["options"]], ["calm", "vivid"])
        row["set"]("vivid")
        self.assertEqual((nav.view()["colours"], saved), ("vivid", ["vivid"]))
        self.assertEqual(Nav([Game(adapter.m, adapter)], colours="neon").view()["colours"], "calm")
        for code in i18n.LANGUAGES:
            for key in ("accessibility.colours", "accessibility.colours_hint", "accessibility.colours_calm",
                        "accessibility.colours_vivid", "online_ui.chapter.profile_account"):
                self.assertTrue(i18n.catalog(code).get(key), (code, key))


class FewerLevels(unittest.TestCase):
    def settings_nav(self):
        adapter = Fake(manifest("a"))
        adapter.settings = lambda: [dict(id="mute", label="Sound", options=[(True, "@on"), (False, "@off")], value=True)]
        nav = Nav([Game(adapter.m, adapter)], language="en")
        nav.screen = "hub"
        nav.sec["a"] = "settings"
        return nav

    def test_a_settings_tab_of_one_or_two_rows_joins_its_neighbour_and_keeps_every_row(self):
        nav = self.settings_nav()
        items = nav.items()
        page = nav.view()["settingsPage"]
        rows = [it for it in items if it.get("kind") != "heading"]
        counts = {}
        for it in rows:
            counts[TAB_OF[it["settingsGroup"]]] = counts.get(TAB_OF[it["settingsGroup"]], 0) + 1
        small = [tab for tab, n in counts.items() if n <= 2]
        self.assertTrue(small)                              # Audio: one row (Sound)
        self.assertLess(len(page["tabs"]), len(counts))
        self.assertTrue(all(tab["id"] not in small or counts[tab["id"]] > 2 for tab in page["tabs"]))
        seen = set()
        for tab in page["tabs"]:
            nav.select_settings_tab(tab["id"])
            seen.update(line["index"] for line in nav.view()["settingsPage"]["tabLines"] if line["kind"] == "setting")
        self.assertEqual(seen, {n for n, it in enumerate(items) if it.get("kind") != "heading"})
        joined = [tab for tab in page["tabs"] if " · " in i18n.localize(tab["label"], "en")]
        self.assertTrue(joined)                             # its tab names both pages

    def test_statistics_and_account_open_on_their_neighbours_pages(self):
        nav = online_scene("t5", "lobby", "en")
        chapters = [c["id"] for c in nav.view()["online"]["chapters"]]
        self.assertNotIn("stats", chapters)
        self.assertNotIn("account", chapters)
        self.assertIn("leaderboard", chapters)
        self.assertIn("profile", chapters)
        self.assertLessEqual(len(chapters), len(CHAPTERS) - 2)
        items = nav.items()
        regions = {it.get("id"): it.get("region") for it in items}
        self.assertEqual(regions.get("stats_refresh"), "leaderboard")
        self.assertTrue(any(it.get("origin") == "account" and it.get("region") == "profile" for it in items))
        nav.click_chapter("account")                        # old names still open their rows
        focused = nav.items()[nav.focus[nav.key()]]
        self.assertEqual((focused.get("region"), focused.get("origin")), ("profile", "account"))
        nav.click_chapter("stats")
        focused = nav.items()[nav.focus[nav.key()]]
        self.assertEqual((focused.get("region"), focused.get("origin")), ("leaderboard", "stats"))
        # the ranking page offers the statistics; the statistics show as plain sections with the ranking's row
        nav._t5_profile_pages = {"t5": "leaderboard"}
        page = nav.view()["online"]
        stats = next(n for n, it in enumerate(nav.items()) if it.get("id") == "stats_refresh")
        self.assertIn(stats, [b["index"] for b in page["leaderboard"]["buttons"]])
        nav._t5_profile_pages = {"t5": "stats"}
        page = nav.view()["online"]
        stats = next(n for n, it in enumerate(nav.items()) if it.get("id") == "stats_refresh")
        self.assertEqual(page["chapter"], "leaderboard")
        self.assertNotIn("leaderboard", page)
        def indices(value):
            if isinstance(value, dict):
                yield from ([value["index"]] if isinstance(value.get("index"), int) else [])
                for child in value.values():
                    yield from indices(child)
            elif isinstance(value, list):
                for child in value:
                    yield from indices(child)
        self.assertIn(stats, set(indices(page["body"]["sections"])))


if __name__ == "__main__":
    unittest.main()
