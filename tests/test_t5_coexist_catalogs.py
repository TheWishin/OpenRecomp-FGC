"""Coexistence guidance is complete in each of the seven player languages."""
import ast
import json
from pathlib import Path
import string
import unittest

from openrecomp import i18n


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "t5.coexist.title", "t5.coexist.hint", "t5.coexist.settings",
    "t5.coexist.login", "t5.coexist.build_match", "t5.coexist.build_differs",
    "t5.coexist.build_unknown", "t5.coexist.build_blocked", "t5.coexist.source",
    "t5.coexist.choose_install", "t5.coexist.choose_hint", "t5.coexist.install_invalid",
)


class T5CoexistCatalogTests(unittest.TestCase):
    def test_coexistence_guidance_exists_in_all_seven_languages(self):
        self.assertEqual(set(i18n.LANGUAGES), {"en", "de", "es", "fr", "ja", "ko", "pt-BR"})
        for language in i18n.LANGUAGES:
            for key in REQUIRED:
                with self.subTest(language=language, key=key):
                    self.assertIn(key, i18n.catalog(language))
                    text = i18n.catalog(language)[key]
                    self.assertIsInstance(text, str)
                    self.assertTrue(text.strip())
                    self.assertEqual(i18n.localize("@" + key, language), text)

    def test_guidance_is_translated_and_preserves_format_fields(self):
        formatter = string.Formatter()
        english = i18n.catalog("en")
        for language in i18n.LANGUAGES:
            for key in REQUIRED:
                with self.subTest(language=language, key=key):
                    translated = i18n.catalog(language)[key]
                    expected = {field for _, field, _, _ in formatter.parse(english[key]) if field}
                    actual = {field for _, field, _, _ in formatter.parse(translated) if field}
                    self.assertEqual(actual, expected)
                    if language != "en":
                        self.assertNotEqual(translated, english[key])

    def test_new_coexistence_references_do_not_fall_back_to_english(self):
        references = set(REQUIRED)
        for path in (ROOT / "openrecomp").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                value = node.value.removeprefix("@")
                if value.startswith("t5.coexist.") and not value.endswith("."):
                    references.add(value)
        for language in i18n.LANGUAGES:
            for key in references:
                with self.subTest(language=language, key=key):
                    self.assertIn(key, i18n.catalog(language))

    def test_catalogs_have_no_duplicate_keys(self):
        for language in i18n.LANGUAGES:
            with self.subTest(language=language):
                pairs = json.loads((ROOT / "openrecomp" / "i18n" / (language + ".json")).read_text(
                    encoding="utf-8"), object_pairs_hook=list)
                keys = [key for key, _value in pairs]
                self.assertEqual(len(keys), len(set(keys)))


if __name__ == "__main__":
    unittest.main()
