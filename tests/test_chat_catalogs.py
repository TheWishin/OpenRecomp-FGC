"""Controller chat and moderation text is complete in every language."""
import ast
from pathlib import Path
import string
import unittest

from openrecomp import i18n


ROOT = Path(__file__).resolve().parents[1] / "openrecomp"
REQUIRED = """
mute unmute muted_players refresh_mutes mute_hint block block_hint filter_notice
mute_updated block_updated filter_blocked chat_muted moderation_unavailable
moderation_failed name_blocked room_name_blocked report_reason
private_title private_hint private_open private_unread private_compose private_send
private_close private_empty private_history private_unavailable private_blank
private_sent report_selection report_sent private_select private_selected
private_report private_report_hint
""".split()
FEATURES = ("nav_moderation.py", "nav_private_chat.py", "nav_keyboard.py",
            "adapters/t5_moderation.py", "adapters/t5_private_chat.py")


class ChatCatalogTests(unittest.TestCase):
    def test_chat_and_moderation_keys_exist_in_all_seven_languages(self):
        self.assertEqual(len(i18n.LANGUAGES), 7)
        keys = {"online_chat." + key for key in REQUIRED}
        for relative in FEATURES:
            path = ROOT / relative
            if not path.exists():
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if node.value.startswith("@online_chat."):
                        keys.add(node.value[1:])
                    elif node.value.startswith("online_chat.") and not node.value.endswith("."):
                        keys.add(node.value)
        formatter = string.Formatter()
        for language in i18n.LANGUAGES:
            for key in keys:
                with self.subTest(language=language, key=key):
                    catalog = i18n.catalog(language)
                    self.assertIn(key, catalog)
                    self.assertTrue(catalog[key].strip())
                    fields = lambda text: {field for _, field, _, _ in formatter.parse(text) if field}
                    self.assertEqual(fields(catalog[key]), fields(i18n.catalog("en")[key]))

    def test_unread_marker_preserves_count_in_every_language(self):
        for language in i18n.LANGUAGES:
            with self.subTest(language=language):
                self.assertIn("3", i18n.text(language, "online_chat.private_unread", count=3))

    def test_instructions_are_translated(self):
        for language in i18n.LANGUAGES:
            if language == "en":
                continue
            for key in ("mute_hint", "block_hint", "private_report_hint", "private_hint"):
                with self.subTest(language=language, key=key):
                    key = "online_chat." + key
                    self.assertNotEqual(i18n.catalog(language)[key], i18n.catalog("en")[key])


if __name__ == "__main__":
    unittest.main()
