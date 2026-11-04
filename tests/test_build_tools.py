"""Missing tools use winget first, then one verified-download batch; tests never download or install anything."""
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
                        mock.patch.object(tools, "refresh_path"), \
                        mock.patch.object(tools.downloads, "install_batch", return_value=["failed"]):
                    adapter.install_prerequisites(run=lambda args, **kw: SimpleNamespace(returncode=code))
                    self.assertEqual(self.wait(adapter)["result"], result)

    def test_no_winget_uses_the_download_fallback(self):
        adapter = self.adapter(("git",))
        run = mock.Mock()
        with mock.patch.object(tools.shutil, "which", return_value=None), \
                mock.patch.object(tools.downloads, "install_batch", return_value=["ok"]) as fallback, \
                mock.patch.object(tools, "refresh_path"):
            adapter.install_prerequisites(run=run)
            self.assertEqual(self.wait(adapter)["result"], "@t4.tools.install_done")
        self.assertEqual(fallback.call_args.args[0], ["git"])
        run.assert_not_called()

    def test_download_failure_is_clear_and_retry_starts_fresh(self):
        adapter = self.adapter(("git",))
        with mock.patch.object(tools.shutil, "which", return_value=None), \
                mock.patch.object(tools.downloads, "install_batch",
                                  side_effect=[RuntimeError("@t4.tools.verification_failed"), ["ok"]]), \
                mock.patch.object(tools, "refresh_path"):
            self.assertTrue(adapter.install_prerequisites(run=mock.Mock()))
            self.assertEqual(self.wait(adapter)["result"], "@t4.tools.verification_failed")
            self.assertTrue(adapter.install_prerequisites(run=mock.Mock()))
            self.assertEqual(self.wait(adapter)["result"], "@t4.tools.install_done")

    def test_nothing_missing_or_busy_starts_nothing(self):
        adapter = self.adapter(())
        self.assertFalse(adapter.install_prerequisites(run=mock.Mock()))
        adapter = self.adapter(("git",))
        adapter._tool_install["running"] = True
        self.assertFalse(adapter.install_prerequisites(run=mock.Mock()))

    def test_only_winget_installs_are_ever_run(self):
        with mock.patch.object(tools.shutil, "which", return_value="winget"):
            for command in ("cmd /c del x", "winget uninstall --id Git.Git", "powershell -c x",
                            "winget install --id Untrusted.Tool --exact"):
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


class InstallTools(unittest.TestCase):
    def plan(self, *names):
        return [("@t4.tools." + name, tools.COMMANDS[name]) for name in names]

    def test_successful_winget_tools_are_not_downloaded_again(self):
        plan = self.plan("git", "cmake", "ninja", "vs2022")
        progress = mock.Mock()
        with mock.patch.object(tools.shutil, "which", return_value="winget"), \
                mock.patch.object(tools, "install_status", side_effect=["ok", "failed", "ok", "failed"]) as winget, \
                mock.patch.object(tools.downloads, "install_batch", return_value=["ok", "ok"]) as fallback:
            result = tools.install_tools(plan, progress=progress)
        self.assertEqual(result, ["ok"] * 4)
        self.assertEqual(winget.call_count, 4)
        self.assertEqual(fallback.call_args.args[0], ["cmake", "vs2022"])
        self.assertTrue(progress.called)

    def test_unknown_winget_install_is_rejected_before_any_installer_runs(self):
        run = mock.Mock()
        with mock.patch.object(tools.downloads, "install_batch") as fallback, self.assertRaises(ValueError):
            tools.install_tools([("untrusted", "winget install --id Untrusted.Tool --exact")], run=run)
        run.assert_not_called()
        fallback.assert_not_called()

    def test_no_winget_batches_every_missing_tool_once(self):
        with mock.patch.object(tools.shutil, "which", return_value=None), \
                mock.patch.object(tools, "install_status") as winget, \
                mock.patch.object(tools.downloads, "install_batch", return_value=["ok", "ok"]) as fallback:
            self.assertEqual(tools.install_tools(self.plan("git", "vs2022")), ["ok", "ok"])
        winget.assert_not_called()
        self.assertEqual(fallback.call_args.args[0], ["git", "vs2022"])
        self.assertEqual(fallback.call_count, 1, "one batch means one elevation request")

    def test_fallback_progress_keeps_the_original_plan_positions(self):
        progress = mock.Mock()

        def batch(names, progress, **kwargs):
            self.assertEqual(names, ["cmake"])
            progress(0, 1, "@t4.tools.cmake")
            return ["ok"]

        with mock.patch.object(tools.shutil, "which", return_value="winget"), \
                mock.patch.object(tools, "install_status", side_effect=["ok", "failed"]), \
                mock.patch.object(tools.downloads, "install_batch", side_effect=batch):
            self.assertEqual(tools.install_tools(self.plan("git", "cmake"), progress=progress), ["ok", "ok"])
        self.assertEqual(progress.call_args.args, (1, 2, "@t4.tools.cmake"))

    def test_winget_disappearing_also_falls_back(self):
        with mock.patch.object(tools.shutil, "which", return_value="winget"), \
                mock.patch.object(tools, "install_status", side_effect=FileNotFoundError("winget")), \
                mock.patch.object(tools.downloads, "install_batch", return_value=["ok"]) as fallback:
            self.assertEqual(tools.install_tools(self.plan("git")), ["ok"])
        self.assertEqual(fallback.call_args.args[0], ["git"])

    def test_reboot_stops_installing_until_the_next_launcher_start(self):
        with mock.patch.object(tools.shutil, "which", return_value="winget"), \
                mock.patch.object(tools, "install_status", side_effect=["reboot", "ok"]) as winget, \
                mock.patch.object(tools.downloads, "install_batch") as fallback:
            self.assertEqual(tools.install_tools(self.plan("git", "vs2022")), ["reboot", "pending"])
        self.assertEqual(winget.call_count, 1)
        fallback.assert_not_called()

    def test_cancel_prevents_downloads_and_later_installers(self):
        cancelled = [False]

        def install(command, **kwargs):
            cancelled[0] = True
            return "ok"

        with mock.patch.object(tools.shutil, "which", return_value="winget"), \
                mock.patch.object(tools, "install_status", side_effect=install) as winget, \
                mock.patch.object(tools.downloads, "install_batch") as fallback:
            result = tools.install_tools(self.plan("git", "vs2022"), cancelled=lambda: cancelled[0])
        self.assertEqual(result[0], "ok")
        self.assertNotEqual(result[1], "ok")
        self.assertEqual(winget.call_count, 1)
        fallback.assert_not_called()

    def test_fallback_errors_keep_the_safe_localized_message(self):
        for error in ("download_failed", "verification_failed", "elevation_cancelled"):
            with self.subTest(error=error), mock.patch.object(tools.shutil, "which", return_value=None), \
                    mock.patch.object(tools.downloads, "install_batch", side_effect=RuntimeError("@t4.tools." + error)):
                with self.assertRaisesRegex(RuntimeError, "@t4.tools." + error):
                    tools.install_tools(self.plan("git"))


if __name__ == "__main__":
    unittest.main()
