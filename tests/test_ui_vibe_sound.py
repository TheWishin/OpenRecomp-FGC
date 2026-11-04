"""Original theme cues, semantic match events and immediate playback suppression."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock
from PySide6.QtCore import Qt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from openrecomp import ui_sound
from openrecomp.app import Backend
from openrecomp.nav import Game, Nav
from test_nav import Fake, manifest
from test_ui_sound import Clock, FakeWinMM, Recorder
import test_ui_sound


class Output(Recorder):
    def __init__(self):
        super().__init__()
        self.stops = 0

    def stop(self):
        self.stops += 1


class ThemeCues(unittest.TestCase):
    def test_every_theme_has_original_short_soft_cues(self):
        for theme in ("t4", "t5dr"):
            for name in ui_sound.NAMES + ui_sound.EVENT_NAMES:
                with self.subTest(theme=theme, name=name):
                    rate, channels, samples = ui_sound.synthesized(name, theme)
                    self.assertEqual((rate, channels), (48000, 1))
                    self.assertTrue(0.03 <= len(samples) / rate <= 0.30)
                    self.assertEqual((samples[0], samples[-1]), (0, 0))
                    self.assertLessEqual(max(map(abs, samples)), 16384)
                    self.assertLess(abs(sum(samples) / len(samples)), 100)
        self.assertNotEqual(ui_sound.synthesized("move", "t4")[2], ui_sound.synthesized("move", "t5dr")[2])
        self.assertIsNone(ui_sound.synthesized("unknown", "t4"))

    def test_themed_events_use_the_volume_and_mute_gate(self):
        out = Output()
        sounds = ui_sound.UiSounds(output=out, clock=Clock())
        sounds.set_theme("t4")
        self.assertTrue(sounds.play(ui_sound.READY))
        self.assertEqual(out.played, ["t4:ready"])
        sounds.configure(False, 70)
        self.assertEqual(out.stops, 1)
        self.assertEqual(out.volumes, [70])
        self.assertFalse(sounds.play(ui_sound.WIN))
        sounds.set_theme("unknown")
        self.assertEqual(sounds.theme, "")

    def test_losing_focus_stops_a_tail_once_without_a_new_cue(self):
        out = Output()
        sounds = ui_sound.UiSounds(output=out)
        sounds.play(ui_sound.NOTIFY)
        self.assertFalse(sounds.play(None, active=False))
        self.assertFalse(sounds.play(None, active=False))
        self.assertEqual(out.stops, 1)

    def test_synthesis_is_cached_on_the_audio_worker(self):
        fake = FakeWinMM()
        out = ui_sound.WinMMOutput(ui_sound.load(), 50, winmm=fake)
        try:
            with mock.patch.object(ui_sound, "synthesized", wraps=ui_sound.synthesized) as synth:
                out.play("t5dr:win")
                test_ui_sound.WinMM.wait(self, fake, 1)
                self.assertEqual(synth.call_count, 1)
                out.play("t5dr:win")
                test_ui_sound.WinMM.wait(self, fake, 2)
                self.assertEqual(synth.call_count, 1)
                self.assertIn("t5dr:win", out._buffers)
            out.stop()
            test_ui_sound.WinMM.wait(self, fake, 3)
            self.assertEqual(fake.calls[-1], (False, 0))
        finally:
            out.close()

    def test_backend_uses_the_selected_game_theme(self):
        window = mock.Mock()
        window.isActive.return_value = True
        window.windowState.return_value = Qt.WindowNoState
        out = Output()
        game = SimpleNamespace(m={"adapter": "t5dr"}, a=SimpleNamespace(running=lambda: False))
        backend = SimpleNamespace(nav=SimpleNamespace(game=game, games=[game], take_sound=lambda: "confirm"),
                                  window=window, sounds=ui_sound.UiSounds(output=out))
        Backend._play_sound(backend)
        self.assertEqual(out.played, ["t5dr:confirm"])
        window.isActive.return_value = False
        Backend._play_sound(backend)
        self.assertEqual(out.stops, 1)


class MatchEvents(unittest.TestCase):
    def setUp(self):
        self.adapter = Fake(manifest("a"))
        self.game = Game(self.adapter.m, self.adapter)
        self.nav = Nav([self.game], language="en")

    def observe(self, **state):
        self.nav.observe_online_sound(self.game, state)
        return self.nav.take_sound()

    def test_ready_and_result_are_once_per_match(self):
        match = {"id": "one"}
        self.assertEqual(self.observe(phase="starting", match=match), ui_sound.READY)
        self.assertIsNone(self.observe(phase="starting", match=match))
        self.assertEqual(self.observe(phase="result", match=match, set={"result": "win"}), ui_sound.WIN)
        self.assertIsNone(self.observe(phase="result_sent", match=match, set={"result": "win"}))
        self.assertEqual(self.observe(phase="result_sent", match={"id": "two"}, set={"result": "loss"}), ui_sound.LOSS)

    def test_no_replay_after_a_game_running_suppresses_an_event(self):
        self.adapter.is_running = True
        self.assertIsNone(self.observe(phase="starting", match={"id": "one"}))
        self.adapter.is_running = False
        self.assertIsNone(self.observe(phase="starting", match={"id": "one"}))

    def test_unknown_and_disputed_result_do_not_guess_a_winner(self):
        self.assertIsNone(self.observe(phase="result_sent", match={"id": "one"}, result={"winner": "private"}))
        self.assertIsNone(self.observe(phase="result_sent", message="@online.result_disputed"))

    def test_last_three_seconds_warn_once_each_then_stop(self):
        row = dict(age=1.0, seconds=5, game="a")
        self.nav._global_offer_clock = {"a/match:one": row}
        sounds = []
        for age in (1, 2, 2.1, 3, 3.4, 4, 4.2, 5, 6):
            row["age"] = age
            self.nav.tick_offer_sounds()
            sound = self.nav.take_sound()
            if sound:
                sounds.append(sound)
        self.assertEqual(sounds, [ui_sound.COUNTDOWN] * 3)

    def test_suppressed_countdown_is_not_replayed(self):
        self.nav._global_offer_clock = {"a/match:one": dict(age=2, seconds=5, game="a")}
        self.adapter.is_running = True
        self.nav.tick_offer_sounds()
        self.assertIsNone(self.nav.take_sound())
        self.adapter.is_running = False
        self.nav.tick_offer_sounds()
        self.assertIsNone(self.nav.take_sound())


if __name__ == "__main__":
    unittest.main()
