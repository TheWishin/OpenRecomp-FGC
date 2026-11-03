"""This PC's game speed goes with every login, as the native Online tab sends it (lobby: slow-PC warning, ranked minimum)."""
import json
import unittest
from types import SimpleNamespace
from unittest import mock

import test_t5_match_flow as flow


class PerfTests(unittest.TestCase):
    login = flow.T5MatchTests.login

    def setUp(self):
        flow.T5MatchTests.setUp(self)
        # The installed LobbyClient has perf_fps (None until set); an older fake client does not.
        patch = mock.patch("test_online_adapter.Client.perf_fps", None, create=True)
        patch.start()
        self.addCleanup(patch.stop)

    def driver_module(self, fps):
        return SimpleNamespace(__file__=self.directory.name + "/lobby/t5lobby/match_driver.py",
                               fps_from_logs=mock.Mock(return_value=fps))

    def test_login_sends_the_newest_game_logs_speed_when_no_match_was_played(self):
        for log_fps, expected in ((58.2, 58.2), (None, None), (5000.0, None)):
            module = self.driver_module(log_fps)
            with mock.patch.object(type(self.a), "_online_driver_module", return_value=module, create=True):
                client = self.login()
            self.assertEqual(client.perf_fps, expected)
            self.a.online_close()

    def test_an_older_client_without_perf_fps_is_left_alone(self):
        import test_online_adapter
        del test_online_adapter.Client.perf_fps
        self.addCleanup(setattr, test_online_adapter.Client, "perf_fps", None)
        with mock.patch.object(type(self.a), "_online_driver_module", return_value=self.driver_module(50.0), create=True):
            client = self.login()
            self.assertFalse(hasattr(client, "perf_fps"))

    def test_last_online_match_speed_wins_and_is_remembered_after_a_match(self):
        module = self.driver_module(31.0)
        with mock.patch.object(type(self.a), "_online_driver_module", return_value=module, create=True):
            client = self.login()
            self.assertEqual(client.perf_fps, 31.0)
            # A finished match's speed goes into OpenRecomp's own online settings ...
            self.a.fake_driver.last_fps = 59.9
            client.events.put(dict(t="match_found", match="one"))
            self.a.online_poll()
            self.a.online_poll()
            with open(self.a.online_cfg_path(), encoding="utf-8") as stream:
                self.assertEqual(json.load(stream)["last_fps"], 59.9)
            self.a.online_close()
            # ... and the next login sends it instead of the log's guess.
            self.assertEqual(self.login().perf_fps, 59.9)


if __name__ == "__main__":
    unittest.main()
