"""Source-bundle tool checks use synthetic responses, never an installer or build."""
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp.adapters import t4_prerequisites as tools


class T4Prerequisites(unittest.TestCase):
    def test_rows_cover_every_required_tool_and_copy_exact_commands(self):
        with mock.patch.object(tools, "_visual_studio", return_value=(None, "")), \
                mock.patch.object(tools, "_tool", return_value=""), \
                mock.patch.object(tools.sys, "version_info", (3, 12, 8)):
            rows = tools.check_prerequisites()
        self.assertEqual([row["id"] for row in rows], ["python", "git", "cmake", "ninja", "vs2022", "msvc"])
        self.assertTrue(rows[0]["ok"])
        self.assertFalse(any(row["ok"] for row in rows[1:]))
        for row in rows:
            self.assertEqual(set(row), {"id", "label", "value", "ok", "command"})
            self.assertTrue(row["command"].startswith("winget install --id "))
            self.assertIn("--exact", row["command"])
        self.assertIn("Microsoft.VisualStudio.Workload.VCTools", rows[-1]["command"])
        self.assertIn("--includeRecommended", rows[-1]["command"])

    def test_old_python_and_cmake_fail_even_if_available(self):
        versions = {"git": "2.48.1", "cmake": "3.19.9", "ninja": "1.12.1"}
        with mock.patch.object(tools, "_visual_studio", return_value=(None, "")), \
                mock.patch.object(tools, "_tool", side_effect=lambda name, extra: versions[name]), \
                mock.patch.object(tools.sys, "version_info", (3, 11, 9)):
            rows = {row["id"]: row for row in tools.check_prerequisites()}
        self.assertFalse(rows["python"]["ok"])
        self.assertFalse(rows["cmake"]["ok"])
        self.assertEqual(rows["cmake"]["value"], "3.19.9")
        self.assertTrue(rows["git"]["ok"])
        self.assertTrue(rows["ninja"]["ok"])

    def test_vs2022_needs_cpp_compiler_sdk_and_environment_script(self):
        install = Path("synthetic-vs")
        for sdk, compiler, script, expected in ((True, True, True, True), (False, True, True, False),
                                                 (True, False, True, False), (True, True, False, False)):
            with self.subTest(sdk=sdk, compiler=compiler, script=script), \
                    mock.patch.object(tools, "_visual_studio", return_value=(install, "17.14.20")), \
                    mock.patch.object(tools, "_msvc_version", return_value=("14.44.35207", compiler)), \
                    mock.patch.object(tools, "_has_sdk", return_value=sdk), \
                    mock.patch.object(tools, "_tool", return_value="4.0.1"), \
                    mock.patch.object(Path, "is_file", return_value=script):
                rows = {row["id"]: row for row in tools.check_prerequisites()}
            self.assertEqual(rows["vs2022"]["ok"], expected)
            self.assertEqual(rows["msvc"]["value"], "14.44.35207")
            if not expected:
                self.assertEqual(rows["vs2022"]["value"], "@t4.tools.vs_incomplete")

    def test_vswhere_is_restricted_to_2022_and_cpp_tools(self):
        commands = []

        def output(command):
            commands.append(command)
            return "synthetic-vs" if command[-1] == "installationPath" else "17.14.20"

        with mock.patch.object(Path, "is_file", return_value=True), mock.patch.object(tools, "_output", side_effect=output):
            install, version = tools._visual_studio()
        self.assertEqual(install, Path("synthetic-vs"))
        self.assertEqual(version, "17.14.20")
        self.assertIn("[17.0,18.0)", commands[0])
        self.assertIn("Microsoft.VisualStudio.Component.VC.Tools.x86.x64", commands[0])

    def test_msvc_version_is_exact_and_requires_x64_compiler(self):
        with mock.patch.object(Path, "read_text", return_value="14.44.35207\n"), \
                mock.patch.object(Path, "is_file", return_value=True, autospec=True) as exists:
            self.assertEqual(tools._msvc_version(Path("synthetic-vs")), ("14.44.35207", True))
            self.assertTrue(exists.call_args.args[0].as_posix().endswith("14.44.35207/bin/Hostx64/x64/cl.exe"))
        with mock.patch.object(Path, "read_text", return_value="14.29.30133"), \
                mock.patch.object(Path, "is_file", return_value=True):
            self.assertEqual(tools._msvc_version(Path("synthetic-vs")), ("14.29.30133", False))
        with mock.patch.object(Path, "read_text", side_effect=OSError):
            self.assertEqual(tools._msvc_version(Path("synthetic-vs")), ("", False))

    def test_invalid_msvc_version_cannot_escape_toolset_folder(self):
        with mock.patch.object(Path, "read_text", return_value="../other"):
            self.assertEqual(tools._msvc_version(Path("synthetic-vs")), ("", False))

    def test_old_path_cmake_is_not_hidden_by_newer_fallback(self):
        with mock.patch.object(tools.shutil, "which", return_value="old-cmake"), \
                mock.patch.object(tools, "_output", return_value="cmake version 3.18.0") as output:
            version = tools._tool("cmake", [Path("synthetic-tools")])
            self.assertEqual(version, "3.18.0")
            self.assertFalse(tools._at_least(version, (3, 20)))
            output.assert_called_once_with(["old-cmake", "--version"])

    def test_fallback_is_first_existing_executable_when_path_is_missing(self):
        with mock.patch.object(tools.shutil, "which", return_value=None), \
                mock.patch.object(Path, "is_file", side_effect=[False, True, True]), \
                mock.patch.object(tools, "_output", return_value="cmake version 3.31.4") as output:
            self.assertEqual(tools._tool("cmake", [Path("absent"), Path("first"), Path("last")]), "3.31.4")
            output.assert_called_once_with([str(Path("first") / "cmake.exe"), "--version"])

    def test_unreadable_path_tool_does_not_fall_back_to_a_different_executable(self):
        with mock.patch.object(tools.shutil, "which", return_value="broken-cmake"), \
                mock.patch.object(tools, "_output", return_value="") as output:
            self.assertEqual(tools._tool("cmake", [Path("synthetic-tools")]), "")
            output.assert_called_once_with(["broken-cmake", "--version"])

    def test_version_probes_are_hidden_bounded_and_never_use_a_shell(self):
        process = mock.Mock()
        process.wait.return_value = 0
        with mock.patch.object(tools.subprocess, "Popen", return_value=process) as popen:
            self.assertEqual(tools._output(["git", "--version"]), "")
        self.assertEqual(popen.call_args.args[0], ["git", "--version"])
        self.assertFalse(popen.call_args.kwargs.get("shell", False))
        self.assertEqual(popen.call_args.kwargs["creationflags"], tools.NO_WINDOW)
        self.assertEqual(popen.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertNotEqual(popen.call_args.kwargs["stdout"], subprocess.PIPE)      # a pipe can outlive the tool
        process.wait.assert_called_once_with(tools.PROBE_SECONDS)
        with mock.patch.object(tools.subprocess, "Popen", side_effect=OSError()):
            self.assertEqual(tools._output(["git", "--version"]), "")

    def test_a_real_tool_answers_and_a_failing_one_is_empty(self):
        self.assertEqual(tools._output([sys.executable, "-c", "print('tool version 1.2.3')"]), "tool version 1.2.3")
        self.assertEqual(tools._output([sys.executable, "-c", "print('x'); raise SystemExit(3)"]), "")

    def test_a_hanging_tool_whose_helper_keeps_the_output_open_ends_the_check(self):
        """Massot's rebuild that stayed at "Checking the build tools": subprocess.run(timeout=) waits on Windows for
        the output pipe after killing the tool, and the tool's own child kept it open."""
        helper = "import time; time.sleep(12)"
        tool = ("import subprocess, sys, time; "
                f"subprocess.Popen([sys.executable, '-c', {helper!r}]); time.sleep(12)")
        started = time.monotonic()
        with mock.patch.object(tools, "PROBE_SECONDS", 1):
            self.assertEqual(tools._output([sys.executable, "-c", tool]), "")
        self.assertLess(time.monotonic() - started, 6)

    def test_unknown_tool_output_is_not_ready_and_does_not_expose_raw_output(self):
        with mock.patch.object(tools.shutil, "which", return_value="git"), \
                mock.patch.object(tools, "_output", return_value="synthetic error text"):
            self.assertEqual(tools._tool("git", []), "")

    def test_windows_git_build_suffix_keeps_numeric_version(self):
        self.assertEqual(tools._version("git version 2.49.0.windows.1"), "2.49.0")


if __name__ == "__main__":
    unittest.main()
