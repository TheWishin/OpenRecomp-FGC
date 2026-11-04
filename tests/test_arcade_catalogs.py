"""Arcade floor copy stays short and translated in every supported language."""
from string import Formatter
import unittest

from openrecomp import i18n


KEYS = """
title players cabinets rooms quick quick_note ranked ranked_note options more help you
idle searching playing in_room challenge watch profile join empty empty_note close
score actions options_note no_matches no_rooms
""".split()


class ArcadeCatalogTests(unittest.TestCase):
    def test_community_controls_are_translated_without_placeholder_fallback(self):
        suffixes = "sort recommended name players ping status live_rank newest oldest all_replays wins losses friends available new_messages mentions lobby_subtitle rank rating latest queue compose chat_short".split()
        for language in i18n.LANGUAGES:
            catalog = i18n.catalog(language)
            for suffix in suffixes:
                key = "community_ui." + suffix
                with self.subTest(language=language, key=key):
                    self.assertIn(key, catalog)
                    self.assertEqual(i18n.localize("@" + key, language), catalog[key])
                    self.assertTrue(catalog[key].strip())
                    self.assertNotIn("?", catalog[key])
                    self.assertLessEqual(len(catalog[key]), 40)
            if language != "en":
                for suffix in ("recommended", "newest", "oldest", "all_replays", "friends", "available", "new_messages", "lobby_subtitle"):
                    self.assertNotEqual(catalog["community_ui." + suffix], i18n.catalog("en")["community_ui." + suffix])

    def test_all_arcade_captions_are_brief_and_translated(self):
        self.assertEqual(len(i18n.LANGUAGES), 7)
        english = i18n.catalog("en")
        for language in i18n.LANGUAGES:
            catalog = i18n.catalog(language)
            for suffix in KEYS:
                key = "arcade." + suffix
                with self.subTest(language=language, key=key):
                    self.assertTrue(key in catalog, key)
                    self.assertTrue(catalog[key].strip())
                    self.assertNotIn("\n", catalog[key])
                    self.assertLessEqual(len(catalog[key]), 60)
                    placeholders = {field for _, field, _, _ in Formatter().parse(catalog[key]) if field}
                    self.assertEqual(placeholders, {"name"} if suffix == "playing" else set())
            if language != "en":
                for suffix in ("quick_note", "ranked_note", "empty_note", "options_note"):
                    key = "arcade." + suffix
                    self.assertNotEqual(catalog[key], english[key])


if __name__ == "__main__":
    unittest.main()
