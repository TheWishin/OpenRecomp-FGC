import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from openrecomp import i18n, nav_profiles


class ProfileHistoryLabels(unittest.TestCase):
    def history_details(self, **record):
        state = dict(profile=dict(history=[dict(opponent="Rival", **record)]))
        rows = nav_profiles._profile_rows(None, SimpleNamespace(), state, None)
        return next(row["detail"]["rows"] for row in rows if row.get("id") == "profile_history:0")

    def test_history_status_and_reason_use_complete_catalog_keys(self):
        statuses = ("confirmed", "onesided", "forfeit", "resolved", "disputed", "void", "training")
        reasons = ("desync", "too_short", "disputed", "crash", "early_quit", "quit", "disconnect",
                   "connection", "no_report", "both_left", "timeout", "crash_repeat", "early_quit_repeat",
                   "no_report_repeat", "score_mismatch", "no_result", "set_restart", "no_return")
        for field, codes in (("status", statuses), ("reason", reasons)):
            for code in codes:
                with self.subTest(field=field, code=code):
                    details = self.history_details(**{field: code})
                    value = next(row["v"] for row in details if row["k"] == "@online.history_" + field)
                    self.assertEqual(value, "@online.history_" + code)
                    for language in i18n.LANGUAGES:
                        self.assertIn(value[1:], i18n.catalog(language))

    def test_unknown_history_codes_do_not_become_catalog_keys(self):
        details = self.history_details(status="private-status", reason="@online.logout")
        self.assertFalse(any(row["k"] in ("@online.history_status", "@online.history_reason") for row in details))

    def test_supplied_history_and_character_rows_use_adapter_cache_references(self):
        from test_online_hierarchy import hierarchy_nav

        adapter, nav = hierarchy_nav()
        cached = Path(__file__).resolve().parents[1] / "build/tmp-home/fighter-cache/a.png"
        adapter.fighters = lambda: [dict(key="A", name="Fighter A"), dict(key="B", name="Fighter B")]
        adapter.fighter_image = mock.Mock(side_effect=lambda key: str(cached) if key == "A" else "")
        adapter.snapshot["profile"] = dict(name="Me", chars=[dict(char="A", games=3)],
            ranked_chars=[dict(char="B", games=2)], history=[dict(opponent="Rival", you_char="A", opp_char="B")])
        nav._t5_profile_pages = {nav.game.id: "profile"}
        nav.click_chapter("profile")
        lines = [line for section in nav.view()["online"]["body"]["sections"] for line in section["lines"]]
        cells = [cell for line in lines for cell in line.get("cells", []) if cell.get("character")]
        self.assertEqual([cell["character"] for cell in cells], ["Fighter A", "Fighter B", "Fighter A", "Fighter B"])
        self.assertEqual([cell["face"] for cell in cells], [cached.as_uri(), "", cached.as_uri(), ""])
        self.assertEqual(adapter.calls, [])

    def test_unknown_history_fighters_do_not_invent_portraits(self):
        from test_online_hierarchy import hierarchy_nav

        adapter, nav = hierarchy_nav()
        adapter.fighter_image = mock.Mock(return_value="")
        adapter.snapshot["profile"] = dict(name="Me", history=[dict(opponent="Rival")])
        nav._t5_profile_pages = {nav.game.id: "profile"}
        nav.click_chapter("profile")
        cells = [cell for section in nav.view()["online"]["body"]["sections"]
                 for line in section["lines"] for cell in line.get("cells", [])]
        self.assertFalse(any(cell.get("character") or cell.get("face") for cell in cells))


if __name__ == "__main__":
    unittest.main()
