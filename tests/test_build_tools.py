"""Owner feedback: the Build page listed every tool with its version and a copy command per tool. Now the check runs
by itself and shows ONE row: ready (after Build), or "Install missing tools" (before Build) whose dialog lists what
winget will install; Copy commands only inside that dialog."""
import os
import subprocess
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp import i18n
from openrecomp.adapters import t4_prerequisites as tools
from openrecomp.adapters.t4 import T4
from openrecomp.nav import Game, Nav
from test_nav import Fake, manifest
from test_t4 import MANIFEST, FakeCore

VERSIONS = [("python", "3.12.10"), ("git", "2.55.0"), ("cmake", "4.4.4"), ("ninja", "1.13.2"),
            ("vs2022", "17.14.3"), ("msvc", "14.44.35207")]


class Tools(Fake):
    def __init__(self, missing=(), busy=False):
        super().__init__(manifest("t4", adapter="t4"), is_ready=False)
        self.rows = [dict(id=sid, label="@t4.tools." + sid, value="@t4.tools.missing" if sid in missing else v,
                          ok=sid not in missing, busy=busy, command=tools.COMMANDS[sid]) for sid, v in VERSIONS]
        self.install = dict(running=False, done=0, total=0, current="", result="")
        self.installed = 0

    def prerequisites(self):
        return [dict(row) for row in self.rows]

    def prerequisite_install_state(self):
        return dict(self.install)

    def install_prerequisites(self):
        self.installed += 1
        self.install = dict(running=True, done=0, total=2, current="@t4.tools.git", result="")
        return True

    def build_ready(self):
        return "@t4.tools.required" if any(not r["ok"] for r in self.rows) else ""


def build_page(adapter, language="en"):
    nav = Nav([Game(adapter.m, adapter)], language=language)
    nav.screen = "hub"
    nav.sec["t4"] = "build"
    return nav


class OneRow(unittest.TestCase):
    def tool_rows(self, nav):
        return [row for row in nav.items() if str(row.get("id", "")).startswith("tool")]

    def test_all_found_is_one_ready_line_after_build_without_versions(self):
        nav = build_page(Tools())
        ids = [row.get("id") for row in nav.items()]
        self.assertEqual([r["id"] for r in self.tool_rows(nav)], ["tools:ready"])
        self.assertGreater(ids.index("tools:ready"), ids.index("build"))
        rows = nav.view()["rows"]
        self.assertFalse(any(v in str(row.get("value", "")) for row in rows for _sid, v in VERSIONS))
        self.assertIn(i18n.text("en", "t4.tools.ready"), [row.get("label") for row in rows])

    def test_versions_live_in_the_rows_details(self):
        nav = build_page(Tools())
        nav.focus["t4:build"] = next(i for i, r in enumerate(nav.items()) if r.get("id") == "tools:ready")
        detail = nav.view()["detail"]
        self.assertEqual([r["v"] for r in detail["rows"]], [v for _sid, v in VERSIONS])

    def test_ready_line_checks_again_on_confirm(self):
        adapter = Tools()
        adapter.refresh_prerequisites = mock.Mock(return_value=True)
        nav = build_page(adapter)
        next(r for r in nav.items() if r.get("id") == "tools:ready")["run"]()
        adapter.refresh_prerequisites.assert_called_once()

    def test_missing_tools_are_one_action_before_build(self):
        nav = build_page(Tools(missing=("git", "cmake")))
        ids = [row.get("id") for row in nav.items()]
        self.assertEqual([r["id"] for r in self.tool_rows(nav)], ["tools:install"])
        self.assertLess(ids.index("tools:install"), ids.index("build"))
        row = next(r for r in nav.view()["rows"] if r.get("label") == i18n.text("en", "t4.tools.install_missing"))
        self.assertEqual(row["value"], "2 missing")

    def test_checking_is_one_quiet_line(self):
        nav = build_page(Tools(busy=True))
        rows = self.tool_rows(nav)
        self.assertEqual([(r["id"], r["disabled"]) for r in rows], [("tools:checking", True)])

    def test_dialog_lists_what_will_be_installed_and_installs_after_confirming(self):
        adapter = Tools(missing=("git", "vs2022", "msvc"))
        nav = build_page(adapter)
        next(r for r in nav.items() if r.get("id") == "tools:install")["run"]()
        dialog = nav.view()["dialog"]
        self.assertIn("Git", dialog["text"])
        self.assertIn("Visual Studio 2022", dialog["text"])
        self.assertNotIn("MSVC", dialog["text"], "VS and MSVC are one installer")
        self.assertEqual([o["label"] for o in dialog["options"]], ["Cancel", "Copy commands", "Install"])
        self.assertTrue(dialog["options"][0]["focused"], "the safe answer has the focus")
        nav.act("left", device="xbox")
        nav.act("confirm", device="xbox")
        self.assertEqual(adapter.installed, 1)
        self.assertEqual(nav.tools_installing.a, adapter)

    def test_back_or_cancel_installs_nothing(self):
        adapter = Tools(missing=("git",))
        nav = build_page(adapter)
        for keys in (["back"], ["confirm"]):
            next(r for r in nav.items() if r.get("id") == "tools:install")["run"]()
            for key in keys:
                nav.act(key, device="xbox")
        self.assertEqual(adapter.installed, 0)

    def test_copy_commands_is_the_fallback_inside_the_dialog(self):
        adapter = Tools(missing=("git", "ninja"))
        nav = build_page(adapter)
        next(r for r in nav.items() if r.get("id") == "tools:install")["run"]()
        nav.act("right", device="kb")
        nav.act("confirm", device="kb")
        self.assertEqual(nav.pending_clipboard, os.linesep.join([tools.COMMANDS["git"], tools.COMMANDS["ninja"]]))
        self.assertEqual(adapter.installed, 0)

    def test_progress_and_one_result_message(self):
        adapter = Tools(missing=("git", "cmake"))
        nav = build_page(adapter)
        next(r for r in nav.items() if r.get("id") == "tools:install")["run"]()
        nav.exit_focus = 2
        nav.act("confirm", device="kb")
        row = next(r for r in nav.view()["rows"] if r.get("label") == i18n.text("en", "t4.tools.installing"))
        self.assertEqual(row["value"], "1 of 2: Git")
        self.assertFalse(nav.tick(0.01) and nav.toast == i18n.text("en", "t4.tools.install_done"))
        adapter.install = dict(running=False, done=2, total=2, current="", result="@t4.tools.install_done")
        self.assertTrue(nav.poll_tools_install())
        self.assertEqual(nav.view()["toast"], i18n.text("en", "t4.tools.install_done"))
        self.assertFalse(nav.poll_tools_install(), "said once")

    def test_every_language_has_the_dialog(self):
        adapter = Tools(missing=("git",))
        for code in i18n.LANGUAGES:
            with self.subTest(language=code):
                nav = build_page(adapter, code)
                next(r for r in nav.items() if r.get("id") == "tools:install")["run"]()
                dialog = nav.view()["dialog"]
                self.assertNotIn("{", dialog["text"])
                self.assertFalse(any(o["label"].startswith("@") for o in dialog["options"]))


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
            self.assertEqual(args[-3:], tools.WINGET_FLAGS)
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
