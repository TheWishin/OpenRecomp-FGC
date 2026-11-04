"""Online hierarchy captions remain available in all seven catalogs."""
import unittest

from openrecomp import i18n


KEYS = """
open_rooms create_room room_empty join_invite access open password invite connection
match_options advanced_options room_name players format lock ping actions settings overview
""".split()


class OnlineHierarchyCatalogTests(unittest.TestCase):
    def test_all_hierarchy_captions_are_present_and_translated(self):
        self.assertEqual(len(i18n.LANGUAGES), 7)
        english = i18n.catalog("en")
        for language in i18n.LANGUAGES:
            catalog = i18n.catalog(language)
            for suffix in KEYS:
                key = "online_hierarchy." + suffix
                with self.subTest(language=language, key=key):
                    self.assertIn(key, catalog)
                    self.assertTrue(catalog[key].strip())
                    self.assertNotIn("?", catalog[key])
                    self.assertFalse("{" in catalog[key] or "}" in catalog[key])
            if language != "en":
                for suffix in ("room_empty", "create_room", "join_invite"):
                    key = "online_hierarchy." + suffix
                    self.assertNotEqual(catalog[key], english[key])

    def test_room_empty_caption_explains_the_next_action(self):
        self.assertEqual(i18n.catalog("en")["online_hierarchy.room_empty"],
                         "No open rooms \u2014 create one")


if __name__ == "__main__":
    unittest.main()
