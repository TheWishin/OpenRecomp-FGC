"""Social text entry stays on the pad and never submits a client request."""
import unittest

from openrecomp.nav import Game, Nav
from test_online_nav import Lobby


class SocialKeyboardTests(unittest.TestCase):
    def setUp(self):
        self.adapter = Lobby()
        self.nav = Nav([Game(self.adapter.m, self.adapter)], language="en")
        self.nav.screen = "hub"
        self.nav.sec[self.nav.game.id] = "online"

    def test_room_password_is_masked_and_preserves_spaces(self):
        secret = " room secret "
        self.adapter.texts["online_room_password"] = secret
        self.nav._open_osk("online_room_password")
        self.assertEqual(self.nav.osk["title"], "@online.room_password")
        self.assertNotIn(secret, str(self.nav.view()))
        self.assertEqual(self.nav.view()["osk"]["text"], "•" * len(secret) + "_")
        self.nav.act("play", device="xbox")
        self.assertEqual(self.adapter.calls, [("text", "online_room_password", secret)])

    def test_social_fields_have_titles_and_pad_done(self):
        for field in ("room_name", "room_code", "friend_name"):
            with self.subTest(field=field):
                tid = "online_" + field
                self.adapter.texts[tid] = "  Player  "
                self.nav._open_osk(tid)
                self.assertEqual(self.nav.osk["title"], "@online." + field)
                self.nav.act("play", device="xbox")
                self.assertEqual(self.adapter.texts[tid], "Player")

    def test_dry_password_done_never_writes(self):
        self.nav.dry = True
        self.nav._open_osk("online_room_password")
        self.nav.osk["text"] = "private"
        self.nav.act("play", device="xbox")
        self.assertEqual(self.adapter.calls, [])


if __name__ == "__main__":
    unittest.main()
