"""Source-only facade checks: all external commands and game processes are mocked."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from openrecomp.adapters.t4_source import SourceCore


class SourceCoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.root = self.folder / "T4"
        self.root.mkdir()
        # Keep synthetic player files in the test fixture while modelling a
        # launcher beside, rather than containing, that player directory.
        module_patch = patch("openrecomp.adapters.t4_source.__file__",
                             str(self.folder / "launcher/openrecomp/adapters/t4_source.py"))
        module_patch.start()
        self.addCleanup(module_patch.stop)
        self.home_patch = patch("openrecomp.adapters.t4_source.user_dir", return_value=str(self.folder / "player"))
        self.home_patch.start()
        self.addCleanup(self.home_patch.stop)
        self.core = SourceCore(self.root)

    def test_initialization_does_not_create_player_data_or_start_a_command(self):
        with patch("openrecomp.adapters.t4_source.subprocess.Popen") as popen:
            self.assertEqual(self.core.load_settings()["iso"], "")
            self.assertEqual(self.core.run_lock_holder(), "")
            self.assertFalse(self.core._home.exists())
            popen.assert_not_called()

    def test_source_settings_are_atomic_and_isolated_per_install(self):
        self.core.save_settings(dict(iso="chosen.iso", sound=False))
        self.assertFalse(self.core.load_settings()["sound"])
        other = SourceCore(self.folder / "T4-other")
        self.assertNotEqual(self.core.SAVE_DIR, other.SAVE_DIR)
        self.assertEqual(other.load_settings()["iso"], "")
        self.assertFalse((self.root / "launcher").exists())

    def test_player_data_inside_source_is_refused(self):
        with patch("openrecomp.adapters.t4_source.user_dir", return_value=str(self.root / "player")):
            with self.assertRaisesRegex(RuntimeError, "t4.source.data_outside"):
                SourceCore(self.root)

    def test_build_command_preserves_iso_as_one_argument(self):
        command = self.core.build_command("space and ; command.iso")
        self.assertEqual(command[-2:], ["-Iso", "space and ; command.iso"])
        self.assertEqual(Path(command[command.index("-File") + 1]), self.root / "tools" / "build_game.ps1")
        env = self.core.build_env()
        self.assertEqual(Path(env["TEKKEN4_SRC"]), self.root / "deps" / "ps2recomp")
        self.assertEqual(env["TEKKEN4_BUILD_DIR"], "runtime")

    def test_verifier_calls_only_check_and_accepts_explicit_ok(self):
        with patch("openrecomp.adapters.t4_source.os.path.isfile", return_value=True), \
                patch("openrecomp.adapters.t4_source.subprocess.run", return_value=Mock(returncode=0, stdout="OK\n")) as run:
            self.assertEqual(self.core.verify_iso("chosen.iso"), (True, ""))
        args, kwargs = run.call_args
        self.assertEqual(args[0][-2:], ["chosen.iso", "--check"])
        self.assertNotIn("--files", args[0])
        self.assertEqual(kwargs["cwd"], str(self.root.resolve()))
        with patch("openrecomp.adapters.t4_source.os.path.isfile", return_value=True), \
                patch("openrecomp.adapters.t4_source.subprocess.run", return_value=Mock(returncode=0, stdout="")):
            self.assertFalse(self.core.verify_iso("chosen.iso")[0])

    def test_wrong_disc_and_wrong_elf_are_clearly_refused(self):
        for code, message in ((2, "@t4.source.iso_wrong"), (3, "@t4.source.iso_checksum")):
            with self.subTest(code=code), \
                    patch("openrecomp.adapters.t4_source.os.path.isfile", return_value=True), \
                    patch("openrecomp.adapters.t4_source.subprocess.run", return_value=Mock(returncode=code, stdout="")):
                ok, reason = self.core.verify_iso("chosen.iso")
                self.assertFalse(ok)
                self.assertIn(message, reason)

    def test_adapter_iso_selection_uses_source_verifier_and_saves_only_success(self):
        from openrecomp.adapters.t4 import T4
        with patch.object(T4, "refresh_prerequisites", return_value=False):
            adapter = T4(dict(id="t4"), {}, str(self.root), core=self.core)
        stamp = ("chosen.iso", 100, 1)
        with patch.object(adapter, "_iso_stamp", return_value=stamp), \
                patch("openrecomp.adapters.t4_source.os.path.isfile", return_value=True), \
                patch("openrecomp.adapters.t4_source.subprocess.run", return_value=Mock(returncode=3, stdout="")), \
                patch.object(self.core, "save_settings") as save:
            adapter._check_iso("chosen.iso")
            self.assertFalse(adapter.source_state()["ok"])
            self.assertEqual(adapter.s["iso"], "")
            save.assert_not_called()
        with patch.object(adapter, "_iso_stamp", return_value=stamp), \
                patch("openrecomp.adapters.t4_source.os.path.isfile", return_value=True), \
                patch("openrecomp.adapters.t4_source.subprocess.run", return_value=Mock(returncode=0, stdout="OK\n")), \
                patch.object(self.core, "save_settings") as save:
            adapter._check_iso("chosen.iso")
            self.assertTrue(adapter.source_state()["ok"])
            self.assertEqual(adapter.s["iso"], "chosen.iso")
            self.assertEqual(adapter._verified_iso, stamp)
            save.assert_called_once()

    def test_verifier_reports_timeout_and_start_failure(self):
        for error in (subprocess.TimeoutExpired("check", 600), OSError("missing")):
            with self.subTest(error=type(error)), \
                    patch("openrecomp.adapters.t4_source.os.path.isfile", return_value=True), \
                    patch("openrecomp.adapters.t4_source.subprocess.run", side_effect=error):
                self.assertFalse(self.core.verify_iso("chosen.iso")[0])

    def test_no_runtime_or_iso_blocks_play(self):
        self.assertIn("@online.build_required", self.core.play_problems({}))
        self.assertIn("@iso.choose_first", self.core.play_problems({}))
        run = self.core.GameRun({})
        with patch("openrecomp.adapters.t4_source.subprocess.Popen") as popen:
            with self.assertRaises(RuntimeError):
                run.start()
            popen.assert_not_called()

    def test_game_environment_drops_shell_experiments_and_uses_settings(self):
        with patch.dict(os.environ, {"TEKKEN4_RB_TEST": "1", "TEKKEN4_RAND_SEED": "7",
                                     "TEKKEN4_NET": "host:9999", "PS2X_GS_HW_SCALE": "9"}):
            env = self.core.game_env(dict(sound=False, resolution="native", fullscreen=True,
                                          fullscreen_exclusive=True))
        for name in ("TEKKEN4_RB_TEST", "TEKKEN4_RAND_SEED", "TEKKEN4_NET", "PS2X_GS_HW_SCALE"):
            self.assertNotIn(name, env)
        self.assertEqual(env["TEKKEN4_SOUND"], "0")
        self.assertEqual(env["TEKKEN4_INTERNAL_RES"], "native")
        self.assertEqual(env["TEKKEN4_FULLSCREEN"], "exclusive")

    def test_game_run_uses_player_directory_and_current_environment_callback(self):
        settings = dict(iso="chosen.iso")
        run = self.core.GameRun(settings)
        process = Mock()
        process.wait.return_value = 0
        process.poll.return_value = None
        self.core.game_env = Mock(return_value={"TEST_ENV": "current"})
        with patch.object(self.core, "play_problems", return_value=[]), \
                patch.object(self.core, "find_runtime", return_value=("runner-placeholder", "source")), \
                patch("openrecomp.adapters.t4_source.subprocess.Popen", return_value=process) as popen:
            run.start()
            record = run.wait()
        self.assertTrue(record["ok"])
        self.assertEqual(popen.call_args.args[0], ["runner-placeholder", self.core.GAME_ELF])
        self.assertEqual(popen.call_args.kwargs["cwd"], self.core.SAVE_DIR)
        self.assertEqual(popen.call_args.kwargs["env"], {"TEST_ENV": "current"})
        self.assertTrue(all(stream.closed for stream in run._streams))
        run.stop()
        process.terminate.assert_called_once()

    def test_process_failure_closes_log_handles(self):
        run = self.core.GameRun({})
        with patch.object(self.core, "play_problems", return_value=[]), \
                patch.object(self.core, "find_runtime", return_value=("runner-placeholder", "source")), \
                patch("openrecomp.adapters.t4_source.subprocess.Popen", side_effect=OSError("start failed")):
            with self.assertRaises(OSError):
                run.start()
        self.assertTrue(all(stream.closed for stream in run._streams))


if __name__ == "__main__":
    unittest.main()
