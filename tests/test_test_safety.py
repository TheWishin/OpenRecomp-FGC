"""The test run can never see or remove the owner's real folders (an uninstall test once removed a real install)."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest import mock

from openrecomp import known_installs, safety, uninstall


CHECKOUT = os.path.dirname(os.path.dirname(os.path.abspath(uninstall.__file__)))


def _inside_temp(path):
    return safety._inside(path, tempfile.gettempdir())


class Sandbox(unittest.TestCase):
    def test_the_run_is_sandboxed(self):
        self.assertEqual(os.environ.get("OPENRECOMP_TESTING"), "1")
        for name in ("LOCALAPPDATA", "APPDATA", "USERPROFILE", "HOME"):
            self.assertTrue(_inside_temp(os.environ[name]), name)
        self.assertTrue(_inside_temp(known_installs._launcher_parent()))

    def test_plan_with_the_real_module_location_stays_in_temp(self):
        plan = uninstall.plan({})
        paths = [g["root"] for g in plan["games"]] + [s["root"] for s in plan["skipped"]]
        paths += [p for p in (plan["data"],) if p]
        for path in paths:
            self.assertTrue(_inside_temp(path), path)
        for game in ("t4", "t5dr"):
            for path in known_installs.candidates({}, game):
                self.assertTrue(_inside_temp(path), path)

    def test_execute_refuses_a_path_outside_temp(self):
        outside = os.path.dirname(os.path.dirname(os.path.abspath(uninstall.__file__)))
        if _inside_temp(outside):
            self.skipTest("checkout lives in the temp folder")
        for the_plan in (dict(games=[dict(game="t4", root=outside)]), dict(data=outside), dict(program=outside)):
            with self.assertRaises(ValueError):
                uninstall.execute(the_plan, start=lambda *a, **k: self.fail("started"))
        self.assertTrue(os.path.isdir(outside))

    def test_program_decides_where_installs_beside_it_are_searched(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = os.path.join(temp, "T4")
            os.makedirs(folder)
            with open(os.path.join(folder, "openrecomp-release.json"), "w", encoding="utf-8") as f:
                f.write('{"game": "t4", "installed_by": "OpenRecomp-FGC"}')
            self.assertEqual(known_installs.candidates({}, "t4", parent=temp), [folder])
            self.assertEqual(known_installs.candidates({}, "t4"), [])


class EveryDestructivePath(unittest.TestCase):
    """A folder the run did not make itself (here: made with os.makedirs in the checkout, like a real install found
    on the PC) is refused by everything that removes, moves or exchanges folders -- before the first file moves."""

    def setUp(self):
        self.root = os.path.join(CHECKOUT, "build", "not-made-by-a-test-" + uuid.uuid4().hex, "T4")
        os.makedirs(os.path.join(self.root, "save"))
        self.addCleanup(shutil.rmtree, os.path.dirname(self.root), True)
        with open(os.path.join(self.root, "openrecomp-release.json"), "w", encoding="utf-8") as f:
            f.write('{"game": "t4", "version": "0.1.0", "installed_by": "OpenRecomp-FGC"}')
        with open(os.path.join(self.root, "save", "slot1"), "w", encoding="utf-8") as f:
            f.write("a save")
        self.before = self.listing()

    def listing(self):
        parent = os.path.dirname(self.root)
        return sorted(os.path.relpath(os.path.join(d, n), parent) for d, ds, fs in os.walk(parent) for n in ds + fs)

    def tearDown(self):
        self.assertEqual(self.listing(), self.before)          # nothing moved out, nothing kept, nothing staged

    def test_remove_game_refuses_before_it_moves_the_saves_out(self):
        with self.assertRaises(ValueError):
            uninstall.remove_game("t4", self.root)

    def test_setup_uninstaller_outside_is_never_started(self):
        exe = os.path.join(self.root, uninstall.SETUP_UNINSTALLER)
        with self.assertRaises(ValueError):
            uninstall.execute(dict(setup_uninstaller=exe), start=lambda *a, **k: self.fail("started"))

    def test_game_install_update_and_restore_refuse(self):
        from openrecomp import game_releases as gr
        offer = dict(version="0.1.1", tag="v0.1.1", zip=dict(name="x.zip", size=1, sha256="0" * 64))
        with self.assertRaises(ValueError):
            gr.install_fresh("t4", offer, os.path.dirname(self.root))
        with self.assertRaises(ValueError):
            gr.update_in_place("t4", offer, self.root)
        with self.assertRaises(ValueError):
            gr.swap(gr.SOURCES["t4"], self.root, self.root, self.root + "-backup")
        with self.assertRaises(ValueError):
            gr.undo_swap(self.root, self.root, self.root, [], [])
        stage = gr.update_stage(self.root)
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(gr, "update_stage", return_value=temp):
            os.makedirs(os.path.join(temp, "backup", "tools"))
            with self.assertRaises(ValueError):
                gr.recover_update("t4", self.root)
        self.assertFalse(os.path.exists(stage))

    def test_the_launcher_updater_refuses(self):
        from openrecomp import updater
        for call in (lambda: updater._work_root(self.root), lambda: updater.stage_update(self.root, dict(version="v9.9.9")),
                     lambda: updater.prepare_update(self.root, os.path.join(self.root, "new")),
                     lambda: updater.clean_finished(self.root), lambda: updater.update_result(self.root)):
            with self.assertRaises(ValueError):
                call()
        self.assertFalse(updater.release_stale_lock(self.root))

    def test_a_folder_the_run_made_with_tempfile_is_allowed_wherever_it_is(self):
        with tempfile.TemporaryDirectory(dir=os.path.join(CHECKOUT, "build")) as made:
            self.assertFalse(_inside_temp(made))
            safety.require_removable(os.path.join(made, "T4"))
            self.assertIn(os.path.normcase(os.path.realpath(made)), os.environ[safety.DIRS_ENV].split(os.pathsep))
        with self.assertRaises(ValueError):
            safety.require_removable(os.path.join(CHECKOUT, "build"))


class RunnerDetection(unittest.TestCase):
    def run_python(self, code, **env):
        environment = {k: v for k, v in os.environ.items() if not k.startswith("OPENRECOMP_TEST")}
        environment.update(PYTHONPATH=CHECKOUT, **env)
        return subprocess.run([sys.executable, "-B", "-c", code], env=environment, capture_output=True, text=True,
                              timeout=60).stdout.strip()

    def test_a_launcher_that_loads_unittest_later_is_not_a_test_run(self):
        code = "import openrecomp, unittest; from openrecomp import safety; print(safety.testing(), safety.sandbox())"
        self.assertEqual(self.run_python(code), "False None")

    def test_a_runner_loaded_first_or_the_switch_makes_a_test_run(self):
        code = "import unittest, openrecomp, os; from openrecomp import safety; print(safety.testing(), bool(safety.sandbox()))"
        self.assertEqual(self.run_python(code), "True True")
        code = "import openrecomp; from openrecomp import safety; print(safety.testing(), bool(safety.sandbox()))"
        self.assertEqual(self.run_python(code, OPENRECOMP_TESTING="1"), "True True")

    def test_a_child_of_the_run_lives_in_the_same_sandbox(self):
        code = "import openrecomp, os; from openrecomp import safety; print(safety.sandbox())"
        environment = dict(os.environ, PYTHONPATH=CHECKOUT)
        out = subprocess.run([sys.executable, "-B", "-c", code], env=environment, capture_output=True, text=True, timeout=60)
        self.assertEqual(out.stdout.strip(), safety.sandbox())
        self.assertTrue(os.path.isdir(safety.sandbox()))        # the child did not take it away on exit


if __name__ == "__main__":
    unittest.main()
