import json
import string
import unittest
from pathlib import Path
from unittest import mock

from openrecomp import i18n


CATALOGS = Path(__file__).parents[1] / "openrecomp" / "i18n"


class CatalogAudit(unittest.TestCase):
    def test_generic_actions_are_translated_in_every_language(self):
        english = i18n.catalog("en")
        for code in i18n.LANGUAGES:
            if code == "en":
                continue
            for key in ("start", "build_game", "ranked", "rematch"):
                with self.subTest(code=code, key=key):
                    self.assertNotEqual(i18n.text(code, key).casefold(), english[key].casefold())

    def test_cjk_network_terms_use_the_local_script(self):
        for code, script in (("ja", "ロ"), ("ko", "롤")):
            self.assertIn(script, i18n.text(code, "rollback"))
            self.assertNotEqual(i18n.text(code, "lockstep"), "Lockstep")
        self.assertEqual(i18n.text("ja", "running"), "実行中")
        self.assertEqual(i18n.text("ja", "online.ping"), "応答時間")

    def test_german_generic_labels_are_translated(self):
        for key in ("section.build", "section.replays", "main", "fighter.main", "your_main",
                    "ranked_set", "best_of_three", "quick_match", "lobby_ranked"):
            self.assertNotEqual(i18n.text("de", key).casefold(), i18n.text("en", key).casefold(), key)
        self.assertNotIn("Ranked", i18n.text("de", "input_delay.lead"))

    def test_destructive_prompts_identify_the_safe_no_option_unambiguously(self):
        for code in ("es", "fr", "pt-BR"):
            no_option = "«" + i18n.text(code, "no") + "»"
            for key in ("dialog_hint", "rebuild_hint", "dialog.stop.text", "dialog.rebuild.text"):
                with self.subTest(code=code, key=key):
                    self.assertIn(no_option, i18n.text(code, key).replace(" ", ""))

    def test_every_catalog_formats_real_messages_with_preserved_fields(self):
        formatter = string.Formatter()
        english = i18n.catalog("en")
        for code in i18n.LANGUAGES:
            entries = json.loads((CATALOGS / (code + ".json")).read_text(encoding="utf-8"))
            self.assertEqual(set(entries), set(english), code)
            for key, template in entries.items():
                with self.subTest(code=code, key=key):
                    fields = [field for _, field, _, _ in formatter.parse(template) if field is not None]
                    expected = [field for _, field, _, _ in formatter.parse(english[key]) if field is not None]
                    self.assertCountEqual(fields, expected)
                    values = {field: "[" + field + "]" for field in fields}
                    rendered = i18n.text(code, key, **values)
                    for field in fields:
                        self.assertIn(values[field], rendered)

    def test_game_failure_code_formats_in_every_language(self):
        key = "t4.source.game_failed"
        for code in i18n.LANGUAGES:
            with self.subTest(code=code):
                expected = i18n.catalog(code)[key].format(code=17)
                self.assertEqual(i18n.text(code, key, code=17), expected)

    def test_deferred_game_failure_code_localizes_in_every_language(self):
        key = "t4.source.game_failed"
        message = i18n.message(key, code=17)
        for code in i18n.LANGUAGES:
            with self.subTest(code=code):
                expected = i18n.catalog(code)[key].format(code=17)
                self.assertEqual(i18n.localize(message, code), expected)

    def test_unparseable_locale_uses_the_next_detection_method(self):
        with mock.patch.object(i18n, "_ui_locale", return_value=None), \
                mock.patch.object(i18n.locale, "getlocale", side_effect=ValueError("unknown locale")), \
                mock.patch.object(i18n.locale, "getdefaultlocale", return_value=("de_DE", "UTF-8")):
            self.assertEqual(i18n.system_language(), "de")

    def test_unavailable_locale_detection_falls_back_to_english(self):
        with mock.patch.object(i18n, "_ui_locale", return_value=None), \
                mock.patch.object(i18n.locale, "getlocale", side_effect=ValueError("unknown locale")), \
                mock.patch.object(i18n.locale, "getdefaultlocale", side_effect=ValueError("unknown locale")):
            self.assertEqual(i18n.normalize(None), "en")

    def test_windows_locale_names_find_the_language(self):
        # QA run on a German Windows: Python's getlocale() says "German_Switzerland", and the launcher started in
        # English for every Windows player (only codes like "de_DE" were understood).
        for name, code in (("German_Switzerland", "de"), ("German_Germany", "de"), ("French_France", "fr"),
                           ("Spanish_Spain", "es"), ("Japanese_Japan", "ja"), ("Korean_Korea", "ko"),
                           ("Portuguese_Brazil", "pt-BR"), ("English_United States", "en"), ("de_CH", "de"),
                           ("pt_BR", "pt-BR")):
            with self.subTest(name=name), mock.patch.object(i18n, "_ui_locale", return_value=None), \
                    mock.patch.object(i18n.locale, "getlocale", return_value=(name, "1252")):
                self.assertEqual(i18n.system_language(), code)

    def test_windows_display_language_comes_first(self):
        with mock.patch.object(i18n, "_ui_locale", return_value="fr_FR"), \
                mock.patch.object(i18n.locale, "getlocale", return_value=("German_Switzerland", "1252")):
            self.assertEqual(i18n.system_language(), "fr")


if __name__ == "__main__":
    unittest.main()
