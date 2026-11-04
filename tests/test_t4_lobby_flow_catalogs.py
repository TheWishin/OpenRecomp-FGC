"""The lobby is T4's normal online route in every supported language."""
import re
import unittest

from openrecomp import i18n


class T4LobbyFlowCatalogs(unittest.TestCase):
    def test_automatic_game_outcomes_are_translated(self):
        english = i18n.catalog("en")
        for language in i18n.LANGUAGES:
            catalog = i18n.catalog(language)
            for key in ("online.result_won", "online.result_lost", "online.result_draw"):
                with self.subTest(language=language, key=key):
                    self.assertTrue(key in catalog, "missing automatic game outcome")
                    self.assertTrue(catalog[key].strip())
                    if language != "en":
                        self.assertNotEqual(catalog[key], english[key])

    def test_advanced_direct_entry_is_translated_in_all_seven_catalogs(self):
        english = i18n.catalog("en")
        for language in i18n.LANGUAGES:
            catalog = i18n.catalog(language)
            with self.subTest(language=language):
                self.assertTrue("t4.direct_advanced" in catalog, "missing advanced direct entry")
                label = catalog["t4.direct_advanced"]
                self.assertTrue(label.strip())
                self.assertIn("LAN", label)
                if language != "en":
                    self.assertNotEqual(label, english["t4.direct_advanced"])

    def test_lobby_guidance_places_direct_connection_in_advanced_settings(self):
        advanced = {"en": "Advanced", "de": "Erweitert", "es": "Avanzado", "fr": "Avancé",
                    "ja": "詳細設定", "ko": "고급", "pt-BR": "Avançado"}
        keys = ("t4.lobby_mode_hint", "t4.direct_mode_hint", "t4.lobby_no_server")
        for language, title in advanced.items():
            catalog = i18n.catalog(language)
            for key in keys:
                with self.subTest(language=language, key=key):
                    self.assertIn(title, catalog[key])
                    self.assertEqual(re.findall(r"\{[^{}]*\}", catalog[key]), [])


if __name__ == "__main__":
    unittest.main()
