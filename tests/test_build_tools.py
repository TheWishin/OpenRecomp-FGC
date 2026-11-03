"""The winget side of the build tools: only the missing installers run, hidden, without a shell, and the PATH they
add is picked up. What the Build page shows of the tools (one line, never a list; Build installs them) is in
test_build_page."""
import subprocess
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp.adapters import t4_prerequisites as tools
from openrecomp.adapters.t4 import T4
from test_t4 import MANIFEST, FakeCore

VERSIONS = [("python", "3.12.10"), ("git", "2.55.0"), ("cmake", "4.4.4"), ("ninja", "1.13.2"),
            ("vs2022", "17.14.3"), ("msvc", "14.44.35207")]


class Core(FakeCore):
    source_only = False


class AdapterInstall(unittest.TestCase):
    def adapter(self, missing):
        adapter = T4(MANIFEST, {}, "fake-root", core=Core())
        adapter._prerequisite_rows = [dict(id=sid, label="@t4.tools." + sid, value="x", ok=sid not in missing,
                                           command=tools.COMMANDS[sid]) for sid, _v in VERSIONS]
        adapter.refresh_prerequisites = mock.Mock(return_value=True)
        return adapter

    def wait(self, adapter):
        for _ in range(200):
            if not adapter.prerequisite_install_state()["running"]:
                return adapter.prerequisite_install_state()
            time.sleep(0.01)
        self.fail("install never ended")

    def test_only_the_missing_commands_run_once_each_then_a_recheck(self):
        adapter = self.adapter(("git", "vs2022", "msvc"))
        calls = []
        run = lambda args, **kw: calls.append(args) or SimpleNamespace(returncode=0)  # noqa: E731
        with mock.patch.object(tools.shutil, "which", return_value="C:/winget.exe"), \
                mock.patch.object(tools, "refresh_path") as refresh_path:
            self.assertTrue(adapter.install_prerequisites(run=run))
            state = self.wait(adapter)
        self.assertEqual(state["result"], "@t4.tools.install_done")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][:5], ["C:/winget.exe", "install", "--id", "Git.Git", "--exact"])
        self.assertIn("--passive --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended", calls[1])
        for args in calls:
            self.assertEqual(args[-len(tools.WINGET_FLAGS):], tools.WINGET_FLAGS)
        refresh_path.assert_called_once()
        adapter.refresh_prerequisites.assert_called_once()

    def test_already_installed_is_fine_and_a_real_failure_is_said(self):
        for code, result in ((0x8A15002B, "@t4.tools.install_done"), (1, "@t4.tools.install_failed")):
            with self.subTest(code=hex(code)):
                adapter = self.adapter(("git",))
                with mock.patch.object(tools.shutil, "which", return_value="winget"), \
                        mock.patch.object(tools, "refresh_path"):
                    adapter.install_prerequisites(run=lambda args, **kw: SimpleNamespace(returncode=code))
                    self.assertEqual(self.wait(adapter)["result"], result)

    def test_no_winget_says_so_and_runs_nothing(self):
        adapter = self.adapter(("git",))
        run = mock.Mock()
        with mock.patch.object(tools.shutil, "which", return_value=None):
            adapter.install_prerequisites(run=run)
            self.assertEqual(self.wait(adapter)["result"], "@t4.tools.no_winget")
        run.assert_not_called()

    def test_nothing_missing_or_busy_starts_nothing(self):
        adapter = self.adapter(())
        self.assertFalse(adapter.install_prerequisites(run=mock.Mock()))
        adapter = self.adapter(("git",))
        adapter._tool_install["running"] = True
        self.assertFalse(adapter.install_prerequisites(run=mock.Mock()))

    def test_only_winget_installs_are_ever_run(self):
        with mock.patch.object(tools.shutil, "which", return_value="winget"):
            for command in ("cmd /c del x", "winget uninstall --id Git.Git", "powershell -c x"):
                with self.subTest(command=command), self.assertRaises(ValueError):
                    tools.winget_args(command)

    def test_installs_run_hidden_without_a_shell(self):
        run = mock.Mock(return_value=SimpleNamespace(returncode=0))
        with mock.patch.object(tools.shutil, "which", return_value="winget"):
            self.assertTrue(tools.run_install(tools.COMMANDS["git"], run=run))
        kwargs = run.call_args.kwargs
        self.assertNotIn("shell", kwargs)
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)

    def test_new_path_parts_are_added_once(self):
        env = {"PATH": r"C:\Windows;C:\Tools"}
        added = tools.refresh_path(env, read=lambda: [r"C:\Windows;C:\Program Files\Git\cmd", r"C:\tools\;D:\New"])
        self.assertEqual(added, [r"C:\Program Files\Git\cmd", r"D:\New"])
        self.assertEqual(env["PATH"], r"C:\Windows;C:\Tools;C:\Program Files\Git\cmd;D:\New")
        self.assertEqual(tools.refresh_path(env, read=lambda: [r"D:\New"]), [])


if __name__ == "__main__":
    unittest.main()
