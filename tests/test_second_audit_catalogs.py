"""Catalog guidance and default test discovery stay local and explicit."""
import os
from pathlib import Path
import unittest
from unittest import mock

from openrecomp import i18n
import test_online_local_lobby as local_lobby


class SecondAuditCatalogs(unittest.TestCase):
    def test_blank_t4_address_guidance_never_promises_a_built_in_server(self):
        # The T4 lobby has no default server: a blank address is the "no T4 server" state.
        for language in i18n.LANGUAGES:
            with self.subTest(language=language):
                self.assertNotIn("127.0.0.1", i18n.text(language, "t4.online_setup_hint"))
                self.assertNotEqual(i18n.text(language, "t4.lobby_no_server"), "t4.lobby_no_server")

    def test_search_guidance_does_not_send_players_to_the_old_launcher(self):
        for language in i18n.LANGUAGES:
            for key in ("search.hint", "ranked.lead"):
                with self.subTest(language=language, key=key):
                    self.assertNotIn("T5DR", i18n.text(language, key))

    def test_german_practice_and_host_labels_use_german_words(self):
        for key in ("practice.hint", "practice.lead", "training.hint", "training.lead", "ranked.lead"):
            with self.subTest(key=key):
                self.assertNotRegex(i18n.text("de", key), r"\b(?:Practice|Ready-Check|Startup|Moves)\b")
        self.assertEqual(i18n.text("de", "t4.direct_host"), "Spiel anbieten")
        self.assertEqual(i18n.text("de", "t4.direct_role_host"), "Gastgeber")

    def test_default_local_lobby_integration_skips_before_external_discovery(self):
        with mock.patch.dict(os.environ, {"OPENRECOMP_TEST_LOCAL_LOBBY": "0"}), \
                mock.patch.object(Path, "is_dir", side_effect=AssertionError("external discovery")):
            with self.assertRaises(unittest.SkipTest):
                local_lobby.LocalLobbyTests.setUpClass()


if __name__ == "__main__":
    unittest.main()
