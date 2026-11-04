"""Unplayed matches never become set results; all handles and traffic are inert."""
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from openrecomp import i18n
import test_t5_match_flow as flow


class UnplayedTests(unittest.TestCase):
    login = flow.T5MatchTests.login
    start = flow.T5MatchTests.start

    def setUp(self):
        root = Path('build/tmp-home')
        root.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.directory.cleanup)
        patch = mock.patch.dict(os.environ, T5_ONLINE_DIR=self.directory.name)
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch('openrecomp.adapters.t5_online.game_process_running', return_value=False)
        patch.start()
        self.addCleanup(patch.stop)
        self.a = flow.MatchSubject(self.directory.name)
        self.a.fake_driver = flow.Driver()
        self.addCleanup(self.a.online_close)

    def offer(self, rated=False):
        client = self.login(account=rated)
        client.ready = mock.Mock(return_value={})
        client.leave_match = mock.Mock(return_value={})
        self.a._online_room = dict(id='room', name='Local room')
        client.events.put(dict(t='match_found', match='one', opponent=dict(name='Peer'),
                               set=dict(id='set-one', rated=rated, casual=not rated, wins=[0, 0], first_to=1)))
        self.a.online_poll()
        self.a.online_poll()
        return client

    def test_failure_result_and_trailing_set_end_never_show_result(self):
        for rated in (False, True):
            for reason in ('ready_timeout', 'declined', 'peer_quit', 'no_peer', 'no_connection', 'udp_unreachable', 'relay_full'):
                with self.subTest(rated=rated, reason=reason):
                    self.a.online_close()
                    client = self.offer(rated)
                    self.a._online_match['my_ready'] = True
                    client.events.put(dict(t='match_result', match='one', status='void', reason=reason, rematch_window=20))
                    client.events.put(dict(t='set_end', set='set-one', reason=reason, wins=[0, 0]))
                    self.a.online_poll()
                    self.a.online_poll()
                    state = self.a.online_state()
                    self.assertEqual(state['phase'], 'logged_in')
                    self.assertFalse(state['set'])
                    self.assertFalse(state['match'])
                    self.assertFalse(state['capabilities']['rematch'])
                    self.assertEqual(state['room']['id'], 'room')
                    text = i18n.localize(state['match_failure']['message'], 'en')
                    self.assertIn('The match could not start:', text)
                    self.assertIn('Peer', text)
                    self.assertFalse(client.closed.is_set())

    def test_set_end_alone_with_zero_games_cannot_be_a_result(self):
        client = self.offer(True)
        client.events.put(dict(t='set_end', set='set-one', reason='ready_timeout', wins=[0, 0], status='forfeit'))
        self.a.online_poll()
        state = self.a.online_state()
        self.assertEqual(state['phase'], 'logged_in')
        self.assertEqual(state['set'], {})
        self.assertIn('did not get ready', i18n.localize(state['match_failure']['message'], 'en'))

    def test_failure_notice_expires_in_three_seconds_without_input(self):
        client = self.offer()
        with mock.patch('openrecomp.adapters.t5_match.time.monotonic', return_value=100):
            client.events.put(dict(t='match_cancel', match='one', reason='declined'))
            self.a.online_poll()
            self.assertEqual(self.a.online_state()['match_failure']['remaining'], 3)
        with mock.patch('openrecomp.adapters.t5_match.time.monotonic', return_value=103.1):
            self.assertTrue(self.a.online_poll())
            self.assertNotIn('match_failure', self.a.online_state())
            self.assertEqual(self.a.online_state()['message'], '@online.room_joined')

    def test_process_start_is_not_evidence_a_game_was_played(self):
        client = self.offer()
        self.start(client)
        client.events.put(dict(t='match_result', match='one', reason='no_peer', status='void'))
        self.a.online_poll()
        self.assertIn('match_failure', self.a.online_state())
        self.a._online_driver_notes([dict(kind='rematch_offer', match='one'), dict(kind='ask_result', match='one')])
        self.assertEqual(self.a.online_state()['phase'], 'logged_in')

    def test_played_game_keeps_result_on_disconnect(self):
        client = self.offer()
        self.start(client)
        self.a._online_driver_notes([dict(kind='game_state', state='fight')])
        client.events.put(dict(t='match_result', match='one', reason='peer_quit', status='forfeit'))
        client.events.put(dict(t='set_end', set='set-one', reason='peer_quit', wins=[0, 0]))
        self.a.online_poll()
        self.assertEqual(self.a.online_state()['phase'], 'result_sent')
        self.assertNotIn('match_failure', self.a.online_state())

    def test_ready_states_are_independent_and_reset_for_new_offer(self):
        client = self.offer()
        self.assertFalse(self.a.online_state()['match']['my_ready'])
        self.assertFalse(self.a.online_state()['match']['peer_ready'])
        client.events.put(dict(t='opponent_ready', match='one'))
        self.a.online_poll()
        self.assertTrue(self.a.online_state()['match']['peer_ready'])
        self.a.online_action('start_match')
        self.assertTrue(self.a.online_state()['match']['my_ready'])

    def test_all_failure_translations_preserve_literal_player_names(self):
        client = self.offer()
        self.a._online_match['my_ready'] = True
        self.a._online_match['opponent'] = '@online.set_ended'
        client.events.put(dict(t='match_cancel', match='one', reason='ready_timeout'))
        self.a.online_poll()
        for language in i18n.LANGUAGES:
            text = i18n.localize(self.a.online_state()['match_failure']['message'], language)
            self.assertIn('@online.set_ended', text)
            self.assertNotIn('{name}', text)

    def test_timeout_names_the_player_who_did_not_ready(self):
        client = self.offer()
        client.events.put(dict(t='opponent_ready', match='one'))
        client.events.put(dict(t='match_cancel', match='one', reason='ready_timeout'))
        self.a.online_poll()
        text = i18n.localize(self.a.online_state()['match_failure']['message'], 'en')
        self.assertIn(self.a.online_state()['name'], text)
        self.assertNotIn('Peer', text)

    def test_clean_exit_before_fight_does_not_request_a_result(self):
        client = self.offer()
        self.start(client)
        self.a._online_driver_notes([dict(kind='game_state', state='select'), dict(kind='ask_result', match='one')])
        self.assertEqual(self.a.online_state()['phase'], 'logged_in')
        self.assertIn('match_failure', self.a.online_state())
        self.assertFalse(self.a.online_state()['set'])

    def test_authoritative_round_score_keeps_result_if_local_fight_note_was_missed(self):
        client = self.offer()
        self.start(client)
        client.events.put(dict(t='match_result', match='one', status='onesided', score=[3, 1], reason='peer_quit'))
        self.a.online_poll()
        self.assertEqual(self.a.online_state()['phase'], 'result_sent')
        self.assertNotIn('match_failure', self.a.online_state())

    def test_server_games_counter_counts_attempts_and_is_not_played_evidence(self):
        client = self.offer()
        self.start(client)
        self.a._online_set['games'] = 1
        client.events.put(dict(t='match_result', match='one', status='void', reason='connection',
                               set=dict(id='set-one', games=1, wins=[0, 0])))
        client.events.put(dict(t='set_end', set='set-one', games=1, wins=[0, 0], reason='connection'))
        self.a.online_poll()
        self.assertEqual(self.a.online_state()['phase'], 'logged_in')
        self.assertIn('match_failure', self.a.online_state())

    def test_scored_set_keeps_result_if_round_score_and_local_note_are_absent(self):
        client = self.offer()
        self.start(client)
        client.events.put(dict(t='match_result', match='one', status='resolved',
                               set=dict(id='set-one', wins=[1, 0])))
        self.a.online_poll()
        self.assertEqual(self.a.online_state()['phase'], 'result_sent')
