"""All day-one T4 lobby controls have translated text."""
import unittest

from openrecomp import i18n


ONLINE_KEYS = [
    "online.players",
    "online.rooms",
    "online.chat",
    "online.refresh_players",
    "online.refresh_rooms",
    "online.challenge",
    "online.accept_challenge",
    "online.decline_challenge",
    "online.create_room",
    "online.join_room",
    "online.leave_room",
    "online.send_chat",
    "online.start_match",
    "online.stop_match",
    "online.result",
    "online.result_hint",
    "online.result_win",
    "online.result_loss",
    "online.result_none",
    "online.rank",
    "online.no_players",
    "online.no_rooms",
    "online.no_chat",
    "online.challenge_hint",
    "online.room_hint",
    "online.chat_hint",
    "online.start_hint",
    "online.match_active",
    "online.cancel_match",
    "online.return_lobby",
    "online.ranked_unavailable",
    "online.lobby_updated",
    "online.challenge_sent",
    "online.challenge_answered",
    "online.room_joined",
    "online.room_left",
    "online.chat_sent",
    "online.chat_required",
    "online.starting",
    "online.playing",
    "online.result_prompt",
    "online.result_sent",
    "online.t4_matched",
    "online.result_confirmed",
    "online.result_disputed",
    "online.result_void"
]


class T4OnlineCatalogTests(unittest.TestCase):
    def test_every_day_one_lobby_message_exists_in_all_seven_catalogs(self):
        for language in i18n.LANGUAGES:
            catalog = i18n.catalog(language)
            for key in ONLINE_KEYS:
                with self.subTest(language=language, key=key):
                    self.assertIn(key, catalog)
                    self.assertTrue(catalog[key].strip())

    def test_shared_login_and_runtime_errors_do_not_name_another_game(self):
        keys = ("game_running", "process_unknown", "build_required", "client_missing",
                "insecure", "version_mismatch", "login_hint")
        for language in i18n.LANGUAGES:
            for key in keys:
                self.assertNotIn("T5DR", i18n.catalog(language)["online." + key])


if __name__ == "__main__":
    unittest.main()

