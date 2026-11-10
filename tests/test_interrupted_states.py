"""A step that was cut off (launcher or helper killed, PC switched off) never blocks the next start.

Every test here starts a real second Python process, lets it get half-way through the step and kills it. Then the
same step is started again the way the launcher would: nothing may stay locked, nothing may be lost, and work
folders of the dead process are cleaned up. "Busy" is only believed while the process that said so is alive."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from openrecomp import game_releases as gr
from openrecomp import game_setup as gs
from openrecomp import updater as u
from openrecomp.adapters import t5_buildlock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import release_fixtures as rf  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CHANNEL = u.Channel("example/OpenRecomp", "12345", "audit-channel", ("01" * 32,))
TEST_KEY = rf.public_key().hex()

CHILD_HEAD = """
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, {tests!r})
def ready():
    Path({ready!r}).write_text(str(os.getpid()), encoding="utf-8")
def hang():
    ready()
    time.sleep(600)
"""


class Killed(unittest.TestCase):
    """Starts a child from Python source, waits until it says it is half-way, and kills it."""

    def setUp(self):
        self.temp = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="openrecomp-cut-")))
        self.ready = self.temp / "child-ready"
        self.children = []
        self.addCleanup(self.stop_children)

    def stop_children(self):
        for child in self.children:
            if child.poll() is None or not child.stdout.closed:
                child.real_pid = getattr(child, "real_pid", child.pid)
                self.kill(child)

    def child(self, body, env=None):
        self.ready.unlink(missing_ok=True)
        source = CHILD_HEAD.format(tests=str(ROOT / "tests"), ready=str(self.ready)) + body
        environment = dict(os.environ, PYTHONPATH=str(ROOT), OPENRECOMP_TESTING="1", **(env or {}))
        process = subprocess.Popen([sys.executable, "-B", "-c", source], cwd=ROOT, env=environment,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.children.append(process)
        deadline = time.monotonic() + 60
        while not self.ready.exists():
            if process.poll() is not None:
                self.fail("the child ended early:\n" + process.stdout.read().decode("utf-8", "replace"))
            if time.monotonic() >= deadline:
                self.fail("the child never got half-way")
            time.sleep(0.02)
        while True:
            try:
                process.real_pid = int(self.ready.read_text(encoding="utf-8"))
                return process
            except (OSError, ValueError):
                time.sleep(0.02)

    def kill(self, process):
        """Kill it the hard way. A venv's python.exe only starts the real one: that one must be gone too."""
        process.kill()
        process.wait(10)
        process.stdout.close()
        if process.real_pid != process.pid and u._pid_alive(process.real_pid):
            try:
                os.kill(process.real_pid, 9)
            except OSError:
                pass
        deadline = time.monotonic() + 10
        while u._pid_alive(process.real_pid) and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertFalse(u._pid_alive(process.real_pid))


# ------------------------------------------------------------------------------------------- the launcher's own update
HELPER = """
from unittest import mock
from openrecomp import updater as u
channel = u.Channel("example/OpenRecomp", "12345", "audit-channel", ("01" * 32,))
moved = []
def move(source, target):
    if len(moved) == {moves}:
        hang()
    os.replace(source, target)
    moved.append(str(target))
def alive(pid):
    if {wait_for_launcher}:
        ready()
    return {wait_for_launcher}
with mock.patch.object(u, "configured_channel", return_value=channel), mock.patch.object(u, "_verify_staged"):
    u.apply_plan({plan!r}, wait=600, alive=alive, processes=lambda root: [], restart=lambda *a, **k: hang(), move=move)
"""


class SelfUpdateHelperKilled(Killed):
    def setUp(self):
        super().setUp()
        self.root = self.temp / "OpenRecomp-FGC"
        self.program(self.root, "v1.0.0")
        self.enterContext(mock.patch.object(u, "configured_channel", return_value=CHANNEL))
        self.enterContext(mock.patch.object(u, "_verify_staged"))
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_HOME=str(self.temp / "player-data")))
        self.lock = u._work_root(self.root) / "apply.lock"

    def program(self, folder, version):
        for item in u.REQUIRED_ITEMS:
            path = folder / item
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture " + version, encoding="utf-8")
        (folder / "release.json").write_text(json.dumps(dict(project=u.PROJECT, channel=CHANNEL.name, version=version)),
                                             encoding="utf-8")

    def plan(self, name, version):
        staged = u._work_root(self.root) / name / "new"
        self.program(staged, version)
        path = staged.parent / "plan.json"
        path.write_text(json.dumps(dict(root=str(self.root), staged=str(staged), version=version, channel=CHANNEL.name,
                                        pid=123, token="a" * 64)), encoding="utf-8")
        return path

    def apply(self, plan):
        def restart(root, marker=None):
            if marker:
                Path(marker["path"]).write_text(json.dumps(dict(token=marker["token"])), encoding="utf-8")
            return mock.Mock(poll=lambda: None)
        return u.apply_plan(plan, wait=5, alive=lambda pid: False, processes=lambda root: [], restart=restart)

    def helper(self, plan, moves=-1, wait_for_launcher=False):
        return self.child(HELPER.format(plan=str(plan), moves=moves, wait_for_launcher=wait_for_launcher))

    def test_helper_killed_while_it_waits_for_the_launcher_does_not_block_updates_for_ever(self):
        process = self.helper(self.plan("aa" * 12, "v1.2.3"), wait_for_launcher=True)
        self.assertTrue(self.lock.is_dir())
        self.assertFalse(u._lock_stale(self.lock))                 # its helper lives: the lock counts
        self.assertFalse(u.release_stale_lock(self.root))
        with self.assertRaises(u.UpdateError):
            self.apply(self.plan("bb" * 12, "v1.2.4"))
        self.assertEqual(u.local_version(self.root), "v1.0.0")
        self.kill(process)
        self.assertTrue(self.lock.is_dir())                        # exactly what a switched-off PC leaves
        self.assertTrue(u.release_stale_lock(self.root))           # the launcher's next start
        self.assertFalse(self.lock.exists())
        self.assertTrue(self.apply(self.plan("cc" * 12, "v1.2.5")))
        self.assertEqual(u.local_version(self.root), "v1.2.5")
        self.assertFalse(self.lock.exists())

    def test_helper_killed_in_the_middle_of_the_exchange_is_put_back_by_the_next_update(self):
        first = self.plan("aa" * 12, "v1.2.3")
        process = self.helper(first, moves=len([i for i in u.PROGRAM_ITEMS if (self.root / i).exists()]) + 1)
        self.kill(process)
        # The old program waits in the backup, one new item is in: neither version is whole.
        self.assertTrue((first.parent / "backup" / "release.json").is_file())
        self.assertFalse((self.root / "release.json").exists())
        self.assertTrue(self.lock.is_dir())
        self.assertFalse(u.release_stale_lock(self.root))          # a running launcher cannot put its own files back
        self.assertTrue(self.lock.is_dir())
        self.assertTrue(self.apply(self.plan("bb" * 12, "v1.2.4")))
        self.assertEqual(u.local_version(self.root), "v1.2.4")
        for item in u.REQUIRED_ITEMS:
            self.assertTrue((self.root / item).is_file(), item)
        self.assertFalse(self.lock.exists())
        self.assertEqual(json.loads((first.parent / "consumed.json").read_text(encoding="utf-8"))["status"], "rolled_back")
        self.assertEqual(u.local_version(u._work_root(self.root) / ("bb" * 12) / "backup"), "v1.0.0")

    def test_helper_killed_after_the_whole_exchange_keeps_the_new_version(self):
        first = self.plan("aa" * 12, "v1.2.3")
        process = self.helper(first)                                # it dies waiting for the new launcher's "I started"
        self.kill(process)
        self.assertEqual(u.local_version(self.root), "v1.2.3")
        self.assertTrue(self.apply(self.plan("bb" * 12, "v1.2.4")))
        self.assertEqual(u.local_version(self.root), "v1.2.4")
        self.assertEqual(json.loads((first.parent / "consumed.json").read_text(encoding="utf-8"))["status"], "updated")
        self.assertFalse(self.lock.exists())

    def test_a_pid_that_now_belongs_to_another_program_does_not_hold_the_lock(self):
        other = self.child("hang()\n")
        self.lock.mkdir(parents=True)
        (self.lock / u.LOCK_OWNER).write_text(json.dumps(dict(pid=other.real_pid, started=1)), encoding="utf-8")
        if os.name == "nt":
            self.assertTrue(u._lock_stale(self.lock))
            (self.lock / u.LOCK_OWNER).write_text(json.dumps(dict(pid=other.real_pid, started=u.pid_started(other.real_pid))),
                                                  encoding="utf-8")
        self.assertFalse(u._lock_stale(self.lock))
        self.kill(other)
        self.assertTrue(u._lock_stale(self.lock))

    def test_a_lock_of_an_older_helper_without_owner_record_ends_after_a_while(self):
        self.lock.mkdir(parents=True)
        self.assertFalse(u._lock_stale(self.lock))
        self.assertFalse(u.release_stale_lock(self.root))
        self.assertTrue(u._lock_stale(self.lock, now=time.time() + u.STALE_LOCK_AFTER + 1))
        self.assertTrue(u.release_stale_lock(self.root, now=time.time() + u.STALE_LOCK_AFTER + 1))
        self.assertFalse(self.lock.exists())


# ------------------------------------------------------------------------------------------- T5DR build
BUILD = """
from openrecomp.adapters import t5_buildlock
t5_buildlock._processes = lambda: []
t5_buildlock.acquire({root!r}, {out!r})
hang()
"""


class BuildKilled(Killed):
    def setUp(self):
        super().setUp()
        self.root = self.temp / "T5DR-Online-1.2.2"
        self.out = self.root / "native"
        self.out.mkdir(parents=True)
        self.enterContext(mock.patch.object(t5_buildlock, "_processes", lambda: []))    # no build process anywhere

    def test_launcher_killed_during_its_build_leaves_nothing_locked(self):
        process = self.child(BUILD.format(root=str(self.root), out=str(self.out)))
        self.assertEqual(t5_buildlock.blocker(str(self.root), str(self.out)), "@t5.build_locked_openrecomp")
        with self.assertRaises(RuntimeError):
            t5_buildlock.acquire(str(self.root), str(self.out))
        self.kill(process)
        self.assertTrue(os.path.isfile(t5_buildlock.lock_path(str(self.root))))         # the dead launcher's lock
        (self.out / "build.log").write_text("[3/9] lift\ncompiling ...\n", encoding="utf-8")   # cut off: no exit line
        self.assertEqual(t5_buildlock.blocker(str(self.root), str(self.out)), "")
        t5_buildlock.acquire(str(self.root), str(self.out))
        self.addCleanup(t5_buildlock.release, str(self.root))
        self.assertEqual(json.loads(Path(t5_buildlock.lock_path(str(self.root))).read_text(encoding="utf-8"))["pid"], os.getpid())

    def test_a_lock_whose_pid_now_belongs_to_another_program_does_not_block(self):
        other = self.child("hang()\n")
        lock = Path(t5_buildlock.lock_path(str(self.root)))
        lock.write_text(json.dumps(dict(pid=other.real_pid, started_at=1, by="OpenRecomp-FGC")), encoding="utf-8")
        if os.name == "nt":
            self.assertEqual(t5_buildlock.blocker(str(self.root), str(self.out)), "")
            lock.write_text(json.dumps(dict(pid=other.real_pid, started_at=u.pid_started(other.real_pid))), encoding="utf-8")
        self.assertEqual(t5_buildlock.blocker(str(self.root), str(self.out)), "@t5.build_locked_openrecomp")
        lock.write_text(json.dumps(dict(pid=other.real_pid)), encoding="utf-8")              # a 0.1.7 lock: believed while alive
        self.assertEqual(t5_buildlock.blocker(str(self.root), str(self.out)), "@t5.build_locked_openrecomp")
        self.kill(other)
        self.assertEqual(t5_buildlock.blocker(str(self.root), str(self.out)), "")


# ------------------------------------------------------------------------------------------- game install / update
GAME = """
import release_fixtures as rf
from openrecomp import game_releases as gr
gh = rf.FakeGitHub()
gh.__enter__()
for version in {versions!r}:
    gh.add_t5dr(version)
os.environ[gr.TEST_ENV] = gh.base
os.environ[gr.TEST_KEY_ENV] = {key!r}
offer = gr.latest(gr.SOURCES["t5dr"], "stable")
"""
INSTALL = GAME + """
real = gr.unpack
def unpack(src, zip_path, dest, offer, **kwargs):
    folder = real(src, zip_path, dest, offer, **kwargs)
    hang()                                    # downloaded, checked and unpacked: killed before the folder is in place
gr.unpack = unpack
gr.install_fresh("t5dr", offer, {parent!r})
"""
UPDATE = GAME + """
real, count = gr._move, []
def move(a, b, timeout=20.0):
    if os.path.dirname(b) == os.path.abspath({root!r}):
        count.append(b)
        if len(count) == 2:
            hang()                            # the old files are out, one new item is in
    return real(a, b, timeout)
gr._move = move
gr.update_in_place("t5dr", offer, {root!r})
"""


class GameStepKilled(Killed):
    def setUp(self):
        super().setUp()
        self.gh = rf.FakeGitHub()
        self.gh.__enter__()
        self.addCleanup(self.gh.__exit__)
        self.enterContext(mock.patch.dict(os.environ, {gr.TEST_ENV: self.gh.base, gr.TEST_KEY_ENV: TEST_KEY,
                                                       "OPENRECOMP_HOME": str(self.temp / "home")}))
        self.games = self.temp / "games"
        self.games.mkdir()

    def offer(self):
        return gr.latest(gr.SOURCES["t5dr"], "stable")

    def test_launcher_killed_during_an_install_can_install_again_and_leaves_no_work_folder(self):
        self.gh.add_t5dr("1.2.0")
        process = self.child(INSTALL.format(versions=["1.2.0"], key=TEST_KEY, parent=str(self.games)))
        self.kill(process)
        left = [p.name for p in self.games.iterdir()]
        self.assertEqual(len([n for n in left if n.startswith(".openrecomp-setup-t5dr-")]), 1, left)
        self.assertFalse((self.games / "T5DR-Online-1.2.0").exists())
        self.assertEqual(gr.check_target(gr.SOURCES["t5dr"], self.offer(), str(self.games)), "")
        root = gr.install_fresh("t5dr", self.offer(), str(self.games))
        self.assertEqual(gr.installed_version("t5dr", root), "1.2.0")
        self.assertEqual(sorted(p.name for p in self.games.iterdir()), ["T5DR-Online-1.2.0"])

    def test_the_work_folder_of_an_install_that_still_runs_is_never_removed(self):
        self.gh.add_t5dr("1.2.0")
        process = self.child(INSTALL.format(versions=["1.2.0"], key=TEST_KEY, parent=str(self.games)))
        self.assertEqual(gr.drop_dead_stages("t5dr", str(self.games)), 0)
        self.assertEqual(len(list(self.games.glob(".openrecomp-setup-t5dr-*"))), 1)
        self.kill(process)
        self.assertEqual(gr.drop_dead_stages("t4", str(self.games)), 0)            # another game's: not its business
        self.assertEqual(gr.drop_dead_stages("t5dr", str(self.games)), 1)

    def test_launcher_killed_in_the_middle_of_a_game_update_gets_the_old_version_back(self):
        self.gh.add_t5dr("1.2.0")
        root = gr.install_fresh("t5dr", self.offer(), str(self.games))
        save = Path(root) / "gamedata" / "save.bin"
        save.parent.mkdir()
        save.write_bytes(b"player")
        self.gh.add_t5dr("1.2.1")
        process = self.child(UPDATE.format(versions=["1.2.0", "1.2.1"], key=TEST_KEY, root=root))
        self.kill(process)
        self.assertTrue(gr.interrupted_update(root))
        setup = gs.GameSetup({}, worker=lambda fn: fn())                   # the launcher's next look at the game
        setup.check("t5dr", root, force=False)
        [(_game, kind, _value, error)] = setup.poll()
        self.assertEqual((kind, error), ("check", None))
        self.assertFalse(gr.interrupted_update(root))
        self.assertEqual(gr.installed_version("t5dr", root), "1.2.0")
        self.assertIn("1.2.0", (Path(root) / "launcher" / "core.py").read_text(encoding="utf-8"))
        self.assertEqual(save.read_bytes(), b"player")
        self.assertEqual(gr.update_in_place("t5dr", self.offer(), root)["version"], "1.2.1")
        self.assertEqual(save.read_bytes(), b"player")


if __name__ == "__main__":
    unittest.main()
