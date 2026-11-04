"""Play time is localized, bounded and based only on local adapter records."""
from datetime import date
import unittest
from unittest import mock

from openrecomp import i18n, playtime_format as fmt


class PlaytimeFormatting(unittest.TestCase):
    def test_requested_duration_examples_and_minute_floor(self):
        for seconds, expected in ((180, "3 min"), (8100, "2 h 15 min"), (432000, "120 h"),
                                  (59, "0 min"), (3600, "1 h"), (3659, "1 h")):
            self.assertEqual(fmt.duration(seconds, "en"), expected)

    def test_invalid_totals_do_not_break_the_view(self):
        for value in (None, "bad", -100, float("inf"), float("nan"), {}):
            self.assertEqual(fmt.duration(value, "en"), "0 min")
        self.assertEqual(fmt.total(dict(offline_seconds=120, online_seconds=-60)), 120)

    def test_every_catalog_has_translations_with_matching_placeholders(self):
        english = {key: value for key, value in i18n.catalog("en").items() if key.startswith("playtime.")}
        self.assertGreaterEqual(len(english), 17)
        expected = {"en": "2 h 15 min", "de": "2 Std. 15 Min.", "es": "2 h 15 min",
                    "fr": "2 h 15 min", "ja": "2時間15分", "ko": "2시간 15분", "pt-BR": "2 h 15 min"}
        from string import Formatter
        fields = lambda value: {field for _, field, _, _ in Formatter().parse(value) if field}
        for language in i18n.LANGUAGES:
            catalog = i18n.catalog(language)
            self.assertEqual(fmt.duration(8100, language), expected[language])
            for key, value in english.items():
                self.assertIn(key, catalog, (language, key))
                self.assertEqual(fields(catalog[key]), fields(value), (language, key))
                self.assertNotIn("\ufffd", catalog[key])

    def test_last_played_uses_injected_calendar_and_local_date_order(self):
        today = date(2026, 11, 4)
        self.assertEqual(fmt.last_played("2026-11-04T19:30:00+00:00", "en", today), "last played today")
        self.assertEqual(fmt.last_played("2026-11-03", "en", today), "last played yesterday")
        self.assertEqual(fmt.last_played("2026-10-30", "en", today), "last played 2026-10-30")
        self.assertEqual(fmt.last_played("2026-10-30", "de", today), "zuletzt am 30.10.2026 gespielt")
        self.assertEqual(fmt.last_played("2026-10-30", "ja", today), "最終プレイ：2026年10月30日")
        self.assertEqual(fmt.last_played("2026-10-02", "ja", today), "最終プレイ：2026年10月2日")
        self.assertEqual(fmt.last_played("2026-10-02", "ko", today), "마지막 플레이: 2026년 10월 2일")
        self.assertEqual(fmt.last_played("2026-10-02", "fr", today), "dernière partie le 02/10/2026")
        for value in (None, "", "bad", "2026-02-30"):
            self.assertEqual(fmt.last_played(value, "en", today), "never played")

    def test_summary_combines_modes_and_profile_lists_games_without_network(self):
        stats = dict(offline_seconds=2 * 3600, online_seconds=15 * 60, last_played="2026-11-04")
        self.assertEqual(fmt.summary(stats, "en", date(2026, 11, 4)), "2 h 15 min played · last played today")
        with mock.patch("socket.socket", side_effect=AssertionError("Network")):
            games = [dict(short="T5DR", offline_seconds=30 * 3600, online_seconds=12 * 3600),
                     dict(short="T4", offline_seconds=6 * 3600)]
            self.assertEqual(fmt.profile(games, "en"), "Play time: T5DR 42 h, T4 6 h")

    def test_art_free_review_fixtures_show_playtime_in_all_languages(self):
        from tools import ui_shots
        with mock.patch("socket.socket", side_effect=AssertionError("Network")), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("External process")):
            for language in i18n.LANGUAGES:
                for name in ("playtime_tile", "playtime_game", "playtime_profile"):
                    nav = ui_shots.scene(name, language)
                    self.assertTrue(nav.dry)
                    self.assertGreater(fmt.total(nav.game.a.playtime()), 0)
                    self.assertEqual(nav.game.a.calls, [])
                    view = ui_shots.snapshot(nav, name)
                    self.assertIn(fmt.duration(42 * 3600 if name.endswith("profile") else 45000, language), str(view))


if __name__ == "__main__":
    unittest.main()
