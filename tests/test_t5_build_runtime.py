"""Legacy start() must not undo the selected Python or change shared module state."""
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp.adapters.t5_build_runtime import start_build_with_python


class InstalledBuild:
    def __init__(self):
        self.cmd = ["launcher-python", "build_game.py"]
        self.launch = mock.Mock()

    def start(self):
        if sys.executable.lower().endswith("pythonw.exe"):
            self.cmd[0] = "wrong-launcher-python"
        return self.launch(self.cmd, sys.executable, sys.version)


class BuildPythonIsolation(unittest.TestCase):
    def setUp(self):
        self.executable = r"D:\WINDOWS 11\Desktop\Tekken\T5DR\python\python.exe"
        # This is the installed function's sys global. The shared sys module must
        # remain untouched while the cloned function observes the selected Python.
        self.source_sys = InstalledBuild.start.__globals__["sys"]
        self.original_executable = self.source_sys.executable

    def assert_shared_unchanged(self):
        self.assertIs(InstalledBuild.start.__globals__["sys"], self.source_sys)
        self.assertEqual(self.source_sys.executable, self.original_executable)

    def test_selected_python_and_return_value_without_shared_changes(self):
        run = InstalledBuild()
        expected = run.launch.return_value
        self.assertIs(start_build_with_python(run, self.executable), expected)
        run.launch.assert_called_once_with(
            [self.executable, "build_game.py"], self.executable, sys.version)
        self.assert_shared_unchanged()

    def test_start_failure_does_not_change_shared_sys(self):
        run = InstalledBuild()
        error = OSError("synthetic failed child creation")
        run.launch.side_effect = error
        with self.assertRaises(OSError) as caught:
            start_build_with_python(run, self.executable)
        self.assertIs(caught.exception, error)
        self.assert_shared_unchanged()

    def test_unknown_start_api_fails_without_calling_unprotected_start(self):
        run = SimpleNamespace(cmd=["launcher-python"], start=mock.Mock())
        with self.assertRaisesRegex(RuntimeError, "@t5.install_incomplete_tools"):
            start_build_with_python(run, self.executable)
        run.start.assert_not_called()
        self.assertEqual(run.cmd, ["launcher-python"])
        self.assert_shared_unchanged()

    def test_concurrent_start_observes_no_global_mutation(self):
        run = InstalledBuild()
        entered, release = threading.Event(), threading.Event()
        errors = []

        def launch(*args):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("test thread was not released")

        def work():
            try:
                start_build_with_python(run, self.executable)
            except BaseException as error:
                errors.append(error)

        run.launch.side_effect = launch
        worker = threading.Thread(target=work)
        worker.start()
        try:
            self.assertTrue(entered.wait(5))
            self.assert_shared_unchanged()
        finally:
            release.set()
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assert_shared_unchanged()


if __name__ == "__main__":
    unittest.main()
