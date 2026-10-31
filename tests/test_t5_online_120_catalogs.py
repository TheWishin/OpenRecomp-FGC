"""The installed T5DR client's extra screens never fall back to missing text."""
import ast
from pathlib import Path
import string
import unittest

from openrecomp import i18n


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = """
online.tournaments online.tour_bracket online.tour_standings online.tour_confirm
online.spectating online.watch_hint online.watch_stopped online.watch_unavailable
online.profile online.profile_hint online.leaderboard online.community_stats
online.ranked_chars online.history_status online.history_reason online.voids_24h
online.community online.community_hint online.room_tables_mode online.dev_badge
online.mention_player online.mention_notice online.character_locked online.set_score
online.set_game online.first_to online.set_game_label online.first_to_label
online.rematch_confirm online.rematch_countdown online.ingame_expired online.life_hint
online.match_health online.training_rule online.challenge_preferences
online.challenge_preferences_hint online.challenge_delay_hint online.challenge_ft
online120.account_tools online120.account_hint online120.blocks_hint
online120.password_changed online120.recovered
t5.screen_side t5.replay_folder_hint t5.auto_spectate_hint t5.delay_frames
""".split()
FEATURES = (
    "adapters/t5_tournaments.py", "adapters/t5_profiles.py",
    "adapters/t5_spectating.py", "adapters/t5_community.py",
    "adapters/t5_accounts.py", "adapters/t5_rules.py", "adapters/t5_challenges.py",
    "nav_tournaments.py", "nav_profiles.py", "nav_spectating.py", "nav_community.py",
    "nav_accounts.py", "nav_rules.py", "nav_challenges.py",
)


class T5Online120CatalogTests(unittest.TestCase):
    def test_each_new_screen_has_text_in_every_catalog(self):
        for language in i18n.LANGUAGES:
            catalog = i18n.catalog(language)
            for key in REQUIRED:
                with self.subTest(language=language, key=key):
                    self.assertIn(key, catalog)
                    self.assertTrue(catalog[key].strip())

    def test_feature_references_resolve_without_english_fallback(self):
        keys = set(REQUIRED)
        for relative in FEATURES:
            path = ROOT / "openrecomp" / relative
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    value = node.value
                    if value.startswith("@") and len(value) > 1 and not value.endswith(("_", ".")):
                        keys.add(value[1:])
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr == "message" and node.args:
                        key = node.args[0]
                        if isinstance(key, ast.Constant) and isinstance(key.value, str):
                            keys.add(key.value)
        for language in i18n.LANGUAGES:
            for key in keys:
                with self.subTest(language=language, key=key):
                    self.assertIn(key, i18n.catalog(language))

    def test_set_and_delay_messages_format_the_same_values_in_every_language(self):
        cases = {
            "online.set_score": dict(mine=2, theirs=1),
            "online.set_game": dict(number=2, best=3),
            "online.first_to": dict(wins=2),
            "online.set_next": dict(seconds=5),
            "online.rematch_countdown": dict(seconds=5),
            "online.challenge_ft": dict(wins=3),
            "online.match_health": dict(you=80, opponent=100),
            "t5.delay_frames": dict(count=8),
        }
        formatter = string.Formatter()
        for language in i18n.LANGUAGES:
            for key, values in cases.items():
                with self.subTest(language=language, key=key):
                    template = i18n.catalog(language)[key]
                    fields = {field for _, field, _, _ in formatter.parse(template) if field}
                    self.assertEqual(fields, set(values))
                    rendered = i18n.text(language, key, **values)
                    for value in values.values():
                        self.assertIn(str(value), rendered)

    def test_new_instructions_are_translated(self):
        keys = (
            "online.watch_hint", "online.profile_hint", "online.stats_hint",
            "online.community_hint", "online.life_hint", "online.training_rule",
            "online.challenge_preferences_hint", "online.challenge_delay_hint",
            "online120.account_hint", "online120.blocks_hint", "t5.replay_folder_hint",
            "t5.auto_spectate_hint", "online.character_locked", "online.ingame_expired",
        )
        for language in i18n.LANGUAGES:
            if language == "en":
                continue
            for key in keys:
                with self.subTest(language=language, key=key):
                    self.assertNotEqual(i18n.catalog(language)[key], i18n.catalog("en")[key])


if __name__ == "__main__":
    unittest.main()
