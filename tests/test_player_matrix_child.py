"""Safety guards are exercised with synthetic audit events and fake process spawns."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

from tools import player_matrix_child as child


class LocalOnly(unittest.TestCase):
    def test_only_loopback_socket_addresses_are_allowed(self):
        for address in (("127.0.0.1", 1), ("::1", 1), ("127.4.3.2", 1)):
            with self.subTest(address=address):
                self.assertTrue(child.local_address(address))
        for address in (("192.0.2.1", 1), ("0.0.0.0", 1), ("example.invalid", 1), "127.0.0.1", None, ()):
            with self.subTest(address=address):
                self.assertFalse(child.local_address(address))

    def test_external_dns_names_are_not_allowed(self):
        for host in ("127.0.0.1", "::1", "localhost", b"localhost", b"127.0.0.1"):
            with self.subTest(host=host):
                self.assertTrue(child.local_host(host))
        for host in ("example.invalid", "192.0.2.1", "0.0.0.0", None):
            with self.subTest(host=host):
                self.assertFalse(child.local_host(host))


class SeededKeys(unittest.TestCase):
    def test_keys_are_copied_into_the_case_once_and_the_source_is_left_alone(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            folder = Path(folder)
            source, root = folder / "owner.keys", folder / "game"
            source.write_bytes(b"inert key data")
            self.assertFalse(child.seed_keys({}, root))
            self.assertFalse(child.seed_keys({"t5dr_keys": str(source)}, ""))
            self.assertTrue(child.seed_keys({"t5dr_keys": str(source)}, root))
            target = root / "native" / "keys" / "ps3.keys"
            self.assertEqual(target.read_bytes(), b"inert key data")
            target.write_bytes(b"built by the game")
            self.assertTrue(child.seed_keys({"t5dr_keys": str(source)}, root))
            self.assertEqual(target.read_bytes(), b"built by the game")
            self.assertEqual(source.read_bytes(), b"inert key data")


class ProcessGuards(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory(dir=Path(__file__).parent)))
        self.events = str(self.folder / "events.jsonl")
        self.spawn = self.enterContext(mock.patch.object(child.subprocess, "Popen"))
        # Capture the guard instead of installing an irreversible audit hook into
        # unittest itself. No socket, child process, shell or game is started.
        self.audit_hook = self.enterContext(mock.patch.object(child.sys, "addaudithook"))

    def guard(self, **kwargs):
        child.safety(self.events, **kwargs)
        return self.audit_hook.call_args.args[0]

    def test_shell_and_installer_processes_are_refused_before_spawn(self):
        self.guard()
        for command in ("cmd /c fake", ["cmd.exe", "/c", "fake"], ["powershell.exe", "-File", "fake.ps1"],
                        ["winget.exe", "install", "fake"], ["git.exe", "clone", "fake"], ["curl.exe", "fake"]):
            with self.subTest(command=command), self.assertRaises(PermissionError):
                subprocess.Popen(command)
        with self.assertRaises(PermissionError):
            subprocess.Popen(["python.exe", "--version"], shell=True)
        self.spawn.assert_not_called()

    def test_game_python_worker_preserves_interpreter_and_arguments(self):
        python = str(self.folder / "game" / "python" / "python.exe")
        self.guard(expected_python=lambda: python)
        subprocess.Popen([python, "tools/build_game.py", "--source", "private-input"], cwd=str(self.folder))
        command = self.spawn.call_args.args[0]
        self.assertEqual(command[0], python)
        self.assertIn("--build-worker", command)
        self.assertEqual(command[command.index("--") + 1:], ["tools/build_game.py", "--source", "private-input"])
        self.assertEqual(self.spawn.call_args.kwargs["cwd"], str(self.folder))
        if os.name == "nt":
            flags = self.spawn.call_args.kwargs["creationflags"]
            self.assertEqual(flags & subprocess.CREATE_NO_WINDOW, subprocess.CREATE_NO_WINDOW)
            self.assertEqual(flags & subprocess.BELOW_NORMAL_PRIORITY_CLASS, subprocess.BELOW_NORMAL_PRIORITY_CLASS)

    def test_foreign_python_is_rejected_before_spawning(self):
        self.guard(expected_python=lambda: str(self.folder / "game/python/python.exe"))
        with self.assertRaisesRegex(PermissionError, "outside the game's own"):
            subprocess.Popen([str(self.folder / "foreign/python.exe"), "inert.py"])
        self.spawn.assert_not_called()
        self.assertTrue(any(row["kind"] == "foreign_python" for row in child.read_events(self.events)))

    def test_crypto_probe_is_exact_and_is_not_converted_into_a_build(self):
        self.guard()
        command = [str(self.folder / "python.exe"), "-I", "-c", "from Crypto.Cipher import AES"]
        subprocess.Popen(command)
        self.assertEqual(self.spawn.call_args.args[0], command)

    def test_compile_boundary_stops_before_spawning_compiler(self):
        self.guard(worker=True)
        for exe in ("cl.exe", "cmake.exe", "ninja.exe", "clang.exe", "msbuild.exe"):
            with self.subTest(exe=exe), self.assertRaises(child.BoundaryStop):
                subprocess.Popen([exe, "inert-compile-input"])
        self.spawn.assert_not_called()
        self.assertTrue(any(row["kind"] == "compile_boundary" for row in child.read_events(self.events)))

    def test_full_mode_refuses_unauditable_native_compile_and_network_tools(self):
        self.guard(worker=True, full=True)
        with self.assertRaisesRegex(PermissionError, "offline process sandbox"):
            subprocess.Popen(["cl.exe", "inert-compile-input"])
        self.spawn.assert_not_called()
        with self.assertRaises(PermissionError):
            subprocess.Popen(["curl.exe", "example.invalid"])

    def test_version_argument_cannot_disguise_a_python_build(self):
        self.guard(expected_python=lambda: str(self.folder / "game/python/python.exe"))
        with self.assertRaises(PermissionError):
            subprocess.Popen([str(self.folder / "foreign/python.exe"), "-c", "pass", "--version"])
        self.spawn.assert_not_called()

    def test_unknown_worker_process_cannot_escape_guard(self):
        self.guard(worker=True)
        with self.assertRaises(PermissionError):
            subprocess.Popen(["unknown-tool.exe", "inert-input"])
        self.spawn.assert_not_called()

    def test_extra_roots_widen_the_writable_area_to_the_named_folders_only(self):
        case, other = self.folder / "case" / "profile", self.folder / "case" / "game copy"
        child.safety(str(case / "events.jsonl"), extra_roots=[other])
        audit = self.audit_hook.call_args.args[0]
        audit("open", (str(case / "settings.json"), "w", os.O_WRONLY | os.O_CREAT))
        audit("open", (str(other / "native" / "build.log"), "w", os.O_WRONLY | os.O_CREAT))
        for outside in (self.folder / "case" / "elsewhere.txt", self.folder / "other-case" / "game copy" / "x"):
            with self.subTest(outside=outside.name), self.assertRaises(PermissionError):
                audit("open", (str(outside), "w", os.O_WRONLY))

    def test_audit_blocks_direct_shell_bypasses_and_external_network_events(self):
        audit = self.guard()
        for name, args in (("os.system", ("fake",)), ("os.spawn", ("fake",)),
                           ("os.exec", ("fake",)), ("os.posix_spawn", ("fake",)),
                           ("socket.connect", (None, ("192.0.2.1", 1))),
                           ("socket.sendto", (None, b"inert", ("192.0.2.1", 1))),
                           ("socket.getaddrinfo", ("example.invalid", 1)),
                           ("subprocess.Popen", ("cmd.exe", ["cmd.exe", "/c", "fake"], None, None))):
            with self.subTest(event=name), self.assertRaises(PermissionError):
                audit(name, args)
        audit("socket.connect", (None, ("127.0.0.1", 1)))
        audit("socket.getaddrinfo", ("localhost", 1))
        self.spawn.assert_not_called()


    def test_null_device_writes_stay_allowed_but_other_writes_outside_the_case_do_not(self):
        # subprocess.DEVNULL opens os.devnull read-write: the launcher's own Python probe
        # (stdin/stdout=DEVNULL) failed with PermissionError and read as a damaged install.
        audit = self.guard()
        for name in (os.devnull, "nul", "NUL"):
            with self.subTest(device=name):
                audit("open", (name, "r+", os.O_RDWR))
        with self.assertRaises(PermissionError):
            audit("open", (str(Path(tempfile.gettempdir()) / "outside-case.txt"), "w", os.O_WRONLY))
        audit("open", (str(self.folder / "inside.txt"), "w", os.O_WRONLY | os.O_CREAT))


class NativeAudit(unittest.TestCase):
    def test_guard_accepts_native_windows_command_and_denies_unwrapped_alias(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            script = textwrap.dedent("""
                import json
                import socket
                import subprocess
                import sys
                from tools import player_matrix_child as child

                events = sys.argv[1]
                original = subprocess.Popen
                child.safety(events)
                # CPython emits a native command string at audit time on Windows.
                # This benign version query must survive the guarded approval.
                result = subprocess.run([sys.executable, '--version'], capture_output=True, text=True, timeout=5)
                assert result.returncode == 0, result
                assert 'Python ' in result.stdout + result.stderr
                for command in ([sys.executable, '--version'],
                                [sys.executable, '-c', 'raise AssertionError("must not execute")']):
                    try:
                        original(command)
                    except PermissionError:
                        pass
                    else:
                        raise AssertionError('An original Popen alias bypassed the guard')
                try:
                    socket.getaddrinfo('matrix-no-network.invalid', 1)
                except PermissionError:
                    pass
                else:
                    raise AssertionError('External DNS lookup escaped the guard')
                records = child.read_events(events)
                assert any(r['kind'] == 'unsafe_process' for r in records)
                assert any(r['kind'] == 'network_denied' for r in records)
                print('NATIVE_AUDIT_OK')
            """)
            events = str(Path(folder) / "audit.jsonl")
            result = subprocess.run([sys.executable, "-B", "-c", script, events],
                                    cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("NATIVE_AUDIT_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
