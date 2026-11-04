"""Direct beta preflight and session ownership, with fake tools and processes only."""
import json
import os
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from openrecomp.adapters.base import Adapter
from openrecomp.adapters.t4_online import DIRECT_CHECKS, DirectCheckError, PREFLIGHT_SCRIPT, T4Online
from openrecomp.adapters import t4_online

_NO_SHIPPED_SERVER = mock.patch.object(t4_online, "SHIPPED_SERVERS", os.path.join(os.devnull, "servers.json"))


def setUpModule():
    # Direct IP is the start screen only while no T4 server is known: never depend on what the
    # shipped server list (a placeholder until the beta server is filled in) holds.
    _NO_SHIPPED_SERVER.start()


def tearDownModule():
    _NO_SHIPPED_SERVER.stop()


class Subject(T4Online, Adapter):
    def __init__(self, folder):
        Adapter.__init__(self, dict(id="t4", short="T4"), {})
        self.root = folder
        self.s = {}
        self.exit_code = None
        self.starts = []
        self.core = SimpleNamespace(SAVE_DIR=folder, run_lock_holder=lambda: "",
                                    find_runtime=lambda s: (os.path.join(folder, "runtime", "runner"), ""),
                                    effective_iso=lambda s: os.path.join(folder, "disc.fixture"))

    def ready(self):
        return True

    def running(self):
        return bool(self.starts and self.exit_code is None)

    def start(self, extra_env=None):
        self.starts.append(extra_env)
        self.exit_code = None
        self.run = SimpleNamespace(proc=SimpleNamespace(poll=lambda: self.exit_code), stop=self.stop)

    def stop(self):
        self.exit_code = 0

    def _direct_submit(self, action, work):
        self._direct_busy = True
        try:
            value, error = work(), None
        except Exception as exc:
            value, error = None, exc
        self._direct_results.put((self._direct_generation, action, value, error))

    def _online_stop_submit(self, work):
        work()
        return None


class DirectBetaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.temp.cleanup)
        self.a = Subject(self.temp.name)
        self.a.online_action("mode_direct")
        self.a.online_state()
        self.stamps = self.enterContext(mock.patch.object(self.a, "_direct_stamp", side_effect=lambda p: (p, 1, 1)))
        self.scan = self.enterContext(mock.patch.object(self.a, "_online_game_check", return_value=""))

    def verified(self):
        return dict(paths=("runtime.fixture",), stamps=(("runtime.fixture", 1, 1),),
                    build="0123456789abcdef", checks=dict.fromkeys(DIRECT_CHECKS, True),
                    checked_at=time.monotonic(), run_dir=self.temp.name)

    def check(self):
        with mock.patch.object(self.a, "_direct_preflight", return_value=self.verified()):
            self.a.online_action("check")
            self.a.online_poll()

    def play(self):
        self.check()
        self.a.online_action("start_match")
        self.a.online_poll()

    def test_shipping_adapter_has_direct_only_capabilities_without_importing_client(self):
        with mock.patch("openrecomp.adapters.t4_online.importlib.import_module", side_effect=AssertionError):
            state = self.a.online_state()
            self.a.online_poll()
            self.a.online_action("login_guest")
            self.a.online_action("search_ranked")
            self.a.online_action("search_quick")
        self.assertEqual(state["capabilities"], dict(direct_ip=True, lobby=False, ranked=False, match_flow=False,
                                                    lobby_available=True))
        self.assertEqual(self.a.starts, [])
        self.scan.assert_not_called()

    def test_snapshot_never_exposes_the_peer_address(self):
        self.a.set_text_value("online_address", "192.0.2.8")
        self.assertEqual(self.a.text_value("online_address"), "192.0.2.8")
        self.assertNotIn("192.0.2.8", json.dumps(self.a.online_state()))

    def test_start_requires_a_successful_check(self):
        self.a.online_action("start_match")
        self.assertEqual(self.a.online_state()["message"], "@t4.direct_check_required")
        self.assertEqual(self.a.starts, [])

    def test_join_rejects_invalid_ipv4_without_starting_a_worker(self):
        self.a.online_action("join")
        for address in ("", "example.test", "::1", "0.0.0.0", "224.0.0.1", "255.255.255.255",
                        "192.168.100.100suffix"):
            with self.subTest(address=address), mock.patch.object(self.a, "_direct_submit") as work:
                self.a.set_text_value("online_address", address)
                self.a.online_action("check")
                work.assert_not_called()
                self.assertEqual(self.a.online_state()["message"], "@t4.direct_invalid_address")

    def test_check_never_starts_game_and_enables_start_only_after_poll(self):
        with mock.patch.object(self.a, "_direct_preflight", return_value=self.verified()):
            self.a.online_action("check")
            self.assertEqual(self.a.online_state()["phase"], "checking")
            self.assertTrue(self.a.online_state()["busy"])
            self.assertEqual(self.a.starts, [])
            self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "checked")
        self.assertTrue(all(row["ok"] for row in self.a.online_state()["checks"]))

    def test_editing_address_or_role_invalidates_a_passed_check(self):
        for action in ("address", "join", "host"):
            with self.subTest(action=action):
                self.check()
                if action == "address":
                    self.a.set_text_value("online_address", "192.0.2.9")
                else:
                    self.a.online_action(action)
                self.a.online_action("start_match")
                self.assertIsNone(self.a._direct_verified)
                self.assertEqual(self.a.starts, [])

    def test_busy_and_playing_address_edits_are_ignored(self):
        self.a._direct_busy = True
        self.a.set_text_value("online_address", "192.0.2.9")
        self.assertEqual(self.a.text_value("online_address"), "")
        self.a._direct_busy = False
        self.play()
        self.a.set_text_value("online_address", "192.0.2.9")
        self.assertEqual(self.a.text_value("online_address"), "")

    def test_start_uses_checked_host_build_and_clears_inherited_session_values(self):
        self.play()
        env = self.a.starts[0]
        self.assertEqual(env["TEKKEN4_NET"], "host:7400")
        self.assertEqual(env["TEKKEN4_NET_BUILD"], "0123456789abcdef")
        for key in ("TEKKEN4_NET_BIND", "TEKKEN4_NET_PEER", "TEKKEN4_NET_KEY", "TEKKEN4_NET_SEED"):
            self.assertEqual(env[key], "")
        self.assertEqual(env["TEKKEN4_NET_TIMEOUT"], "90")

    def test_join_start_uses_the_address_entered_by_pad(self):
        self.a.online_action("join")
        self.a.set_text_value("online_address", "192.0.2.9")
        self.play()
        self.assertEqual(self.a.starts[0]["TEKKEN4_NET"], "join:192.0.2.9:7400")

    def test_old_check_or_changed_files_cannot_start_game(self):
        self.check()
        self.a._direct_verified["checked_at"] -= 61
        self.a.online_action("start_match")
        self.assertEqual(self.a.starts, [])
        self.check()
        self.stamps.side_effect = lambda p: (p, 2, 2)
        self.a.online_action("start_match")
        self.a.online_poll()
        self.assertEqual(self.a.starts, [])
        self.assertEqual(self.a.online_state()["message"], "@t4.direct_identity_failed")

    def test_disconnect_invalidates_a_queued_check_completion(self):
        with mock.patch.object(self.a, "_direct_preflight", return_value=self.verified()):
            self.a.online_action("check")
            cancel = self.a._direct_cancel
            self.a.online_action("disconnect")
            self.a.online_poll()
        self.assertTrue(cancel.is_set())
        self.assertEqual(self.a.online_state()["phase"], "offline")
        self.assertIsNone(self.a._direct_verified)

    def test_failed_comparisons_have_real_failure_values_and_preserve_owned_logs(self):
        error = DirectCheckError("@t4.direct_compiler_mismatch", dict(compiler=False), self.temp.name)
        with mock.patch.object(self.a, "_direct_preflight", side_effect=error):
            self.a.online_action("check")
            self.a.online_poll()
        row = next(row for row in self.a.online_state()["checks"] if row["id"] == "compiler")
        self.assertEqual(row["value"], "@t4.direct_compiler_mismatch")
        self.assertEqual(self.a._direct_last_run["run_dir"], self.temp.name)

    def test_raw_tool_errors_never_reach_the_view(self):
        with mock.patch.object(self.a, "_direct_preflight", side_effect=OSError("private endpoint and path")):
            self.a.online_action("check")
            self.a.online_poll()
        self.assertEqual(self.a.online_state()["message"], "@t4.direct_failed")
        self.assertNotIn("private", json.dumps(self.a.online_state()))

    def test_pad_stop_stops_only_the_owned_run_and_captures_logs(self):
        self.play()
        with mock.patch.object(self.a, "_direct_snapshot_logs") as capture:
            self.a.online_action("stop_match")
        capture.assert_called_once_with()
        self.assertEqual(self.a.exit_code, 0)
        self.assertEqual(self.a.online_state()["phase"], "offline")

    def test_game_exit_requires_fresh_checks(self):
        self.play()
        self.a.exit_code = 0
        self.a.online_poll()
        self.assertIsNone(self.a._direct_verified)
        self.a.online_action("start_match")
        self.assertEqual(len(self.a.starts), 1)

    def test_failed_exit_invalidates_checks_before_owned_logs_finish(self):
        self.play()
        run = self.a._online_owned_run
        pending = []

        def defer(work):
            pending.append(work)
            return SimpleNamespace(is_alive=lambda: bool(pending))

        with mock.patch.object(self.a, "_online_stop_submit", side_effect=defer), \
                mock.patch.object(self.a, "_direct_snapshot_logs") as capture:
            self.a.exit_code = 1
            self.a.online_poll()
            self.assertIsNone(self.a._direct_verified)
            self.assertIs(self.a._online_owned_run, run)
            self.assertEqual(self.a.online_state()["phase"], "stopping")
            self.assertTrue(self.a.online_state()["busy"])
            with mock.patch.object(self.a, "_direct_submit") as work:
                for action in ("check", "start_match", "collect_logs"):
                    self.a.online_action(action)
                work.assert_not_called()
            self.a.online_poll()
            self.assertEqual(len(pending), 1)
            capture.assert_not_called()
            pending.pop()()
            self.a.online_poll()
            capture.assert_called_once_with()
        self.assertIsNone(self.a._online_owned_run)
        self.assertEqual(self.a.online_state()["phase"], "offline")
        self.assertFalse(self.a.online_state()["busy"])
        self.a.online_action("start_match")
        self.assertEqual(len(self.a.starts), 1)

    def test_log_collector_receives_only_the_owned_folder(self):
        self.check()

        def collect(command, cancel):
            target = Path(command[command.index("-OutputDirectory") + 1], "T4-test-logs-fixture.zip")
            with zipfile.ZipFile(target, "x"):
                pass
            return 0

        with mock.patch.object(self.a, "_direct_user_folder", return_value=self.temp.name), \
                mock.patch.object(self.a, "_direct_process", side_effect=collect) as tool:
            self.a.online_action("collect_logs")
            self.a.online_poll()
        command = tool.call_args.args[0]
        self.assertTrue(command[command.index("-File") + 1].endswith("collect_test_logs.ps1"))
        self.assertEqual(command[command.index("-RunDir") + 1], self.temp.name)
        self.assertEqual(self.a.online_state()["message"], "@t4.direct_logs_saved")
        self.assertTrue(Path(self.a.online_state()["log_path"]).is_file())

    def test_player_report_destination_inside_checkout_is_refused(self):
        with mock.patch("openrecomp.adapters.t4_online.user_dir", return_value=self.temp.name):
            with self.assertRaises(RuntimeError):
                self.a._direct_user_folder()

    def test_checkout_never_supplies_runtime_log_sources(self):
        Path(self.temp.name, "net.log").write_text("NETSUMMARY fixture", encoding="utf-8")
        self.assertEqual(self.a._direct_log_stamps(), {})

    def test_preflight_delegates_all_checks_and_never_calls_game_tool(self):
        identity = dict(build_id="0123456789abcdef", compiler="MSVC fixture", iso_sha256="0" * 64,
                        elf_sha1="0" * 40, net="1", strict_hello="0", delay_match="0")
        report = dict(status="ok", local=identity, peer=identity, mismatch_fields=[])

        def run(command, cancel, env):
            self.assertNotIn("net_play.ps1", " ".join(command))
            self.assertNotIn("Start-Process", Path(command[command.index("-File") + 1]).read_text())
            self.assertEqual(env["TEKKEN4_NET_BIND"], "")
            output = command[command.index("-Output") + 1]
            Path(output).write_text(json.dumps(report), encoding="utf-8")
            return 0

        with mock.patch.object(self.a, "_direct_user_folder", return_value=self.temp.name), \
                mock.patch.object(self.a, "_direct_process", side_effect=run):
            result = self.a._direct_preflight("host", "", threading.Event())
        self.assertEqual(result["checks"], dict.fromkeys(DIRECT_CHECKS, True))
        self.assertIn("New-T4NetIdentity -BuildStampJson", PREFLIGHT_SCRIPT)
        self.assertIn("Invoke-T4NetPreflight", PREFLIGHT_SCRIPT)
        self.assertIn("Get-FileHash -LiteralPath $Elf -Algorithm SHA1", PREFLIGHT_SCRIPT)
        self.assertEqual(self.a.starts, [])

    def test_malformed_success_report_never_enables_start(self):
        identity = dict(build_id="0123456789abcdef", compiler="MSVC fixture", iso_sha256="0" * 64,
                        elf_sha1="0" * 40, net="1", strict_hello="0", delay_match="0")
        for peer, mismatch in (({}, []), (dict(identity, compiler="other"), []), (identity, ["build_id"])):
            with self.subTest(peer=peer, mismatch=mismatch):
                def run(command, cancel, env):
                    output = command[command.index("-Output") + 1]
                    Path(output).write_text(json.dumps(dict(status="ok", local=identity, peer=peer,
                                                           mismatch_fields=mismatch)), encoding="utf-8")
                    return 0
                with mock.patch.object(self.a, "_direct_user_folder", return_value=self.temp.name), \
                        mock.patch.object(self.a, "_direct_process", side_effect=run):
                    with self.assertRaisesRegex(DirectCheckError, "@t4.direct_identity_failed"):
                        self.a._direct_preflight("host", "", threading.Event())

    def test_stop_pending_blocks_logs_and_another_check_until_owned_game_is_reaped(self):
        self.play()
        pending = []

        def defer(work):
            pending.append(work)
            return SimpleNamespace(is_alive=lambda: bool(pending))

        with mock.patch.object(self.a, "_online_stop_submit", side_effect=defer):
            self.a.online_action("stop_match")
        self.assertEqual(self.a.online_state()["phase"], "stopping")
        self.assertTrue(self.a.online_state()["busy"])
        with mock.patch.object(self.a, "_direct_submit") as work:
            self.a.online_action("check")
            self.a.online_action("collect_logs")
            work.assert_not_called()
        self.a.exit_code = 0
        pending.pop()()
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "offline")
        self.assertFalse(self.a.online_state()["busy"])

    def test_runtime_snapshot_includes_only_this_owned_run_suffix(self):
        path = Path(self.temp.name, "net-source.fixture")
        path.write_bytes(b"old-line\nNETSUMMARY new-line\n")
        self.a._direct_last_run = dict(run_dir=self.temp.name)
        self.a._direct_log_baseline = {"net.log": (str(path), 9, 1, b"old-line\n")}
        self.stamps.side_effect = None
        self.stamps.return_value = (str(path), path.stat().st_size, 2)
        with mock.patch.object(self.a, "_direct_log_stamps", return_value={
                "net.log": (str(path), path.stat().st_size, 2, path.read_bytes())}):
            self.a._direct_snapshot_logs()
        self.assertEqual(Path(self.temp.name, "net.log").read_bytes(), b"NETSUMMARY new-line\n")

    def test_cancelling_preflight_terminates_the_tool_process(self):
        proc = mock.Mock()
        proc.poll.side_effect = [None, 0]
        proc.returncode = 0
        cancel = mock.Mock()
        cancel.is_set.return_value = False
        cancel.wait.return_value = True
        with mock.patch("openrecomp.adapters.t4_online.subprocess.Popen", return_value=proc):
            with self.assertRaisesRegex(RuntimeError, "@online.cancelled"):
                self.a._direct_process(["fake-tool"], cancel)
        proc.terminate.assert_called_once_with()
        proc.wait.assert_called_once_with(timeout=5)


if __name__ == "__main__":
    unittest.main()
