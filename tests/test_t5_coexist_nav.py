"""Borrowed installs remain inspectable and selectable using controller actions only."""
import unittest
from unittest import mock

from openrecomp import i18n
from openrecomp.adapters.base import Missing
from openrecomp.nav import Game, Nav
from test_nav import Fake, manifest


class Borrowed(Fake):
    def coexistence_state(self):
        return dict(active=True, source="@literal-folder", build="different")


class CoexistenceNavigation(unittest.TestCase):
    def setUp(self):
        self.adapter = Borrowed(manifest("t5dr", adapter="t5dr"))
        self.nav = Nav([Game(self.adapter.m, self.adapter)], language="en")
        self.nav.screen = "hub"
        self.nav.game = self.nav.games[0]

    def test_play_explains_reuse_and_settings_isolation(self):
        self.nav.sec["t5dr"] = "play"
        items = self.nav.items()
        row = next(item for item in items if item["id"] == "coexistence")
        self.nav.focus["t5dr:play"] = items.index(row)
        view = self.nav.view()
        detail = str(view["detail"])
        for key in ("t5.coexist.hint", "t5.coexist.settings", "t5.coexist.login", "t5.coexist.build_differs"):
            self.assertIn(i18n.text("en", key), detail)
        self.assertIn("@literal-folder", detail)
        self.assertEqual(self.adapter.calls, [])

    def test_build_screen_never_reads_sources_or_offers_rebuild(self):
        self.nav.sec["t5dr"] = "build"
        with mock.patch.object(self.adapter, "sources", side_effect=AssertionError("must not inspect game sources")):
            items = self.nav.items()
        self.assertEqual([item["id"] for item in items], ["coexistence", "coexistence_folder", "build"])
        self.assertTrue(items[-1]["disabled"])
        self.nav.focus["t5dr:build"] = 2
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.adapter.calls, [])

    def test_controller_can_choose_another_install_and_cancel_without_changes(self):
        self.nav.sec["t5dr"] = "settings"
        with mock.patch.object(self.nav, "_picker_entries", return_value=[]):
            self.nav.act("down", device="xbox")
            self.nav.act("confirm", device="xbox")
            self.assertEqual(self.nav.overlay, "picker")
            self.assertEqual(self.nav.picker["target"], "source:folder")
            self.nav.act("back", device="xbox")
        self.assertIsNone(self.nav.overlay)
        self.assertEqual(self.adapter.calls, [])

    def test_missing_install_rejects_invalid_folder_without_changing_selection(self):
        adapter = Missing(manifest("t5dr", adapter="t5dr"), {"roots": {"t5dr": "previous"}})
        with mock.patch("openrecomp.adapters.t5dr.find_root", return_value=None):
            self.assertEqual(adapter.set_source("folder", "invalid"), "@t5.coexist.install_invalid")
        self.assertEqual(adapter.config["roots"]["t5dr"], "previous")

    def test_missing_install_registers_validated_root_without_copy(self):
        adapter = Missing(manifest("t5dr", adapter="t5dr"), {})
        with mock.patch("openrecomp.adapters.t5dr.find_root", return_value="validated"):
            self.assertEqual(adapter.set_source("folder", "wrapper"), "reload")
        self.assertEqual(adapter.config["roots"]["t5dr"], "validated")

    def test_changing_missing_install_clears_previous_settings_copy(self):
        adapter = Missing(manifest("t5dr", adapter="t5dr"),
                          {"roots": {"t5dr": "previous"}, "t5dr_settings_copy": "previous-copy"})
        with mock.patch("openrecomp.adapters.t5dr.find_root", return_value="validated"):
            self.assertEqual(adapter.set_source("folder", "new"), "reload")
        self.assertNotIn("t5dr_settings_copy", adapter.config)


if __name__ == "__main__":
    unittest.main()
