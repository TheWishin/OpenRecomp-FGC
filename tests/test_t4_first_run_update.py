"""First-run update recovery with fake worker and process APIs."""
from pathlib import Path
import unittest
from unittest import mock

from openrecomp.update_service import UpdateService


class FirstRunUpdateTests(unittest.TestCase):
    def test_prepared_update_explains_wait_and_cannot_be_replaced_by_another_check(self):
        api = mock.Mock()
        api.check_release.return_value = dict(version="v1.2.3", size=42, notes="Changes")
        api.prepare_update.return_value = "fake-plan"
        busy = [False]
        quit_app = mock.Mock()
        service = UpdateService("fake-install", api=api, busy=lambda: busy[0],
                                quit=quit_app, worker=lambda fn: fn())
        service.check()
        service.poll()
        self.assertTrue(service.install())
        busy[0] = True
        self.assertTrue(service.poll())
        self.assertEqual(service.state["phase"], "waiting")
        self.assertFalse(service.poll())
        service.check()
        api.check_release.assert_called_once()
        self.assertEqual(service.state["phase"], "waiting")
        api.launch_update.assert_not_called()
        quit_app.assert_not_called()
        busy[0] = False
        self.assertTrue(service.poll())
        api.launch_update.assert_called_once_with(Path("fake-install"), "fake-plan")
        quit_app.assert_called_once()

    def test_native_starter_explains_an_early_private_runtime_exit(self):
        # The SDK is an owner-run build: inspect the failure branch without compiling or starting it.
        source = (Path(__file__).parents[1] / "tools/starter/openrecomp.c").read_text(encoding="utf-8")
        branch = source.split("GetExitCodeProcess", 1)[1]
        self.assertIn("if (result != 0)", branch)
        self.assertIn("MessageBoxW(NULL, startup_failure(GetUserDefaultUILanguage())", branch)


if __name__ == "__main__":
    unittest.main()
