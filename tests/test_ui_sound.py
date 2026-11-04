"""Menu sounds: the WAVs the generator makes, which sound each press makes (pad, keyboard, mouse), the setting, and
the player's gate. Nothing reaches a speaker: the player is a recorder, winmm is a fake."""
import array
import os
import sys
import threading
import unittest
import wave
from types import SimpleNamespace
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt  # noqa: E402

from openrecomp import ui_sound  # noqa: E402
from openrecomp.app import Backend, click  # noqa: E402
from openrecomp.nav import Game, Nav  # noqa: E402
from test_nav import Fake, manifest  # noqa: E402
import make_ui_sounds  # noqa: E402


class Recorder:
    """The output a test listens to: what would have played."""
    available = True

    def __init__(self):
        self.played, self.volumes, self.closed = [], [], False

    def play(self, name):
        self.played.append(name)

    def set_volume(self, volume):
        self.volumes.append(volume)

    def close(self):
        self.closed = True


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class GeneratedFiles(unittest.TestCase):
    def test_every_sound_is_committed_as_the_generator_makes_it(self):
        for name in ui_sound.NAMES:
            with self.subTest(sound=name):
                path = os.path.join(ui_sound.SOUND_DIR, name + ".wav")
                with wave.open(path, "rb") as w:
                    self.assertEqual((w.getframerate(), w.getsampwidth(), w.getnchannels()), (48000, 2, 1))
                    data = array.array("h")
                    data.frombytes(w.readframes(w.getnframes()))
                expected = make_ui_sounds.render(name)
                self.assertEqual(len(data), len(expected))
                # the same samples (one step of difference allowed for another PC's libm)
                self.assertLessEqual(max(abs(a - b) for a, b in zip(data, expected)), 1)

    def test_short_soft_and_clean(self):
        total = 0
        for name in make_ui_sounds.SOUNDS:
            samples = make_ui_sounds.render(name)
            ms = len(samples) / make_ui_sounds.RATE * 1000
            with self.subTest(sound=name):
                self.assertTrue(30 <= ms <= 150, ms)
                self.assertLessEqual(max(abs(s) for s in samples), int(0.55 * 32767))   # never loud
                self.assertEqual((samples[0], samples[-1]), (0, 0))                      # no click at the ends
                self.assertLess(abs(sum(samples) / len(samples)), 60)                    # no DC offset
            total += os.path.getsize(os.path.join(ui_sound.SOUND_DIR, name + ".wav"))
        self.assertEqual(set(make_ui_sounds.SOUNDS), set(ui_sound.NAMES))
        self.assertLess(total, 150_000)

    def test_generator_writes_a_folder(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder, mock.patch("builtins.print"):
            make_ui_sounds.main([folder])
            self.assertEqual(sorted(os.listdir(folder)), sorted(n + ".wav" for n in ui_sound.NAMES))
            self.assertEqual(set(ui_sound.load(folder)), set(ui_sound.NAMES))

    def test_release_zip_carries_the_sounds_and_modules(self):
        from tools import package_release
        for name in ui_sound.NAMES:
            self.assertIn("openrecomp/ui/sounds/" + name + ".wav", package_release.SOURCE_FILES)
        self.assertIn("openrecomp/ui_sound.py", package_release.SOURCE_FILES)
        self.assertIn("openrecomp/nav_sound.py", package_release.SOURCE_FILES)


class Volume(unittest.TestCase):
    def test_scaled_wav_follows_the_volume(self):
        rate, channels, samples = ui_sound.load()["confirm"]
        loud = ui_sound.scaled_wav(rate, channels, samples, 100)
        half = ui_sound.scaled_wav(rate, channels, samples, 50)
        import io
        with wave.open(io.BytesIO(loud)) as w:
            full = array.array("h", w.readframes(w.getnframes()))
        with wave.open(io.BytesIO(half)) as w:
            quarter = array.array("h", w.readframes(w.getnframes()))
        self.assertEqual(list(full), list(samples))
        self.assertEqual(max(map(abs, quarter)), int(max(map(abs, samples)) * 0.25))

    def test_saved_volume_is_cleaned(self):
        self.assertEqual(ui_sound.clean_volume(47), 50)
        self.assertEqual(ui_sound.clean_volume(1000), 100)
        self.assertEqual(ui_sound.clean_volume("loud"), ui_sound.DEFAULT_VOLUME)
        self.assertEqual(ui_sound.clean_volume(True), ui_sound.DEFAULT_VOLUME)
        self.assertEqual(ui_sound.clean_volume(None), ui_sound.DEFAULT_VOLUME)


class Gate(unittest.TestCase):
    def setUp(self):
        self.out, self.clock = Recorder(), Clock()
        self.sounds = ui_sound.UiSounds(output=self.out, clock=self.clock)

    def test_defaults_on_at_a_modest_volume(self):
        self.assertTrue(self.sounds.enabled)
        self.assertEqual(self.sounds.volume, 50)

    def test_off_inactive_and_unknown_play_nothing(self):
        self.assertFalse(self.sounds.play("confirm", active=False))
        self.assertFalse(self.sounds.play("boom"))
        self.sounds.configure(False, 50)
        self.assertFalse(self.sounds.play("confirm"))
        self.assertEqual(self.out.played, [])

    def test_a_held_direction_does_not_pile_up(self):
        for _ in range(30):                 # 30 repeats 10 ms apart = 300 ms
            self.sounds.play("move")
            self.clock.now += 0.010
        self.assertLessEqual(len(self.out.played), 8)
        self.assertGreaterEqual(len(self.out.played), 5)

    def test_other_sounds_are_not_held_back_by_a_move(self):
        self.sounds.play("move")
        self.assertTrue(self.sounds.play("confirm"))
        self.assertEqual(self.out.played, ["move", "confirm"])

    def test_volume_change_reaches_the_output_once(self):
        self.sounds.configure(True, 80)
        self.sounds.configure(True, 80)
        self.assertEqual(self.out.volumes, [80])

    def test_priority_keeps_the_sound_that_says_most(self):
        self.assertEqual(ui_sound.louder("move", "error"), "error")
        self.assertEqual(ui_sound.louder("open", "move"), "open")
        self.assertEqual(ui_sound.louder(None, "tab"), "tab")


class FakeWinMM:
    def __init__(self, device=True, fail=False):
        self.device, self.fail = device, fail
        self.calls = []
        self.done = threading.Event()

    def PlaySoundW(self, sound, module, flags):
        self.calls.append((sound is not None, flags))
        self.done.set()
        if self.fail:
            raise OSError("no audio service")
        return 1 if self.device or sound is None else 0


class WinMM(unittest.TestCase):
    def wait(self, fake, count):
        for _ in range(200):
            if len(fake.calls) >= count:
                return
            fake.done.wait(0.01)
            fake.done.clear()

    def test_plays_from_memory_without_waiting(self):
        fake = FakeWinMM()
        out = ui_sound.WinMMOutput(ui_sound.load(), 50, winmm=fake)
        out.play("confirm")
        self.wait(fake, 1)
        out.close()
        self.assertEqual(fake.calls[0], (True, 0x0001 | 0x0002 | 0x0004))   # SND_ASYNC | SND_NODEFAULT | SND_MEMORY

    def test_no_output_device_is_silent_and_harmless(self):
        fake = FakeWinMM(device=False)
        out = ui_sound.WinMMOutput(ui_sound.load(), 50, winmm=fake)
        out.play("confirm")
        self.wait(fake, 1)
        out.play("back")          # Windows said no: the worker goes on, never asks for the default sound
        self.wait(fake, 2)
        out.close()
        self.wait(fake, 3)
        self.assertTrue(all(flags & 0x0002 for sound, flags in fake.calls if sound))   # SND_NODEFAULT
        self.assertEqual(fake.calls[-1], (False, 0))

    def test_a_broken_audio_stack_never_stops_the_worker(self):
        fake = FakeWinMM(fail=True)
        out = ui_sound.WinMMOutput(ui_sound.load(), 50, winmm=fake)
        out.play("move")
        self.wait(fake, 1)
        fake.fail = False
        out.play("back")
        self.wait(fake, 2)
        out.close()
        self.assertGreaterEqual(len(fake.calls), 2)

    def test_volume_change_stops_and_rebuilds(self):
        fake = FakeWinMM()
        out = ui_sound.WinMMOutput(ui_sound.load(), 50, winmm=fake)
        out.play("tab")
        self.wait(fake, 1)
        out.set_volume(90)
        out.play("tab")
        self.wait(fake, 3)
        out.close()
        self.assertEqual(fake.calls[1], (False, 0))       # the old buffer is no longer read
        self.assertEqual(out._volume, 90)

    def test_no_windows_or_switched_off_is_silent(self):
        with mock.patch.object(ui_sound.os, "name", "posix"):
            self.assertIsInstance(ui_sound.make_output(ui_sound.load(), 50), ui_sound.NullOutput)
        with mock.patch.dict(os.environ, OPENRECOMP_UI_SOUND="0"):
            self.assertIsInstance(ui_sound.make_output(ui_sound.load(), 50), ui_sound.NullOutput)
        self.assertIsInstance(ui_sound.make_output({}, 50), ui_sound.NullOutput)


class Online(Fake):
    def __init__(self, m):
        super().__init__(m)
        self.phase, self.news = "logged_in", False

    def online_supported(self):
        return True

    def online_poll(self):
        news, self.news = self.news, False
        return news

    def online_state(self):
        return dict(phase=self.phase, message="@online.matched")


class Presses(unittest.TestCase):
    """Which sound each press makes; the mouse makes the pad's sound."""

    def setUp(self):
        self.a = Online(manifest("a"))
        self.b = Fake(manifest("b", sections=("play", "build", "settings")), is_ready=False)
        self.saved = []
        self.nav = Nav([Game(self.a.m, self.a), Game(self.b.m, self.b)], language="en",
                       on_ui_sound=lambda on, volume: self.saved.append((on, volume)))

    def sound(self, *actions):
        for action in actions:
            self.nav.act(action)
        self.nav.view()
        return self.nav.take_sound()

    def to_settings(self):
        self.sound("confirm")
        while self.nav.section() != "settings":
            self.sound("next")

    def test_shelf_and_hub(self):
        self.assertEqual(self.sound("right"), "move")
        self.assertEqual(self.sound("left"), "move")
        self.assertIsNone(self.sound("left"))                 # at the edge: nothing moved, no sound
        self.assertEqual(self.sound("confirm"), "confirm")    # into the game's hub
        self.assertEqual(self.sound("down"), "move")
        self.assertEqual(self.sound("next"), "tab")           # RB / E
        self.assertEqual(self.sound("prev"), "tab")
        self.assertEqual(self.sound("switchGame"), "tab")
        self.assertEqual(self.sound("back"), "back")          # to the shelf

    def test_overlays_open_and_close(self):
        self.assertEqual(self.sound("social"), "open")        # Quick access
        self.assertEqual(self.sound("down"), "move")
        self.assertEqual(self.sound("back"), "back")
        self.assertEqual(self.sound("social"), "open")
        self.assertEqual(self.sound("social"), "close")       # the same button closes it again
        self.assertEqual(self.sound("quit"), "open")          # the quit question
        self.assertEqual(self.sound("right"), "move")         # its other answer
        self.assertEqual(self.sound("back"), "back")

    def test_drawer_toggles_say_on_and_off(self):
        self.sound("social", "down")
        self.assertEqual(self.sound("right"), "toggle_off")   # fullscreen -> windowed
        self.assertEqual(self.sound("right"), "toggle_on")
        self.sound("up")
        self.assertEqual(self.sound("right"), "toggle_on")    # language: next one
        self.assertEqual(self.sound("left"), "toggle_off")

    def test_settings_audio_has_the_menu_sound_rows(self):
        self.to_settings()
        items = self.nav.items()
        ids = [it.get("id") for it in items]
        self.assertIn("ui_sounds", ids)
        self.assertIn("ui_sound_volume", ids)
        row = items[ids.index("ui_sounds")]
        self.assertEqual(row["settingsGroup"], "audio")
        self.nav.focus[self.nav.key()] = ids.index("ui_sounds")
        self.assertEqual(self.sound("left"), "toggle_off")
        self.assertEqual(self.saved[-1], (False, 50))
        self.assertEqual(self.sound("confirm"), "toggle_on")
        self.assertEqual(self.saved[-1], (True, 50))
        self.nav.focus[self.nav.key()] = ids.index("ui_sound_volume")
        self.assertEqual(self.sound("right"), "toggle_on")
        self.assertEqual(self.saved[-1], (True, 60))
        page = self.nav.view()["settingsPage"]
        self.assertIn("60 %", [line["value"] for line in page["lines"] if line["kind"] == "setting"])
        self.assertEqual([g["id"] for g in page["groups"]][0], "audio")

    def test_rows_are_offered_only_with_a_place_to_save(self):
        nav = Nav([Game(self.a.m, self.a)], language="en")
        nav.act("confirm")
        while nav.section() != "settings":
            nav.act("next")
        self.assertNotIn("ui_sounds", [it.get("id") for it in nav.items()])

    def test_refusals_and_failures_sound_as_errors(self):
        self.sound("confirm")
        self.a.is_running = True
        self.assertEqual(self.sound("play"), "error")         # game_already_running
        self.a.is_running = False
        self.nav.say("@library.busy")
        self.nav.tick(0.5)                                    # the toast is still up, a little older
        self.nav.take_sound()
        self.nav.library_busy = True
        self.assertEqual(self.sound("down"), "error")         # the same refusal said again
        self.nav.library_busy = False
        with mock.patch.object(self.nav, "_hub", side_effect=RuntimeError("broken core")):
            self.assertEqual(self.sound("confirm"), "error")

    def test_disabled_row_is_refused(self):
        self.sound("confirm")
        with mock.patch.object(self.nav, "items", return_value=[dict(kind="action", label="x", disabled=True,
                                                                     run=lambda: None)]):
            self.assertEqual(self.sound("confirm"), "error")

    def test_a_found_match_rings_once(self):
        self.a.phase, self.a.news = "matched", True
        self.nav.tick(0.016)
        self.assertEqual(self.nav.take_sound(), "notify")
        self.a.news = True                                    # connection notices keep arriving: no second ring
        self.nav.tick(0.016)
        self.assertIsNone(self.nav.take_sound())

    def test_a_finished_hold_confirms(self):
        self.sound("confirm")
        ran = []
        self.nav.holding = dict(kind="hold", run=lambda: ran.append(1))
        for _ in range(200):
            self.nav.tick(0.05)
            if ran:
                break
        self.assertEqual(ran, [1])
        self.assertEqual(self.nav.take_sound(), "confirm")

    def test_starting_a_hold_is_silent(self):
        self.sound("confirm")
        with mock.patch.object(self.nav, "items", return_value=[dict(kind="hold", label="x", run=lambda: None)]):
            self.assertIsNone(self.sound("confirm"))

    def test_on_screen_keyboard(self):
        self.sound("confirm")
        self.nav._open_osk("online_name")
        self.nav.take_sound()
        self.assertEqual(self.sound("right"), "move")
        self.assertEqual(self.sound("confirm"), "move")       # a key typed
        self.assertEqual(self.sound("x"), "back")             # a letter deleted
        self.assertEqual(self.sound("social"), "tab")         # the next page of keys
        self.assertEqual(self.sound("play"), "confirm")       # done: the keyboard closes with the text

    def test_mouse_makes_the_pads_sound(self):
        self.sound("confirm")
        pad = Nav([Game(self.a.m, self.a), Game(self.b.m, self.b)], language="en")
        pad.act("confirm")
        pad.take_sound()
        pad.act("next")
        click(self.nav, ui_sound.CLICK_TAB, "click_tab", "online")
        self.assertEqual((pad.take_sound(), self.nav.take_sound()), ("tab", "tab"))
        click(self.nav, "confirm", "click_tile", 0)           # (in the hub: nothing)
        self.nav.take_sound()
        self.nav.act("back")
        self.nav.take_sound()
        click(self.nav, "confirm", "click_tile", 1)           # the shelf's second tile: focus there
        self.assertIn(self.nav.take_sound(), ("move", "confirm"))

    def test_a_click_that_confirms_inside_counts_once(self):
        self.sound("quit")
        click(self.nav, "confirm", "click_entry", 0)          # "No" in the quit question
        self.assertEqual(self.nav.take_sound(), "confirm")
        self.assertIsNone(self.nav.take_sound())


class App(unittest.TestCase):
    """The app plays only while the player looks at the launcher."""

    def backend(self, active=True, minimized=False, running=False):
        nav = SimpleNamespace(games=[SimpleNamespace(a=SimpleNamespace(running=lambda: running))],
                              take_sound=lambda: "confirm")
        window = mock.Mock()
        window.isActive.return_value = active
        window.windowState.return_value = Qt.WindowMinimized if minimized else Qt.WindowNoState
        out = Recorder()
        return SimpleNamespace(nav=nav, window=window, sounds=ui_sound.UiSounds(output=out)), out

    def test_plays_in_front(self):
        backend, out = self.backend()
        Backend._play_sound(backend)
        self.assertEqual(out.played, ["confirm"])

    def test_silent_unfocused_minimized_or_while_a_game_runs(self):
        for kwargs in (dict(active=False), dict(minimized=True), dict(running=True)):
            with self.subTest(**kwargs):
                backend, out = self.backend(**kwargs)
                Backend._play_sound(backend)
                self.assertEqual(out.played, [])

    def test_setting_is_saved_and_applied(self):
        out = Recorder()
        backend = SimpleNamespace(config={}, sounds=ui_sound.UiSounds(output=out), nav=None,
                                  _save_config=mock.Mock())
        Backend._save_ui_sound(backend, False, 70)
        self.assertEqual(backend.config, dict(ui_sounds=False, ui_sound_volume=70))
        self.assertFalse(backend.sounds.enabled)
        self.assertEqual(out.volumes, [70])
        backend._save_config.assert_called_once()

    def test_offscreen_has_no_real_output(self):
        from openrecomp import app
        with mock.patch.object(app.QGuiApplication, "instance", return_value=object()), \
                mock.patch.object(app.QGuiApplication, "platformName", return_value="offscreen"):
            self.assertFalse(app.real_audio())
        with mock.patch.dict(os.environ, OPENRECOMP_UI_SOUND="0"):
            self.assertFalse(app.real_audio())


if __name__ == "__main__":
    unittest.main()
