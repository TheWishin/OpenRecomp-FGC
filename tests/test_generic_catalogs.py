"""External games have complete guidance in every player language."""
import ast
import json
from pathlib import Path
import string
import unittest

from openrecomp import i18n


ROOT = Path(__file__).resolve().parents[1]
PREFIXES = ("generic.", "library.", "games.update_")
REQUIRED = (
    "library.add", "library.github", "library.local", "library.choose_source",
    "library.repository", "library.repository_hint", "library.third_party",
    "library.preview", "library.preview_summary", "library.requirement",
    "library.requirement_summary", "library.next", "library.accept",
    "library.manage", "library.check", "library.remove", "library.remove_confirm",
    "library.update_confirm", "library.update", "library.no_update", "library.failed",
    "library.unavailable", "library.loading", "library.saved", "library.invalid_source", "library.manifest_unavailable",
    "library.invalid_manifest", "library.preview_expired", "library.source_changed",
    "library.remove_failed", "generic.own_online", "generic.own_online_hint",
    "generic.lobby_arrangement", "generic.requirement_hint", "generic.requirement_bad_hash",
    "generic.build_manual", "generic.settings_error", "generic.source_checking",
    "generic.controls_hint", "generic.root_missing", "generic.running",
    "games.update_failed", "games.update_current", "games.update_ready",
)


class GenericCatalogTests(unittest.TestCase):
    def test_external_game_guidance_is_present_and_translated(self):
        english = i18n.catalog("en")
        formatter = string.Formatter()
        for language in i18n.LANGUAGES:
            catalog = i18n.catalog(language)
            for key in REQUIRED:
                with self.subTest(language=language, key=key):
                    self.assertIn(key, catalog)
                    self.assertIsInstance(catalog[key], str)
                    self.assertTrue(catalog[key].strip())
                    expected = {field for _, field, _, _ in formatter.parse(english[key]) if field}
                    actual = {field for _, field, _, _ in formatter.parse(catalog[key]) if field}
                    self.assertEqual(actual, expected)
                    if not expected:
                        self.assertEqual(i18n.localize("@" + key, language), catalog[key])
                    else:
                        values = {field: "sample" for field in expected}
                        self.assertEqual(i18n.localize(i18n.message(key, **values), language),
                                         catalog[key].format(**values))
                    if language != "en":
                        self.assertNotEqual(catalog[key], english[key])

    def test_external_game_keys_have_exact_catalog_parity(self):
        english = {key for key in i18n.catalog("en") if key.startswith(PREFIXES)}
        for language in i18n.LANGUAGES:
            with self.subTest(language=language):
                keys = {key for key in i18n.catalog(language) if key.startswith(PREFIXES)}
                self.assertEqual(keys, english)

    def test_new_external_game_references_have_catalog_entries(self):
        references = set(REQUIRED)
        for path in (ROOT / "openrecomp").rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    key = node.value.removeprefix("@")
                    if key.startswith(PREFIXES) and not key.endswith((".", "_")):
                        references.add(key)
        for language in i18n.LANGUAGES:
            for key in references:
                with self.subTest(language=language, key=key):
                    self.assertIn(key, i18n.catalog(language))

    def test_catalogs_do_not_repeat_keys(self):
        for language in i18n.LANGUAGES:
            pairs = json.loads((ROOT / "openrecomp" / "i18n" / (language + ".json")).read_text(
                encoding="utf-8"), object_pairs_hook=list)
            with self.subTest(language=language):
                keys = [key for key, _ in pairs]
                self.assertEqual(len(keys), len(set(keys)))


if __name__ == "__main__":
    unittest.main()
