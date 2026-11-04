"""Build preflight uses only a synthetic install and mocked child processes."""
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp import i18n
from openrecomp.adapters import t5dr
from openrecomp.nav import Game, Nav
from test_nav import Fake, manifest


class Settings(dict):
    coexistence = False


class T5InstallChecks(unittest.TestCase):
    def setUp(self):
        home = Path(__file__).resolve().parents[1] / "build" / "tmp-home"
        home.mkdir(parents=True, exist_ok=True)
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory(dir=home)))
        self.root = self.folder / "synthetic-install"
        self.python = self.root / "python" / "python.exe"
        self.marker = self.root / "python" / ".runtime-marker"
        self.marker.parent.mkdir(parents=True)
        self.marker.write_text("synthetic runtime identity", encoding="utf-8")
        (self.root / "tools").mkdir()
        (self.root / "tools" / "build_game.py").write_text("# Inert build-tool marker.\n", encoding="utf-8")
        (self.root / "toolchain").mkdir()
        (self.root / "deps" / "ps3recomp").mkdir(parents=True)
        self.real_isfile = os.path.isfile
        self.real_stat = os.stat
        self.files = self.enterContext(mock.patch.object(t5dr.os.path, "isfile", side_effect=self.isfile))
        self.stats = self.enterContext(mock.patch.object(t5dr.os, "stat", side_effect=self.stat))
        self.run = self.enterContext(mock.patch.object(t5dr.subprocess, "run"))
        self.a = self.adapter(self.root)

    def isfile(self, path):
        if os.fspath(path) == str(self.python):
            return self.real_isfile(self.marker)
        return self.real_isfile(path)

    def stat(self, path, *args, **kwargs):
        if isinstance(path, (str, os.PathLike)) and os.fspath(path) == str(self.python):
            path = self.marker
        return self.real_stat(path, *args, **kwargs)

    def adapter(self, root):
        a = object.__new__(t5dr.T5DR)
        a.root = str(root)
        a.s = Settings(pkg="synthetic-package", rap="synthetic-license", low_priority=False)
        a.s.out_dir = str(root / "output")
        a.core = SimpleNamespace(BuildRun=mock.Mock(return_value=SimpleNamespace(
            cmd=["launcher-python", "synthetic-build-tool"], start=mock.Mock())))
        return a

    def test_missing_python_blocks_readiness_and_build_without_fallback(self):
        self.marker.unlink()
        self.marker.parent.rmdir()
        self.assertEqual(self.a.build_ready(), "@t5.install_incomplete_python")
        with self.assertRaisesRegex(RuntimeError, "@t5.install_incomplete_python"):
            self.a.build_start()
        self.a.core.BuildRun.assert_not_called()
        self.run.assert_not_called()

    def test_missing_crypto_blocks_build_before_buildrun_is_created(self):
        self.run.side_effect = subprocess.CalledProcessError(1, [str(self.python)])
        self.assertEqual(self.a.build_ready(), "@t5.install_incomplete_python")
        with self.assertRaisesRegex(RuntimeError, "@t5.install_incomplete_python"):
            self.a.build_start()
        self.a.core.BuildRun.assert_not_called()

    def test_timeout_and_failed_python_launch_have_actionable_errors(self):
        for error in (subprocess.TimeoutExpired([str(self.python)], 3), OSError("synthetic launch failure")):
            with self.subTest(error=type(error).__name__):
                self.run.side_effect = error
                a = self.adapter(self.root)
                self.assertEqual(a.build_install_problem(), "@t5.install_incomplete_python")

    def test_probe_uses_only_install_python_with_short_timeout_and_caches_it(self):
        self.assertEqual(self.a.build_install_problem(), "")
        self.assertEqual(self.a.build_ready(), "")
        self.run.assert_called_once_with(
            [str(self.python), "-I", "-c", "from Crypto.Cipher import AES"], cwd=str(self.root),
            timeout=3, check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=t5dr.NO_WINDOW)

    def test_runtime_replacement_invalidates_probe(self):
        self.assertEqual(self.a.build_install_problem(), "")
        self.marker.write_text("replacement runtime with different identity", encoding="utf-8")
        self.run.side_effect = subprocess.CalledProcessError(1, [str(self.python)])
        self.assertEqual(self.a.build_install_problem(), "@t5.install_incomplete_python")
        self.assertEqual(self.run.call_count, 2)

    def test_missing_python_after_success_does_not_reuse_probe(self):
        self.assertEqual(self.a.build_install_problem(), "")
        self.marker.unlink()
        self.assertEqual(self.a.build_install_problem(), "@t5.install_incomplete_python")
        with self.assertRaisesRegex(RuntimeError, "@t5.install_incomplete_python"):
            self.a.build_start()
        self.a.core.BuildRun.assert_not_called()
        self.run.assert_called_once()

    def test_python_directory_replacement_invalidates_probe(self):
        self.assertEqual(self.a.build_install_problem(), "")
        current = self.real_stat(self.marker.parent)
        os.utime(self.marker.parent, ns=(current.st_atime_ns, current.st_mtime_ns + 1_000_000_000))
        self.assertEqual(self.a.build_install_problem(), "")
        self.assertEqual(self.run.call_count, 2)

    def test_selecting_another_install_does_not_reuse_successful_probe(self):
        self.assertEqual(self.a.build_install_problem(), "")
        other_root = self.folder / "other-install"
        other_python = other_root / "python" / "python.exe"
        self.a.root = str(other_root)
        self.run.side_effect = subprocess.CalledProcessError(1, [str(other_python)])

        def other_stat(path, *args, **kwargs):
            if isinstance(path, (str, os.PathLike)):
                if Path(path) == other_python:
                    return self.real_stat(self.marker)
                if Path(path) == other_python.parent:
                    return self.real_stat(self.marker.parent)
            return self.stat(path, *args, **kwargs)

        with mock.patch.object(t5dr.os, "stat", side_effect=other_stat):
            self.assertEqual(self.a.build_install_problem(), "@t5.install_incomplete_python")
        self.assertEqual(self.run.call_count, 2)
        self.assertEqual(self.run.call_args.args[0][0], str(other_python))

    def test_missing_build_script_toolchain_or_recompiler_is_repairable(self):
        for path in (self.root / "tools" / "build_game.py", self.root / "toolchain",
                     self.root / "deps" / "ps3recomp"):
            with self.subTest(path=path.name):
                saved = path.with_name(path.name + ".saved")
                path.rename(saved)
                try:
                    self.assertEqual(self.a.build_install_problem(), "@t5.install_incomplete_tools")
                    with self.assertRaisesRegex(RuntimeError, "@t5.install_incomplete_tools"):
                        self.a.build_start()
                    self.a.core.BuildRun.assert_not_called()
                finally:
                    saved.rename(path)

    def test_build_always_uses_validated_install_python(self):
        self.a.build_start(force=True)
        run = self.a.core.BuildRun.return_value
        self.assertEqual(run.cmd[0], str(self.python))
        run.start.assert_called_once_with()
        self.a.core.BuildRun.assert_called_once_with(
            "synthetic-package", "synthetic-license", str(self.root / "output"), force=True,
            low_priority=False)

    def test_install_check_precedes_package_and_license_selection(self):
        self.a.s.update(pkg="", rap="")
        self.marker.unlink()
        self.assertEqual(self.a.build_ready(), "@t5.install_incomplete_python")

    def test_check_my_problem_reports_missing_python_without_native_diagnostics(self):
        self.marker.unlink()
        check = mock.Mock()
        with mock.patch.object(self.a, "_support_runtime", return_value=(check, mock.Mock())):
            self.a._support_work("check")
        check.check.assert_not_called()
        self.assert_install_finding()

    def test_check_my_problem_survives_missing_crypto_and_broken_native_diagnostics(self):
        self.run.side_effect = subprocess.CalledProcessError(1, [str(self.python)])
        with mock.patch.object(self.a, "_support_runtime", side_effect=ImportError("synthetic missing diagnostics")), \
                mock.patch("openrecomp.adapters.support.threading.Thread") as thread:
            self.assertTrue(self.a.support_available())
            self.assertTrue(self.a.support_start("check"))
            kwargs = thread.call_args.kwargs
            kwargs["target"](*kwargs["args"])
        self.assert_install_finding()

    def test_check_my_problem_remains_available_with_incomplete_native_report_api(self):
        check = SimpleNamespace(check=mock.Mock(return_value=[]))
        report = SimpleNamespace(Context=mock.Mock(), settings_lines=mock.Mock(), build_info_for=mock.Mock(),
                                 discover=mock.Mock(), build=None)
        self.a.core.desktop_dir = mock.Mock()
        with mock.patch.object(self.a, "_support_runtime", return_value=(check, report)):
            self.assertTrue(self.a.support_available())

    def assert_install_finding(self):
        state = self.a.support_state()
        self.assertFalse(state["running"])
        self.assertTrue(state["checked"])
        self.assertEqual(state["error"], "")
        self.assertEqual(state["findings"], [dict(
            id="t5_install", label="@support.finding.t5_install.title", seen="",
            fix="@t5.install_incomplete_python", kind="problem")])


class Incomplete(Fake):
    root = "synthetic-install"

    def build_install_problem(self):
        return "@t5.install_incomplete_python"


class T5InstallRecovery(unittest.TestCase):
    def setUp(self):
        self.a = Incomplete(manifest("t5dr", adapter="t5dr"), is_ready=False)
        self.setup = mock.Mock(return_value=True)
        self.nav = Nav([Game(self.a.m, self.a)], language="en", on_setup=self.setup)
        self.nav.screen = "hub"
        self.nav.sec["t5dr"] = "build"

    def test_build_page_shows_repair_actions_and_explanation(self):
        with mock.patch.object(self.a, "sources", side_effect=AssertionError("do not inspect game sources")):
            items = self.nav.items()
        by_id = {it["id"]: it for it in items}
        self.assertIn("build_reinstall", by_id)
        self.assertTrue(by_id["build_reinstall"]["primary"])
        self.assertIn("build_choose_install", by_id)
        self.assertNotIn("build", by_id)
        self.assertEqual(self.nav.view()["build"]["main"]["lead"],
                         i18n.text("en", "t5.install_incomplete_python"))
        self.assertEqual(self.a.calls, [])

    def test_controller_can_choose_another_folder(self):
        items = self.nav.items()
        self.nav.focus["t5dr:build"] = next(i for i, row in enumerate(items)
                                              if row["id"] == "build_choose_install")
        with mock.patch.object(self.nav, "_picker_entries", return_value=[]):
            self.nav.act("confirm", device="xbox")
        self.assertEqual(self.nav.overlay, "picker")
        self.assertEqual(self.nav.picker["target"], "source:folder")
        self.assertEqual(self.a.calls, [])

    def test_one_controller_confirm_reinstalls_existing_folder(self):
        self.nav.setup_state = {"t5dr": dict(phase="ready", latest="1.2.0")}
        items = self.nav.items()
        self.nav.focus["t5dr:build"] = next(i for i, row in enumerate(items)
                                              if row["id"] == "build_reinstall")
        self.nav.act("confirm", device="xbox")
        self.setup.assert_called_once_with("reinstall", "t5dr", None)
        self.assertEqual(self.nav.overlay, "dialog")
        self.assertEqual(self.nav.confirm_kind, "setup_progress")
        self.assertEqual(self.a.calls, [])

    def test_reinstall_waits_for_release_check_then_continues_without_second_confirm(self):
        items = self.nav.items()
        self.nav.focus["t5dr:build"] = next(i for i, row in enumerate(items)
                                              if row["id"] == "build_reinstall")
        self.nav.act("confirm", device="xbox")
        self.setup.assert_called_once_with("check", "t5dr", True)
        self.assertEqual(self.nav.confirm_kind, "setup_loading")
        self.nav.setup_state = {"t5dr": dict(phase="ready", latest="1.2.0")}
        self.nav.poll_setup([("t5dr", "check", {}, None)])
        self.assertEqual(self.setup.call_args, mock.call("reinstall", "t5dr", None))
        self.assertEqual(self.nav.confirm_kind, "setup_progress")


if __name__ == "__main__":
    unittest.main()
