"""Playtime crosses the adapter boundary and refreshes the scene without game launches."""
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp import app
from openrecomp.adapters.base import Adapter
from openrecomp.nav import Game
from tools.package_release import SOURCE_GROUPS
from test_nav import manifest


class PlaytimeBackend(unittest.TestCase):
    def test_loading_games_attaches_one_local_store_without_starting_tracking(self):
        from openrecomp import playtime
        manifests = [manifest('t4'), manifest('t5dr')]
        store = mock.Mock()
        with mock.patch.object(app.mf, 'load_all', return_value=(manifests, [])), \
                mock.patch.object(app.adapters, 'make', side_effect=lambda m, c: Adapter(m, c)), \
                mock.patch.object(playtime, 'shared_store', return_value=store):
            games, problems = app.load_games({})
        self.assertEqual(problems, [])
        self.assertEqual([g.a.playtime_store for g in games], [store, store])
        self.assertEqual(store.mock_calls, [])

    def test_quit_checkpoints_shared_store_once_before_closing(self):
        store = mock.Mock()
        games = [SimpleNamespace(a=SimpleNamespace(playtime_store=store)) for _ in range(2)]
        owner = SimpleNamespace(nav=SimpleNamespace(games=games), window=None)
        with mock.patch.object(app.QGuiApplication, 'quit') as quit_app:
            app.Backend._quit(owner)
        store.checkpoint.assert_called_once_with()
        quit_app.assert_called_once_with()

    def test_new_playtime_refreshes_even_when_game_is_still_running(self):
        adapter = Adapter(manifest('sample'))
        stats = dict(offline_seconds=60, online_seconds=0, sessions=1, last_played='2026-11-04')
        adapter.playtime = lambda: dict(stats)
        owner = SimpleNamespace(nav=SimpleNamespace(games=[Game(adapter.m, adapter)]),
                                window=None, _was_running=True, _was_building=False, _last_hero={})
        self.assertTrue(app.Backend._slow_changes(owner, True))
        self.assertFalse(app.Backend._slow_changes(owner, True))
        stats['offline_seconds'] = 119
        self.assertFalse(app.Backend._slow_changes(owner, True))
        stats['offline_seconds'] = 120
        self.assertTrue(app.Backend._slow_changes(owner, True))
        self.assertFalse(app.Backend._slow_changes(owner, True))

    def test_release_inventory_contains_tracker_and_formatter(self):
        self.assertIn('nav_playtime.py', SOURCE_GROUPS['openrecomp'])
        self.assertIn('playtime.py', SOURCE_GROUPS['openrecomp'])
        self.assertIn('playtime_format.py', SOURCE_GROUPS['openrecomp'])


if __name__ == '__main__':
    unittest.main()
