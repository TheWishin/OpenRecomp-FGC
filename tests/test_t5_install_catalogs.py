"""Incomplete T5DR installs explain the repair in every player language."""
import string
import unittest

from openrecomp import i18n


INSTALL_KEYS = (
    "t5.install_incomplete_python", "t5.install_incomplete_tools",
    "t5.reinstall", "t5.choose_install", "support.finding.t5_install.title",
    "t5.folder_taken", "t5.folder_several", "t5.folder_old", "t5.update_here", "t5.folder_update",
)


class T5InstallCatalogTests(unittest.TestCase):
    def test_folder_guidance_preserves_format_fields_in_every_language(self):
        formatter = string.Formatter()
        english = i18n.catalog("en")
        for language in i18n.LANGUAGES:
            for key in INSTALL_KEYS:
                with self.subTest(language=language, key=key):
                    expected = {field for _, field, _, _ in formatter.parse(english[key]) if field}
                    actual = {field for _, field, _, _ in formatter.parse(i18n.catalog(language)[key]) if field}
                    self.assertEqual(actual, expected)

    def test_repair_guidance_is_translated_in_all_seven_catalogs(self):
        self.assertEqual(set(i18n.LANGUAGES), {"en", "de", "es", "fr", "ja", "ko", "pt-BR"})
        english = i18n.catalog("en")
        for language in i18n.LANGUAGES:
            for key in INSTALL_KEYS:
                with self.subTest(language=language, key=key):
                    catalog = i18n.catalog(language)
                    self.assertTrue(key in catalog, key)
                    self.assertTrue(catalog[key].strip())
                    fields = {field: field for _, field, _, _ in string.Formatter().parse(catalog[key]) if field}
                    message = i18n.message(key, **fields)
                    self.assertEqual(i18n.localize(message, language), catalog[key].format(**fields))
                    if language != "en":
                        self.assertNotEqual(catalog[key], english[key])

    def test_python_failure_explains_what_to_reinstall_and_what_is_kept(self):
        self.assertEqual(i18n.catalog("en")["t5.install_incomplete_python"],
                         "This Tekken 5 DR install is incomplete: its Python (python folder) is missing or damaged. "
                         "Reinstall T5DR (your game files and saves stay).")
        for language in i18n.LANGUAGES:
            for key in ("t5.install_incomplete_python", "t5.install_incomplete_tools"):
                with self.subTest(language=language, key=key):
                    self.assertIn("T5DR", i18n.catalog(language)[key])
            self.assertIn("python", i18n.catalog(language)["t5.install_incomplete_python"])


if __name__ == "__main__":
    unittest.main()
