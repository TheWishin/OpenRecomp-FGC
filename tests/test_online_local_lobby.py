"""Real lobby protocol on loopback; no launcher window, game, or published server list.

The optional source checkout is read-only. Only build discovery and the game process
are replaced: the launcher's workers, installed client, server, NAT and match driver
all run normally. No protocol responses or events are fabricated.
"""
import asyncio
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from openrecomp.adapters.base import Adapter
from openrecomp.adapters.t5_match import T5Match
from openrecomp.nav import Game, Nav


REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO.parent / "OpenRecomp-work" / "T5DROnline-Source"
LOOPBACK = "127.0.0.1"


class LoopbackOnly:
    """Audit C-level socket calls too, including calls made by client threads.

    Audit hooks cannot be removed. The installed bound hook becomes inert after
    cleanup; keep it active until all of this test's threads have stopped.
    """
    def __init__(self):
        self.active = True
        self.violations = []
        self.addresses = []
        self.leaked = False

    def source_write(self, path):
        if isinstance(path, (str, bytes, os.PathLike)) and Path(os.fsdecode(path)).resolve().is_relative_to(SOURCE.resolve()):
            self.reject("local lobby attempted to change its read-only source checkout")

    def reject(self, reason):
        self.violations.append(reason)
        raise AssertionError(reason)

    def address(self, address):
        if not isinstance(address, tuple) or len(address) != 2 or address[0] != LOOPBACK:
            self.reject("local lobby attempted a non-127.0.0.1 address")
        self.addresses.append(address)

    def audit(self, event, args):
        if not self.active:
            return
        if event in ("socket.bind", "socket.connect", "socket.sendto", "socket.sendmsg"):
            address = args[0].getpeername() if event == "socket.sendmsg" and args[1] is None else args[1]
            self.address(address)
        elif event in ("socket.getaddrinfo", "socket.gethostbyname"):
            if args[0] != LOOPBACK:
                self.reject("local lobby attempted non-loopback name resolution")
        elif event in ("socket.gethostbyaddr", "socket.getnameinfo"):
            # Even a loopback argument can trigger an OS reverse-DNS query.
            self.reject("local lobby attempted reverse name resolution")
        elif event == "socket.gethostname":
            self.reject("local lobby attempted host discovery")
        elif event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            if os.path.basename(os.fsdecode(args[0])).casefold() == "servers.json":
                self.reject("local lobby attempted to read a real server list")
            mode, flags = args[1:3]
            if (mode and any(c in mode for c in "wax+")) or (flags and flags & (
                    os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
                self.source_write(args[0])
        elif event == "sqlite3.connect":
            self.source_write(args[0])
        elif event in ("os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.truncate", "os.utime"):
            self.source_write(args[0])
        elif event in ("os.rename", "os.link", "os.symlink"):
            self.source_write(args[0])
            self.source_write(args[1])
        elif event in ("subprocess.Popen", "os.system", "os.startfile", "os.posix_spawn"):
            self.reject("local lobby attempted to start a process")


class StubGame:
    """The only game handle the real match driver can obtain."""
    log_path = None
    proc = None

    def __init__(self):
        self.alive = True

    def running(self):
        return self.alive

    def stop(self):
        self.alive = False


class LoopbackGuardTests(unittest.TestCase):
    def test_socket_operations_require_literal_loopback(self):
        for event in ("socket.bind", "socket.connect", "socket.sendto", "socket.sendmsg"):
            for host in (LOOPBACK, "localhost", "0.0.0.0", "127.0.0.2", "::1", "example.invalid"):
                with self.subTest(event=event, host=host):
                    guard = LoopbackOnly()
                    args = (None, (host, 1234))
                    if host == LOOPBACK:
                        guard.audit(event, args)
                        self.assertEqual(guard.addresses, [(LOOPBACK, 1234)])
                    else:
                        with self.assertRaises(AssertionError):
                            guard.audit(event, args)
                        self.assertTrue(guard.violations)

    def test_dns_and_host_discovery_are_guarded(self):
        for event in ("socket.getaddrinfo", "socket.gethostbyname"):
            guard = LoopbackOnly()
            guard.audit(event, (LOOPBACK,))
            with self.assertRaises(AssertionError):
                guard.audit(event, ("localhost",))
        guard = LoopbackOnly()
        with self.assertRaises(AssertionError):
            guard.audit("socket.gethostbyaddr", (LOOPBACK,))
        with self.assertRaises(AssertionError):
            guard.audit("socket.getnameinfo", ((LOOPBACK, 1234),))
        with self.assertRaises(AssertionError):
            guard.audit("socket.getnameinfo", (("::1", 1234),))
        with self.assertRaises(AssertionError):
            guard.audit("socket.gethostname", ())

    def test_server_lists_and_source_mutations_are_blocked(self):
        for path in (str(SOURCE / "lobby" / "servers.json"),
                     bytes(str(SOURCE / "lobby" / "servers.json"), "utf-8"),
                     SOURCE / "lobby" / "servers.json"):
            with self.subTest(path_type=type(path).__name__), self.assertRaises(AssertionError):
                LoopbackOnly().audit("open", (path, "r", 0))
        path = str(SOURCE / "guard-fixture")
        events = [("open", (path, "w", os.O_WRONLY)),
                  ("sqlite3.connect", (path,)), ("os.mkdir", (path,)),
                  ("os.remove", (path,)), ("os.rmdir", (path,)),
                  ("os.chmod", (path,)), ("os.truncate", (path,)), ("os.utime", (path,)),
                  ("os.rename", ("fixture", path)), ("os.rename", (path, "fixture")),
                  ("os.link", ("fixture", path)), ("os.symlink", ("fixture", path)),
                  ("subprocess.Popen", ()), ("os.system", ()),
                  ("os.startfile", ()), ("os.posix_spawn", ())]
        for event, args in events:
            with self.subTest(event=event), self.assertRaises(AssertionError):
                LoopbackOnly().audit(event, args)

    def test_guard_is_inert_after_cleanup(self):
        guard = LoopbackOnly()
        guard.active = False
        guard.audit("socket.connect", (None, ("example.invalid", 1234)))
        guard.audit("open", (SOURCE / "lobby" / "servers.json", "r", 0))
        self.assertEqual(guard.violations, [])


class LocalAdapter(T5Match, Adapter):
    online_legacy_config = False

    def __init__(self, directory, build):
        super().__init__(dict(id="local", short="Local", title="Local lobby", accent="#112233",
                              sections=["online"]))
        self.root = str(SOURCE)
        self.directory = str(directory)
        self.build = build
        self.s = {}
        self.game = None
        self.starts = []

    def online_cfg_path(self):
        return os.path.join(self.directory, "online.json")

    def _online_out_dir(self):
        return self.directory

    def _online_build(self, api):
        # No game data or generated game files are needed for protocol identity.
        return self.build

    def _online_client_options(self):
        return dict(super()._online_client_options(), request_timeout=3, relays=False,
                    test_inbound="", handover="port")

    def text_value(self, tid):
        return self.online_text_value(tid)

    def set_text_value(self, tid, value):
        self.set_online_text_value(tid, value)

    def ready(self):
        return True

    def chosen_fighter(self):
        return "random"

    def running(self):
        return self.game is not None and self.game.running()

    def start(self, extra_env=None):
        self.starts.append(dict(extra_env or {}))
        self.game = StubGame()


class LocalLobbyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_dir():
            raise unittest.SkipTest("real lobby source checkout missing: " + str(SOURCE))
        # A present but incompatible checkout is a failure, not an optional skip.
        cls.resources = unittest.TestCase()
        cls.guard = LoopbackOnly()
        # Fail closed if a runtime worker ever outlives teardown: restoring the
        # environment or removing protection while it can still run is unsafe.
        cls.addClassCleanup(lambda: None if cls.guard.leaked else cls.resources.doCleanups())
        sys.addaudithook(cls.guard.audit)
        cls.resources.addCleanup(setattr, cls.guard, "active", False)
        old_path = sys.path[:]
        old_modules = {k: v for k, v in sys.modules.items()
                       if k == "t5lobby" or k.startswith("t5lobby.")}

        def restore_imports():
            sys.path[:] = old_path
            for name in tuple(sys.modules):
                if name == "t5lobby" or name.startswith("t5lobby."):
                    del sys.modules[name]
            sys.modules.update(old_modules)

        cls.resources.addCleanup(restore_imports)
        cls.resources.addCleanup(setattr, sys, "dont_write_bytecode", sys.dont_write_bytecode)
        sys.dont_write_bytecode = True
        for name in old_modules:
            del sys.modules[name]
        sys.path.insert(0, str(SOURCE / "lobby"))
        env = mock.patch.dict(os.environ, T5_NET_BIND=LOOPBACK, T5_PORTMAP="0",
                              T5_NET_TEST_INBOUND="", T5_RELAY_PUMP="0")
        env.start()
        cls.resources.addCleanup(env.stop)
        cls.proto = importlib.import_module("t5lobby.proto")
        cls.server_module = importlib.import_module("t5lobby.server")
        cls.client_module = importlib.import_module("t5lobby.client")
        cls.build_module = importlib.import_module("t5lobby.buildid")
        cls.servers = importlib.import_module("t5lobby.servers")
        cls.driver_module = importlib.import_module("t5lobby.match_driver")
        for module in (cls.proto, cls.server_module, cls.client_module, cls.build_module,
                       cls.servers, cls.driver_module):
            if not Path(module.__file__).resolve().is_relative_to((SOURCE / "lobby").resolve()):
                raise AssertionError("real lobby module loaded from another checkout")
        # Keep real resolve/ServerEntry/client_kwargs; bypass only catalog discovery.
        for patch in (mock.patch.object(cls.servers, "load", return_value=([], [])),
                      mock.patch.object(cls.servers, "load_file", side_effect=AssertionError("server list read")),
                      mock.patch.object(cls.driver_module, "game_files", return_value=()),
                      mock.patch("openrecomp.adapters.t5_online.game_process_running", return_value=False)):
            patch.start()
            cls.resources.addCleanup(patch.stop)

    def setUp(self):
        self.assertEqual(self.guard.violations, [])
        directory = tempfile.TemporaryDirectory(prefix="local-lobby-", dir=REPO)
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.baseline_threads = set(threading.enumerate())
        self.adapters = []
        self.clients = []
        self.navs = []
        self.loop = self.proto.new_event_loop()
        self.server = None
        self.start_error = None
        self.shutdown_requested = threading.Event()
        ready = threading.Event()
        cfg = self.server_module.Config(
            host=LOOPBACK, port=0, udp_port=0, udp_port2=-1,
            db=str(self.directory / "lobby.db"), status_port=0, relays="",
            scrypt_n=1 << 10, blind_ready=True, min_match_seconds=0,
            max_match_seconds=0, pair_cooldown=0, ranked_same_ip=True,
            ready_timeout=20, register_timeout=4, punch_timeout=1.5,
            relay_timeout=5, result_timeout=3, invite_retry_seconds=0,
            lobby_interval=0.02, log_level="WARNING")

        def serve():
            asyncio.set_event_loop(self.loop)
            try:
                self.server = self.server_module.LobbyServer(cfg)
                self.loop.run_until_complete(self.server.start())
            except BaseException as exc:
                self.start_error = exc
            finally:
                ready.set()
            if self.start_error is None and not self.shutdown_requested.is_set():
                self.loop.run_forever()

        self.server_thread = threading.Thread(target=serve, name="local-lobby-server", daemon=True)
        self.addCleanup(self.shutdown)
        self.server_thread.start()
        self.assertTrue(ready.wait(10), "local lobby server did not start")
        if self.start_error is not None:
            raise self.start_error
        self.assertEqual(cfg.host, LOOPBACK)
        self.assertGreater(self.server.port, 0)
        self.assertGreater(self.server.udp.port, 0)
        self.address = LOOPBACK + ":" + str(self.server.port)
        build = self.build_module.BuildInfo("0" * 40, "local-protocol-fixture", "test")
        for index in range(2):
            out = self.directory / str(index)
            out.mkdir()
            adapter = LocalAdapter(out, build)
            adapter.set_text_value("online_server", self.address)
            nav = Nav([Game(adapter.m, adapter)], language="en")
            nav.screen = "hub"
            nav.sec[adapter.m["id"]] = "online"
            self.adapters.append(adapter)
            self.navs.append(nav)

    def shutdown(self):
        errors = []
        self.shutdown_requested.set()
        for adapter in self.adapters:
            client = getattr(adapter, "_online_client", None)
            if client is not None:
                self.clients.append(client)
            try:
                adapter.online_close()
            except Exception as exc:
                errors.append("adapter close: " + type(exc).__name__)
        # online_close delegates client closure to a worker. Let that one owner
        # finish before making any idempotent fallback close call ourselves.
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            closers = [t for t in threading.enumerate() if t not in self.baseline_threads
                       and t.name.startswith("openrecomp-")]
            if not closers:
                break
            for thread in closers:
                thread.join(0.02)
        # Close retained clients as well, including a displaced/cancelled session.
        # This is idempotent and finishes transports before stopping the server.
        for client in self.clients:
            if closers:
                break
            try:
                client.close()
            except Exception as exc:
                errors.append("client close: " + type(exc).__name__)
        stopped = False
        try:
            if self.loop.is_running() and self.server is not None and self.start_error is None:
                asyncio.run_coroutine_threadsafe(self.server.stop(), self.loop).result(10)
                stopped = True
        except Exception as exc:
            errors.append("server stop: " + type(exc).__name__)
        finally:
            if self.loop.is_running():
                self.loop.call_soon_threadsafe(self.loop.stop)
            self.server_thread.join(10)
        if self.server_thread.is_alive():
            errors.append("local server thread leaked")
        else:
            try:
                # start() can fail after opening SQLite or binding some sockets.
                if self.server is not None and not stopped:
                    self.loop.run_until_complete(asyncio.wait_for(self.server.stop(), 10))
                async def drain():
                    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                self.loop.run_until_complete(asyncio.wait_for(drain(), 5))
                self.loop.run_until_complete(asyncio.wait_for(self.loop.shutdown_asyncgens(), 5))
                self.loop.run_until_complete(self.loop.shutdown_default_executor(timeout=5))
            except Exception as exc:
                errors.append("server loop cleanup: " + type(exc).__name__)
            finally:
                self.loop.close()
        # Include the native driver's anonymous async-call threads and asyncio
        # executors, not just the launcher's named worker threads.
        deadline = time.monotonic() + 10
        workers = []
        while time.monotonic() < deadline:
            workers = [t for t in threading.enumerate() if t not in self.baseline_threads]
            if not workers:
                break
            for thread in workers:
                thread.join(0.02)
        if workers:
            self.guard.leaked = True
            errors.append("local lobby runtime threads leaked; isolation guard remains active")
        self.assertEqual(errors, [])
        self.assertEqual(self.guard.violations, [])
        self.assertTrue(self.guard.addresses)
        self.assertTrue(all(address[0] == LOOPBACK for address in self.guard.addresses))

    def wait(self, predicate, description, timeout=12):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for nav in self.navs:
                nav.poll_online()
                self.assertNotEqual(nav.toast, "@online.failure", "Nav swallowed a lobby failure")
            self.assertEqual(self.guard.violations, [])
            if predicate():
                return
            time.sleep(0.01)
        states = [(a.online_state()["phase"], a.online_state()["message"]) for a in self.adapters]
        self.fail(description + "; phase/message: " + repr(states))

    def state(self, index):
        return self.adapters[index].online_state()

    def choose(self, index, iid):
        adapter, nav = self.adapters[index], self.navs[index]
        self.wait(lambda: not adapter._online_busy, "adapter worker did not finish")
        # Use controller actions to select every requested network operation.
        for _ in range(200):
            items = nav.items()
            target = next((i for i, item in enumerate(items) if item.get("id") == iid), None)
            self.assertIsNotNone(target, "missing controller action: " + iid)
            focus = nav.focus_index(items)
            if focus == target:
                nav.act("confirm", device="xbox")
                self.assertNotEqual(nav.toast, "@online.failure")
                return
            nav.act("down" if focus < target else "up", device="xbox")
        self.fail("controller could not reach " + iid)

    def login(self, index, name, action="login_guest"):
        adapter = self.adapters[index]
        adapter.set_text_value("online_name", name)
        if action != "login_guest":
            adapter.set_text_value("online_password", "local-test-password")
        self.choose(index, action)
        self.wait(lambda: self.state(index)["phase"] == "logged_in", "login did not complete")
        client = adapter._online_client
        self.clients.append(client)
        self.assertIsInstance(client, self.client_module.LobbyClient)
        self.assertEqual(client.host, LOOPBACK)
        self.assertEqual(client.port, self.server.port)
        self.assertEqual(client.reconnect_window, 0)
        self.assertEqual(client._writer.get_extra_info("peername")[0], LOOPBACK)
        self.assertEqual(self.state(index)["account"], action != "login_guest")
        if action == "login_register":
            self.assertTrue(self.state(index)["recovery_codes"])
            self.choose(index, "acknowledge_recovery")
            self.assertEqual(self.state(index)["recovery_codes"], [])
        return client

    def both(self, phase):
        return all(self.state(i)["phase"] == phase for i in range(2))

    def test_guest_search_cancel_and_second_login_kick(self):
        self.login(0, "GuestLocal")
        self.choose(0, "search_casual")
        self.wait(lambda: self.state(0)["phase"] == "searching", "quick search did not start")
        first = self.adapters[0]._online_client
        self.choose(0, "cancel")
        self.wait(lambda: self.state(0)["phase"] == "offline" and not first.connected,
                  "cancel did not disconnect")
        self.assertIsNone(self.adapters[0]._online_client)
        self.assertFalse(first.connected)
        self.login(0, "AccountLocal", "login_register")
        self.choose(0, "logout")
        self.login(0, "AccountLocal", "login_account")
        displaced = self.adapters[0]._online_client
        self.login(1, "AccountLocal", "login_account")
        self.wait(lambda: self.state(0)["phase"] == "kicked", "second account login did not kick first")
        self.assertEqual(self.state(0)["message"], "@online.kicked")
        self.assertIsNone(self.adapters[0]._online_client)
        # Poll over several server/client ticks: no automatic saved-session login.
        until = time.monotonic() + 0.4
        self.wait(lambda: time.monotonic() >= until, "kick observation interval")
        self.assertEqual(self.state(0)["phase"], "kicked")
        self.assertFalse(displaced.connected)
        self.assertEqual(self.state(1)["phase"], "logged_in")

    def test_quick_match_ready_result_and_rematch(self):
        self.login(0, "QuickOne")
        self.login(1, "QuickTwo")
        self.choose(0, "search_casual")
        self.wait(lambda: self.state(0)["phase"] == "searching", "first client did not queue")
        self.choose(1, "search_casual")
        self.wait(lambda: self.both("matched"), "real quick match not found")
        mid = self.adapters[0]._online_match_id
        self.assertEqual(mid, self.adapters[1]._online_match_id)
        self.assertTrue(all(a._online_ready_check for a in self.adapters))
        self.assertTrue(all(not a.starts for a in self.adapters))
        self.navs[0].dry = True
        self.choose(0, "start_match")
        self.assertEqual(self.state(0)["phase"], "matched")
        self.assertFalse(self.adapters[0]._online_authorized)
        self.assertFalse(self.adapters[0].starts)
        self.navs[0].dry = False
        self.choose(0, "start_match")
        self.wait(lambda: self.state(0)["phase"] == "starting" and not self.adapters[0]._online_busy,
                  "first ready request did not finish")
        self.assertEqual(self.state(1)["phase"], "matched")
        self.assertTrue(all(not a.starts for a in self.adapters))
        self.choose(1, "start_match")
        self.wait(lambda: self.both("playing"), "ready/NAT/stub launch did not complete", timeout=20)
        for adapter in self.adapters:
            self.assertEqual(len(adapter.starts), 1)
            self.assertIsInstance(adapter.game, StubGame)
            self.assertIsInstance(adapter._online_driver, self.driver_module.MatchDriver)
            self.assertEqual(adapter.starts[0]["T5_NET_MATCH"], mid)
            # The stub supplies a result through the game's documented file boundary.
            with open(adapter._online_driver.result_path, "w", encoding="utf-8") as stream:
                json.dump(dict(winner=0, score=[3, 1], match=mid, desync=0), stream)
        self.wait(lambda: self.both("result_sent") and all(
            self.state(i)["message"] == "@online.result_confirmed" for i in range(2)),
            "real server did not confirm both game reports")
        self.assertTrue(all(a._online_driver.history[-1][1]["source"] == "game" for a in self.adapters))
        self.assertTrue(all(self.state(i)["capabilities"]["rematch"] for i in range(2)))
        self.choose(0, "rematch")
        self.choose(1, "rematch")
        self.wait(lambda: self.both("playing") and all(a._online_match_id != mid for a in self.adapters),
                  "real rematch did not launch the stub", timeout=20)
        self.assertEqual(self.adapters[0]._online_match_id, self.adapters[1]._online_match_id)
        self.assertTrue(all(len(a.starts) == 2 for a in self.adapters))

    def test_rooms_password_and_invite_code(self):
        self.login(0, "CodeOne")
        self.login(1, "CodeTwo")
        self.choose(0, "create_room")
        self.wait(lambda: bool(self.state(0)["room"]), "public room not created")
        self.choose(0, "leave_room")
        self.wait(lambda: not self.state(0)["room"], "public room not left")
        self.adapters[0].set_text_value("online_room_name", "Local locked room")
        self.adapters[0].set_text_value("online_room_password", "local-room-password")
        self.choose(0, "create_password_room")
        self.wait(lambda: self.state(0)["room"].get("lock") == "password", "password room not created")
        rid = self.state(0)["room"]["id"]
        self.assertEqual(self.adapters[0].text_value("online_room_password"), "")
        self.assertNotIn("local-room-password", str(self.state(0)))
        self.choose(1, "refresh_rooms")
        self.wait(lambda: any(r["id"] == rid for r in self.state(1)["rooms"]), "password room not listed")
        listed = next(r for r in self.state(1)["rooms"] if r["id"] == rid)
        self.assertEqual(listed["name"], "Local locked room")
        self.assertEqual(listed["lock"], "password")
        self.adapters[1].set_text_value("online_room_password", "local-room-password")
        self.choose(1, "join_room:" + rid)
        self.wait(lambda: self.both("matched"), "password join did not create a match")
        self.assertTrue(all(not a.starts for a in self.adapters))
        # Cancel closes both sessions without accepting a ready check.
        self.choose(0, "cancel_match")
        self.wait(lambda: self.state(1)["phase"] == "offline", "peer did not observe cancelled room match")
        self.login(0, "RoomOne")
        self.login(1, "RoomTwo")
        self.choose(0, "create_code_room")
        self.wait(lambda: bool(self.state(0)["room"].get("code")), "invite code not returned")
        code = self.state(0)["room"]["code"]
        self.assertEqual(self.state(0)["room"]["lock"], "code")
        self.assertRegex(code, r"^[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}$")
        self.choose(1, "refresh_rooms")
        self.wait(lambda: not self.adapters[1]._online_busy, "code room refresh incomplete")
        self.assertNotIn(code, str(self.state(1)["rooms"]))
        self.adapters[1].set_text_value("online_room_code", code)
        self.choose(1, "join_room_code")
        self.wait(lambda: self.both("matched"), "invite code join did not create a match")
        self.assertEqual(self.state(0)["room"]["id"], self.state(1)["room"]["id"])
        self.assertEqual(self.state(1)["room"]["code"], code)
        self.assertTrue(all(not a.starts for a in self.adapters))

    def test_chat_friends_and_challenge(self):
        self.login(0, "SocialOne", "login_register")
        self.login(1, "SocialTwo", "login_register")
        self.adapters[0].set_text_value("online_chat", "hello local lobby")
        self.choose(0, "send_chat")
        self.wait(lambda: all(any(line == dict(name="SocialOne", text="hello local lobby")
                                  for line in self.state(i)["chat"]) for i in range(2)),
                  "server chat echo did not reach both adapters")
        self.adapters[0].set_text_value("online_friend_name", "SocialTwo")
        self.choose(0, "add_friend")
        self.wait(lambda: bool(self.state(0)["friend_outgoing"]) and bool(self.state(1)["friend_incoming"]),
                  "friend request not delivered")
        self.choose(1, "accept_friend:SocialOne")
        self.wait(lambda: all(bool(self.state(i)["friends"]) for i in range(2)), "friend acceptance not delivered")
        self.choose(0, "refresh_friends")
        self.wait(lambda: not self.adapters[0]._online_busy, "friends refresh incomplete")
        self.assertEqual(self.state(0)["friends"][0]["name"], "SocialTwo")
        self.assertEqual(self.state(1)["friends"][0]["name"], "SocialOne")
        self.choose(0, "refresh_players")
        self.wait(lambda: any(p["name"] == "SocialTwo" for p in self.state(0)["players"]), "peer not listed")
        peer = next(p["id"] for p in self.state(0)["players"] if p["name"] == "SocialTwo")
        self.choose(0, "challenge:" + peer)
        self.wait(lambda: bool(self.state(1)["challenge"]), "challenge not delivered")
        self.assertEqual(self.state(1)["challenge"]["name"], "SocialOne")
        self.choose(1, "accept_challenge")
        self.wait(lambda: self.both("matched"), "accepted challenge not matched")
        self.assertTrue(all(not a._online_ready_check for a in self.adapters))
        # An accepted native challenge may already have a ticket; local pad consent
        # still has to precede starting even the inert game.
        until = time.monotonic() + 0.2
        self.wait(lambda: time.monotonic() >= until, "challenge observation interval")
        self.assertTrue(all(not a.starts for a in self.adapters))


if __name__ == "__main__":
    unittest.main()
