"""The test run can never see or remove the owner's real folders (an uninstall test once removed a real install)."""
import os
import tempfile
import unittest

from openrecomp import known_installs, safety, uninstall


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


if __name__ == "__main__":
    unittest.main()
