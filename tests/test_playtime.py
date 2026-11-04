"""Play time uses fake clocks, inert process handles and repository-local homes."""
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp import playtime
from openrecomp.adapters.base import Adapter, Generic

ROOT = Path(__file__).resolve().parents[1]


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class Child:
    def __init__(self, pid, clock, born=0, online=False):
        self.pid, self.clock, self.born = pid, clock, born
        self.end = None
        self.mode = online
        self.closed = False

    def running(self):
        return self.end is None

    def poll(self):
        return None if self.running() else 0

    def interval(self):
        return self.born, self.end

    def elapsed(self):
        return (self.clock() if self.end is None else self.end) - self.born

    def online(self):
        return self.mode

    def close(self):
        self.closed = True


class PlaytimeTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.folder.cleanup)
        self.clock = Clock()
        self.store = self.new_store()
        self.enterContext(mock.patch.object(playtime.Process, "open", return_value=None))

    def new_store(self):
        return playtime.Store(self.folder.name, self.clock, wall=lambda: 1793790000, background=False)

    def watch(self, game="t5dr", online=False, born=0):
        child = Child(len(self.store.active) + 10, self.clock, born, online)
        self.store.watch(game, child.running, online, process=child, elapsed=child.elapsed)
        return child

    def persisted(self):
        return json.loads(Path(self.store.path).read_text(encoding="utf-8"))

    def test_no_file_migrates_to_zero_without_writing_on_view(self):
        self.assertEqual(self.store.snapshot("t5dr"), playtime.empty())
        self.assertFalse(Path(self.store.path).exists())
        adapter = Adapter(dict(id="t5dr"))
        adapter.playtime_store = self.store
        self.assertEqual(adapter.playtime(), playtime.empty())
        self.assertFalse(Path(self.store.path).exists())

    def test_successful_launch_saves_session_and_local_date_immediately(self):
        self.watch()
        row = self.persisted()["games"]["t5dr"]
        self.assertEqual(row["sessions"], 1)
        self.assertEqual(row["last_played"], "2026-11-04")
        self.assertEqual(row["offline_seconds"], 0)
        self.assertEqual(set(row), set(playtime.empty()))

    def test_checkpoint_at_sixty_seconds_then_exact_exit_not_poll_time(self):
        child = self.watch()
        self.clock.advance(59)
        self.store.tick()
        self.assertEqual(self.persisted()["games"]["t5dr"]["offline_seconds"], 0)
        self.clock.advance(1)
        self.store.tick()
        self.assertEqual(self.persisted()["games"]["t5dr"]["offline_seconds"], 60)
        self.clock.advance(17.25)
        child.end = self.clock()
        self.clock.advance(8)
        self.store.tick()
        self.assertEqual(self.persisted()["games"]["t5dr"]["offline_seconds"], 77.25)
        self.assertEqual(self.store.active, {})

    def test_crash_retains_checkpoint_and_never_counts_launcher_downtime(self):
        self.watch()
        self.clock.advance(60)
        self.store.tick()
        self.clock.advance(24 * 60 * 60)
        restarted = self.new_store()
        self.assertEqual(restarted.snapshot("t5dr")["offline_seconds"], 60)
        self.assertEqual(restarted.snapshot("t5dr")["sessions"], 1)
        self.assertFalse(restarted.active)
        child = Child(21, self.clock, self.clock())
        restarted.watch("t5dr", child.running, process=child, elapsed=child.elapsed)
        self.clock.advance(10)
        child.end = self.clock()
        restarted.tick()
        self.assertEqual(restarted.snapshot("t5dr")["offline_seconds"], 70)
        self.assertEqual(restarted.snapshot("t5dr")["sessions"], 2)

    def test_two_games_at_once_keep_independent_modes_and_exits(self):
        first = self.watch("t5dr")
        self.clock.advance(30)
        second = self.watch("t4", online=True, born=30)
        self.clock.advance(60)
        first.end = 90
        self.store.tick()
        self.clock.advance(30)
        second.end = 120
        self.store.tick()
        self.assertEqual(self.store.snapshot("t5dr")["offline_seconds"], 90)
        self.assertEqual(self.store.snapshot("t5dr")["online_seconds"], 0)
        self.assertEqual(self.store.snapshot("t4")["online_seconds"], 90)
        self.assertEqual(self.store.snapshot("t4")["offline_seconds"], 0)

    def test_same_game_offline_and_online_sessions_accumulate_separately(self):
        child = self.watch()
        self.clock.advance(180)
        child.end = self.clock()
        self.store.tick()
        other = self.watch(online=True, born=180)
        self.clock.advance(120)
        other.end = self.clock()
        self.store.tick()
        row = self.new_store().snapshot("t5dr")
        self.assertEqual((row["offline_seconds"], row["online_seconds"], row["sessions"]), (180, 120, 2))

    def test_repeated_launch_hook_does_not_add_session_or_reset_clock(self):
        child = self.watch()
        self.clock.advance(60)
        self.store.watch("t5dr", child.running, process=child, elapsed=child.elapsed)
        self.assertEqual(self.store.snapshot("t5dr")["sessions"], 1)
        self.assertEqual(self.store.snapshot("t5dr")["offline_seconds"], 60)

    def test_view_reads_live_time_without_changing_persisted_total(self):
        self.watch()
        self.clock.advance(25)
        self.assertEqual(self.store.snapshot("t5dr")["offline_seconds"], 25)
        self.assertEqual(self.persisted()["games"]["t5dr"]["offline_seconds"], 0)

    def test_atomic_replace_failure_keeps_previous_file_and_retries_without_double_count(self):
        child = self.watch()
        previous = Path(self.store.path).read_bytes()
        self.clock.advance(60)
        with mock.patch("openrecomp.playtime.os.replace", side_effect=OSError("inert disk error")):
            self.store.tick()
        self.assertEqual(Path(self.store.path).read_bytes(), previous)
        self.assertEqual(list(Path(self.folder.name).glob(".playtime-*.tmp")), [])
        self.clock.advance(10)
        self.store.tick()
        self.assertEqual(self.persisted()["games"]["t5dr"]["offline_seconds"], 70)
        child.end = 70
        self.store.tick()
        self.assertEqual(self.store.snapshot("t5dr")["offline_seconds"], 70)

    def test_checkpoint_during_quit_does_not_finish_live_session(self):
        self.watch()
        self.clock.advance(31)
        self.store.checkpoint()
        self.assertEqual(self.persisted()["games"]["t5dr"]["offline_seconds"], 31)
        self.assertEqual(len(self.store.active), 1)

    def test_corrupt_or_invalid_saved_rows_do_not_crash_or_inject_values(self):
        Path(self.store.path).write_text(json.dumps(dict(version=1, games={
            "t5dr": dict(offline_seconds=-1, online_seconds=float("inf"), sessions=True, last_played="bogus"),
            "../../outside": dict(sessions=99), "t4": "bad"})), encoding="utf-8")
        restored = self.new_store()
        self.assertEqual(restored.snapshot("t5dr"), playtime.empty())
        self.assertEqual(set(restored.games), {"t5dr"})
        Path(self.store.path).write_text("[", encoding="utf-8")
        self.assertEqual(self.new_store().snapshot("t5dr"), playtime.empty())

    def test_network_switches_classify_online_without_diagnostics_false_positive(self):
        self.assertTrue(playtime.online_environment(dict(T5_NET_MATCH="match")))
        self.assertTrue(playtime.online_environment(dict(TEKKEN4_NET="1")))
        self.assertFalse(playtime.online_environment(dict(TEKKEN4_NET="0", T5_NET_LINE="1", T5_RB_NET_FEEL="balanced")))
        self.assertFalse(playtime.online_environment(dict(TEKKEN4_NET="off")))

    def test_large_saved_numeric_values_are_ignored_without_preventing_startup(self):
        Path(self.store.path).write_text(json.dumps(dict(version=1, games=dict(
            t5dr=dict(offline_seconds=10 ** 1000, online_seconds=42)))), encoding="utf-8")
        row = self.new_store().snapshot("t5dr")
        self.assertEqual(row["offline_seconds"], 0)
        self.assertEqual(row["online_seconds"], 42)

    def test_tracking_worker_failure_never_fails_a_successful_game_launch(self):
        adapter = Generic(dict(id="tag2", online=dict(mode="own")))
        adapter.playtime_store = self.store
        self.store.background = True
        child = Child(71, self.clock)
        with mock.patch.object(adapter, "ready", return_value=True), mock.patch.object(adapter, "exe", return_value="game.exe"), mock.patch("subprocess.Popen", return_value=child), mock.patch("openrecomp.playtime.threading.Thread.start", side_effect=RuntimeError("inert worker failure")):
            self.assertEqual(adapter.start(), 71)
        self.assertEqual(adapter.playtime()["sessions"], 1)

    def test_adapter_launch_hook_uses_mode_and_never_exports_to_online_state(self):
        adapter = Adapter(dict(id="t4"))
        adapter.playtime_store = self.store
        child = Child(91, self.clock)
        adapter._track_playtime(child.running, extra_env=dict(TEKKEN4_NET="1"))
        self.clock.advance(45)
        self.assertEqual(adapter.playtime()["online_seconds"], 45)
        self.assertNotIn("playtime", adapter.online_state())

    def test_generic_online_action_counts_online_without_injecting_environment_flag(self):
        adapter = Generic(dict(id="tag2", online=dict(mode="own")))
        adapter.playtime_store = self.store
        child = Child(71, self.clock)
        with mock.patch.object(adapter, "ready", return_value=True), mock.patch.object(adapter, "exe", return_value="game.exe"), mock.patch("subprocess.Popen", return_value=child) as popen:
            adapter.run_online("own")
        self.clock.advance(30)
        self.assertEqual(adapter.playtime()["online_seconds"], 30)
        self.assertEqual(adapter.playtime()["offline_seconds"], 0)
        self.assertNotIn("OPENRECOMP_PLAYTIME", popen.call_args.kwargs["env"])
        self.assertFalse(adapter._playtime_online_launch)

    def test_failed_generic_launch_does_not_create_session(self):
        adapter = Generic(dict(id="tag2", exe="missing-game.exe", online=dict(mode="own")))
        adapter.playtime_store = self.store
        with self.assertRaises(RuntimeError):
            adapter.run_online("own")
        self.assertEqual(adapter.playtime(), playtime.empty())
        self.assertFalse(adapter._playtime_online_launch)

    def test_native_launcher_idle_is_not_playtime_and_unrelated_games_are_ignored(self):
        launcher = Child(100, self.clock)
        owned = Child(101, self.clock, born=10, online=True)
        unrelated = Child(201, self.clock, born=10)
        rows = [(100, 1, "native.exe"), (101, 100, "T5DR.EXE"), (201, 200, "t5dr.exe")]
        handles = {100: launcher, 101: owned, 201: unrelated}
        self.store.watch_native("t5dr", launcher, ("t5dr.exe",), scan=lambda: rows,
                                open_process=handles.get)
        self.clock.advance(10)
        self.store.tick()
        self.clock.advance(120)
        owned.end = 130
        self.store.tick()
        self.assertEqual(self.store.snapshot("t5dr")["online_seconds"], 120)
        self.assertEqual(self.store.snapshot("t5dr")["sessions"], 1)
        self.clock.advance(100)
        self.store.tick()
        self.assertEqual(self.store.snapshot("t5dr")["online_seconds"], 120)
        self.assertFalse(unrelated.closed)

    def test_native_intermediary_launcher_exit_keeps_game_owned_and_exact_exit_time(self):
        launcher = Child(100, self.clock)
        middle = Child(101, self.clock, born=1)
        child = Child(102, self.clock, born=2)
        handles = {100: launcher, 101: middle, 102: child}
        rows = [(100, 1, "native.exe"), (101, 100, "helper.exe"), (102, 101, "game.exe")]
        self.store.watch_native("t4", launcher, ("game.exe",), scan=lambda: rows, open_process=handles.get)
        self.clock.advance(5)
        launcher.end = 3
        middle.end = 4
        self.store.tick()
        self.assertEqual(self.store.snapshot("t4")["offline_seconds"], 3)
        rows[:] = [(102, 101, "game.exe")]
        self.clock.advance(100)
        child.end = 104
        self.store.tick()
        self.assertEqual(self.store.snapshot("t4")["offline_seconds"], 102)
        self.assertTrue(child.closed)
        self.assertFalse(self.store.native)

    def test_recycled_native_launcher_pid_cannot_claim_unrelated_game(self):
        launcher = Child(100, self.clock)
        child = Child(102, self.clock, born=20)
        handles = {100: launcher, 102: child}
        launcher.end = 5
        rows = [(100, 1, "other.exe"), (102, 100, "game.exe")]
        self.store.watch_native("t4", launcher, ("game.exe",), scan=lambda: rows, open_process=handles.get)
        self.clock.advance(25)
        self.store.tick()
        self.assertEqual(self.store.snapshot("t4"), playtime.empty())
        self.assertTrue(child.closed)

    def test_t5_successful_start_passes_owned_process_and_network_mode(self):
        from openrecomp.adapters.t5dr import T5DR
        child = Child(73, self.clock)
        game = SimpleNamespace(proc=child, running=child.running, start=mock.Mock(return_value=73), stop=mock.Mock())
        adapter = T5DR.__new__(T5DR)
        adapter.m = dict(id="t5dr")
        adapter.playtime_store = self.store
        adapter.ready = lambda: True
        adapter.game = None
        adapter.s = SimpleNamespace(out_dir="fake")
        adapter.core = SimpleNamespace(GameRun=mock.Mock(return_value=game))
        with mock.patch("openrecomp.adapters.t5dr.LaunchGuard"), mock.patch("openrecomp.adapters.t5dr.game_process_running", return_value=False):
            self.assertEqual(adapter.start(extra_env=dict(T5_NET_MATCH="match")), 73)
        self.clock.advance(20)
        self.assertEqual(adapter.playtime()["online_seconds"], 20)
        child.end = 20
        self.store.tick()
        self.assertEqual(adapter.playtime()["sessions"], 1)

    def test_t4_successful_runtime_start_tracks_online_and_restores_environment(self):
        from openrecomp.adapters.t4 import T4
        child = Child(74, self.clock)
        run = SimpleNamespace(proc=child, start=mock.Mock())
        adapter = T4.__new__(T4)
        adapter.m = dict(id="t4")
        adapter.playtime_store = self.store
        adapter.problems = lambda: []
        adapter._graphics_values = lambda: {}
        adapter.s = {}
        environment = mock.Mock(return_value={})
        adapter.core = SimpleNamespace(GameRun=mock.Mock(return_value=run), game_env=environment,
                                       run_lock_holder=lambda: None, take_run_lock=mock.Mock())
        with mock.patch("openrecomp.adapters.t4.threading.Thread"):
            self.assertEqual(adapter._start(dict(TEKKEN4_NET="1")), 74)
        self.assertIs(adapter.core.game_env, environment)
        self.clock.advance(40)
        self.assertEqual(adapter.playtime()["online_seconds"], 40)

    def test_manifest_v2_external_online_action_tracks_future_games(self):
        from openrecomp.adapters.manifest_game import ManifestGame
        child = Child(75, self.clock)
        adapter = ManifestGame.__new__(ManifestGame)
        adapter.m = dict(id="tag2", online=dict(mode="external"))
        adapter.playtime_store = self.store
        adapter.proc = None
        adapter.lock = threading.Lock()
        adapter.ready = lambda: True
        adapter._command = lambda env: (["game.exe"], "", {})
        adapter.popen = mock.Mock(return_value=child)
        adapter.run_online("own")
        self.clock.advance(50)
        self.assertEqual(adapter.playtime()["online_seconds"], 50)
        self.assertFalse(adapter._playtime_online_launch)

    def test_native_adapter_hooks_observe_only_launcher_started_here(self):
        from openrecomp.adapters.t4 import T4
        from openrecomp.adapters.t5dr import T5DR
        launcher = Child(76, self.clock)
        t5 = T5DR.__new__(T5DR)
        t5.m = dict(id="t5dr")
        t5.playtime_store = mock.Mock()
        t5._exe_launcher = mock.Mock(return_value=launcher)
        t5.open_native()
        t5.playtime_store.watch_native.assert_called_once_with("t5dr", launcher, ("t5dr.exe",))
        t4 = T4.__new__(T4)
        t4.m = dict(id="t4")
        t4.playtime_store = mock.Mock()
        t4.root = "fake-root"
        t4.s = {}
        t4.core = SimpleNamespace(find_python=lambda: "python.exe", NO_WINDOW=0,
                                 subprocess=SimpleNamespace(Popen=mock.Mock(return_value=launcher)),
                                 find_runtime=lambda settings: ("game.exe", ""))
        t4.open_native()
        t4.playtime_store.watch_native.assert_called_once_with("t4", launcher, ("game.exe",))

    def test_starting_second_game_checkpoints_first_without_postponing_its_save(self):
        self.watch()
        self.clock.advance(59)
        self.watch("t4", born=59)
        self.assertEqual(self.persisted()["games"]["t5dr"]["offline_seconds"], 59)

    def test_background_worker_can_be_restarted_after_becoming_idle(self):
        # The idle transition clears its reference while holding the store lock.
        self.store._thread = object()
        self.store._wake = mock.Mock()
        self.store._run()
        self.assertIsNone(self.store._thread)


if __name__ == "__main__":
    unittest.main()
