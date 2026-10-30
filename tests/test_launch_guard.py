"""Same-game exclusion with repository-local lock files and fake game state only."""
import errno
import os
import tempfile
import threading
import unittest
from unittest import mock

from openrecomp.adapters.launch_guard import LaunchGuard


class LaunchGuardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.directory.cleanup)

    def guard(self, game="t5dr"):
        guard = LaunchGuard(game, self.directory.name)
        self.addCleanup(guard.release)
        return guard

    def test_second_launcher_is_refused_until_owner_releases(self):
        owner, other = self.guard(), self.guard()
        owner.acquire()
        with self.assertRaisesRegex(RuntimeError, "@online.game_running"):
            other.acquire()
        owner.release()
        other.acquire()

    def test_games_have_separate_reservations(self):
        self.guard("t5dr").acquire()
        self.guard("t4").acquire()

    def test_stale_file_contents_and_pid_have_no_authority(self):
        with open(os.path.join(self.directory.name, "t5dr.lock"), "wb") as stream:
            stream.write(b"old owner 123")
        self.guard().acquire()

    def test_same_object_cannot_acquire_twice(self):
        guard = self.guard().acquire()
        with self.assertRaisesRegex(RuntimeError, "@online.game_running"):
            guard.acquire()

    def test_child_stopping_keeps_lock_until_confirmed_exit(self):
        owner, other = self.guard().acquire(), self.guard()
        exited = threading.Event()
        worker = owner.watch(lambda: not exited.is_set())
        with self.assertRaisesRegex(RuntimeError, "@online.game_running"):
            other.acquire()
        exited.set()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        other.acquire()

    def test_unknown_child_state_keeps_reservation(self):
        owner, other = self.guard().acquire(), self.guard()
        worker = owner.watch(mock.Mock(side_effect=OSError("fake check failed")))
        worker.join(2)
        with self.assertRaisesRegex(RuntimeError, "@online.game_running"):
            other.acquire()

    def test_old_monitor_does_not_release_a_new_reservation(self):
        guard = self.guard().acquire()
        previous = guard._stream
        guard.release()
        guard.acquire()
        guard.release(expected=previous)
        with self.assertRaisesRegex(RuntimeError, "@online.game_running"):
            self.guard().acquire()

    def test_unavailable_lock_fails_closed(self):
        with mock.patch("openrecomp.adapters.launch_guard._lock_file", side_effect=OSError(errno.EIO, "fake")):
            with self.assertRaisesRegex(RuntimeError, "@online.process_unknown"):
                self.guard().acquire()

    def test_game_id_cannot_escape_lock_directory(self):
        with self.assertRaises(ValueError):
            LaunchGuard("../elsewhere", self.directory.name)


if __name__ == "__main__":
    unittest.main()
