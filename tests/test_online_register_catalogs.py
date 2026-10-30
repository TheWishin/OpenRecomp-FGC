"""Account registration and recovery text exists in every supported language."""
import string
import unittest

from openrecomp import i18n


class OnlineRegisterCatalogTests(unittest.TestCase):
    def test_register_label_exists_and_localizes_in_every_language(self):
        for language in i18n.LANGUAGES:
            for suffix in ("register", "recovery_codes", "recovery_hint", "recovery_done"):
                key = "online." + suffix
                with self.subTest(language=language, key=key):
                    catalog = i18n.catalog(language)
                    self.assertIn(key, catalog)
                    self.assertTrue(catalog[key].strip())
                    self.assertEqual(i18n.localize("@" + key, language), catalog[key])

    def test_recovery_messages_have_no_format_placeholders(self):
        formatter = string.Formatter()
        for language in i18n.LANGUAGES:
            for suffix in ("recovery_codes", "recovery_hint", "recovery_done"):
                with self.subTest(language=language, suffix=suffix):
                    fields = [field for _, field, _, _ in formatter.parse(
                        i18n.catalog(language)["online." + suffix]) if field is not None]
                    self.assertEqual(fields, [])


if __name__ == "__main__":
    unittest.main()
