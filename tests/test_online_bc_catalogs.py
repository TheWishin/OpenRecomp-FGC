"""Ready checks and social controls have text in every supported language."""
import string
import unittest

from openrecomp import i18n


KEYS = """
waiting_peer_ready connection_direct connection_relay connection_fallback peer_quit
peer_timeout connection_failed game_build_mismatch ready_hint rematch rematch_hint
rematch_wait rematch_declined rematch_offer game_closed match_error select loading
room_name room_password room_code join_room_code create_password_room create_code_room
room_invite_code private_room_hint friends refresh_friends friend_name add_friend
remove_friend invite_friend invite_room accept_friend decline_friend cancel_friend
accept_invite decline_invite cancel_invite no_friends friends_hint friend_requests
friend_pending invites friend_status room_password_required room_code_required
friend_name_required friend_updated friend_requested friend_answered friend_removed
friend_cancelled invite_sent invite_answered invite_ended invite_wait room_locked
social_unavailable friend_online friend_in_match friend_offline ready_expired relay_full
peer_declined
""".split()


class OnlineBCCatalogTests(unittest.TestCase):
    def test_ready_match_and_social_messages_exist_in_all_languages(self):
        for language in i18n.LANGUAGES:
            catalog = i18n.catalog(language)
            for suffix in KEYS:
                key = "online." + suffix
                with self.subTest(language=language, key=key):
                    self.assertIn(key, catalog)
                    self.assertTrue(catalog[key].strip())

    def test_new_messages_keep_the_same_placeholders(self):
        formatter = string.Formatter()
        english = i18n.catalog("en")
        for suffix in KEYS:
            key = "online." + suffix
            expected = {field for _, field, _, _ in formatter.parse(english[key]) if field}
            for language in i18n.LANGUAGES:
                with self.subTest(language=language, key=key):
                    actual = {field for _, field, _, _ in formatter.parse(i18n.catalog(language)[key]) if field}
                    self.assertEqual(actual, expected)

    def test_shared_match_messages_do_not_name_one_game(self):
        for language in i18n.LANGUAGES:
            for suffix in ("start_hint", "result_hint", "result_prompt"):
                with self.subTest(language=language, suffix=suffix):
                    self.assertNotIn("T4", i18n.catalog(language)["online." + suffix])
                    self.assertNotIn("T5DR", i18n.catalog(language)["online." + suffix])


if __name__ == "__main__":
    unittest.main()
