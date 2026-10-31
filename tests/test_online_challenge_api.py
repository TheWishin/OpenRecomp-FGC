"""Challenge preferences retain the shared client's public challenge method."""
import unittest
from unittest import mock

from openrecomp import nav_challenges
from openrecomp.adapters import t5_challenges as challenges
from test_t5_challenges import Client, Owner


class PublicChallengeClient(Client):
    send_challenge = None

    def challenge(self, target, delay=None, first_to=1):
        return Client.send_challenge(self, target, delay=delay, first_to=first_to)


class PublicChallengeTests(unittest.TestCase):
    def test_public_challenge_method_keeps_preferences_and_negotiated_choices(self):
        with mock.patch("socket.socket", side_effect=AssertionError("external I/O denied")), mock.patch(
                "subprocess.Popen", side_effect=AssertionError("game start denied")):
            owner = Owner()
            owner._online_client = PublicChallengeClient()
            challenges.init(owner)
            nav = mock.Mock()
            nav._online_action.side_effect = lambda _game, request: challenges.action(
                owner, request, owner._online_client)
            game = object()
            for field, choice in (("delay", "8"), ("first_to", "3"), ("side", "1")):
                state = challenges.state(owner)
                rows = nav_challenges.rows(nav, game, state, mock.Mock())
                row = next(item for item in rows if item.get("id") == "challenge_" + field)
                row["set"](choice)
                owner.finish()
            self.assertTrue(challenges.state(owner)["capabilities"]["challenge_preferences"])
            self.assertTrue(challenges.action(owner, "challenge:peer", owner._online_client))
            owner.finish()
            self.assertIn(("prefs", 1, "random"), owner._online_client.calls)
            self.assertIn(("challenge", "peer", 8, 3), owner._online_client.calls)
            self.assertEqual(owner.saved[-1]["casual_side"], 1)
            self.assertFalse(owner.closed)


if __name__ == "__main__":
    unittest.main()
