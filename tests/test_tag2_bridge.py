"""The TAG2 Core host (adapters/tag2_core.py + tag2_bridge/) and the launch contract.

These tests run the real host: Windows PowerShell compiles Tag2Bridge.cs against a stand-in Core
(tests/fixtures/tag2_stand_in_core.cs, our own file with the Core's public names). The stand-in's "service" is a
server on 127.0.0.1 in this process and its "game" is a sleeping Python. No TAG2 file, account or server is used.

The launch contract (the 96 argument / environment cases and the guards of the handover's tests/LaunchContract.cs)
runs on the adapter's launch path, the bridge's `start_info`. Set OPENRECOMP_TAG2_CORE to the Tag2.Launcher.Core.dll
of a TAG2 PC install to run the same cases against the published Core: it only constructs start settings in an
empty temporary root and never starts anything.
"""
import http.server
import itertools
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from openrecomp import __version__
from openrecomp.adapters import tag2_core
from openrecomp.adapters.tag2_core import Core, CoreError

FIXTURE = Path(__file__).with_name("fixtures") / "tag2_stand_in_core.cs"
WINDOWS = os.name == "nt" and os.path.isfile(tag2_core.powershell())
SECRET = "not-a-real-password-1"


class Service(http.server.BaseHTTPRequestHandler):
    seen = []           # (path, user agent, body)
    refuse = {}         # path -> HTTP status

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8")
        operation = self.path.rsplit("/", 1)[-1]
        Service.seen.append((operation, self.headers.get("User-Agent"), json.loads(body)))
        self.send_response(Service.refuse.get(operation, 200))
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *_args):
        pass


class HostedBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.shared.cleanup)
        cls.dll = os.path.join(cls.shared.name, tag2_core.CORE_FILE)
        build = subprocess.run(
            [tag2_core.powershell(), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
             "Add-Type -TypeDefinition ([IO.File]::ReadAllText($env:STAND_IN)) -ReferencedAssemblies "
             "System,System.Core,System.Net.Http,System.Web.Extensions -OutputAssembly $env:STAND_IN_DLL"],
            env=dict(os.environ, STAND_IN=str(FIXTURE), STAND_IN_DLL=cls.dll), capture_output=True, text=True)
        if build.returncode or not os.path.isfile(cls.dll):
            raise unittest.SkipTest("the stand-in Core could not be compiled: " + build.stderr[-300:])
        cls.digest = tag2_core.sha256_file(cls.dll)[0]
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Service)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.addClassCleanup(cls.server.server_close)
        cls.addClassCleanup(cls.server.shutdown)

    def setUp(self):
        Service.seen, Service.refuse = [], {}
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.join(self.tmp.name, "TAG2-PC")
        os.makedirs(os.path.join(self.root, "game"))
        with open(self.dll, "rb") as source, open(os.path.join(self.root, tag2_core.CORE_FILE), "wb") as target:
            target.write(source.read())
        with open(os.path.join(self.root, "never-executed.exe"), "w", encoding="ascii") as inert:
            inert.write("INERT TEST FILE; NEVER EXECUTE")
        sleeper = os.path.join(self.tmp.name, "sleeper.py")
        with open(sleeper, "w", encoding="ascii") as stream:
            stream.write("import time\ntime.sleep(120)\n")
        self.steer(service="http://127.0.0.1:%d/v1/" % self.server.server_address[1],
                   game_command=[sys.executable, "-I", sleeper])
        self.events = []
        self.core = Core(self.root, trusted={self.digest: "stand-in"}, cache=os.path.join(self.tmp.name, "cache"),
                         on_event=self.events.append)
        self.addCleanup(self.close)

    def steer(self, **values):
        self.steering = dict(getattr(self, "steering", {}), **values)
        with open(os.path.join(self.root, "stand-in.json"), "w", encoding="utf-8") as stream:
            json.dump(self.steering, stream)

    def close(self):
        if self.core.running():
            try:
                if self.core.call("stop", force=True, timeout=10).get("running"):
                    self.wait_event("game_exit")
            except CoreError:
                pass
        self.core.close()
        try:                                    # a "game" whose request failed after its start is nobody's: end it
            subprocess.run(["taskkill", "/F", "/PID", str(self.local("last-launch.json")["pid"])], capture_output=True)
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(0.3)                         # Windows lets go of the ended processes' folder

    def wait_event(self, kind, seconds=15):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if any(e.get("event") == kind for e in self.events):
                return
            time.sleep(0.05)
        self.fail("no %s event" % kind)

    def local(self, name):
        with open(os.path.join(self.root, "local", name), encoding="utf-8") as stream:
            return json.load(stream)


@unittest.skipUnless(WINDOWS, "the TAG2 Core host needs Windows PowerShell")
class Hosted(HostedBase):
    # ---------------------------------------------------------------- loading the Core
    def test_only_a_known_core_is_loaded_and_the_installs_file_stays_free(self):
        self.assertEqual(Core(self.root).problem(), "@tag2.core_unknown")        # the published list only
        with self.assertRaises(CoreError) as refused:
            Core(self.root).call("hello")
        self.assertEqual((refused.exception.kind, refused.exception.message), ("bridge", "@tag2.core_unknown"))
        self.assertEqual(self.core.call("hello")["protocol"], 3)
        os.replace(os.path.join(self.root, tag2_core.CORE_FILE), os.path.join(self.root, "moved.dll"))   # not held open
        self.assertEqual(self.core.call("hello")["build"], 16)
        self.assertEqual(Core(self.root).problem(), "@tag2.core_missing")

    def test_the_host_refuses_a_core_that_is_not_the_checked_one(self):
        self.core.call("hello")
        command = list(self.core.proc.args)
        command[command.index("-CoreSha256") + 1] = "0" * 64
        result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, timeout=120)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stdout, b"")

    # ---------------------------------------------------------------- account
    def test_sign_in_uses_our_user_agent_and_keeps_the_password_off_everything_but_the_pipe(self):
        answer = self.core.call("sign_in", name="Tester", password=SECRET)
        self.assertEqual((answer["has_account"], answer["name"]), (True, "Tester"))
        operation, agent, body = Service.seen[0]
        self.assertEqual(operation, "login")
        self.assertEqual(agent, f"OpenRecomp-FGC/{__version__} (tag2-pc)")
        self.assertEqual((body["product"], body["build"], body["protocol"]), ("tag2-pc", 16, 3))
        self.assertEqual(body["password"], SECRET)                           # it did arrive: through the Core
        self.assertNotIn(SECRET, " ".join(self.core.proc.args))
        self.assertNotIn(SECRET, self.core.stderr)
        self.assertNotIn(SECRET, json.dumps(answer) + json.dumps(self.events))
        self.assertEqual(self.core.call("register", name="Other", password=SECRET)["name"], "Other")
        self.assertEqual(Service.seen[1][0], "register")

    def test_a_refused_saved_sign_in_is_reported_once_as_sign_in_again(self):
        self.core.call("sign_in", name="Tester", password=SECRET)
        Service.refuse = {"session": 401}
        with self.assertRaises(CoreError) as refused:
            self.core.call("play", mode="online")
        self.assertEqual(refused.exception.kind, "sign_in")
        self.assertNotIn("Tester", refused.exception.message)
        time.sleep(1.5)
        self.assertEqual([s[0] for s in Service.seen], ["login", "session"])   # asked once; nothing retries
        self.assertFalse(self.core.call("game_status")["running"])
        Service.refuse = {"login": 403}
        with self.assertRaises(CoreError) as refused:
            self.core.call("sign_in", name="Tester", password=SECRET)
        self.assertEqual(refused.exception.kind, "error")                    # a wrong password is no "sign in again"
        self.assertNotIn(SECRET, refused.exception.message)

    def test_input_the_core_refuses_never_reaches_the_service(self):
        with self.assertRaises(CoreError) as refused:
            self.core.call("sign_in", name="Tester", password="short")
        self.assertEqual(refused.exception.kind, "input")
        self.assertEqual(Service.seen, [])

    # ---------------------------------------------------------------- the offline start path
    def test_offline_start_is_the_cores_own_launch_and_stop_ends_it(self):
        self.core.call("settings_set", values=dict(SkipStartupIntros=True, GraphicsBackend="vulkan"))
        call = self.core.request("play", mode="offline")
        game = call.wait(30)
        self.assertEqual(game["kind"], "offline")
        self.assertIn("offline", call.status.lower())                        # the Core's own progress line
        launch = self.local("last-launch.json")
        self.assertEqual((launch["online"], launch["ranked"], launch["offline_timing"]), (False, False, "1"))
        self.assertIn("--tag2_skip_startup_intros=true", launch["arguments"])
        self.assertIn("--gpu_backend=vulkan", launch["arguments"])
        self.assertNotIn("--tag2_launcher_ranked_start", launch["arguments"])
        self.assertEqual(Service.seen, [])                                   # offline asks no service
        status = self.core.call("game_status")
        self.assertEqual((status["running"], status["pid"], status["kind"]), (True, game["pid"], "offline"))
        with self.assertRaises(CoreError):
            self.core.call("play", mode="offline")                           # never a second game
        self.core.call("stop", force=True)
        self.wait_event("game_exit")
        self.assertFalse(self.core.call("game_status")["running"])

    def test_a_game_that_is_not_built_is_a_build_answer(self):
        self.steer(no_build=True)
        with self.assertRaises(CoreError) as refused:
            self.core.call("play", mode="offline")
        self.assertEqual(refused.exception.kind, "build")
        self.assertFalse(os.path.exists(os.path.join(self.root, "local", "last-launch.json")))

    def test_settings_are_validated_and_saved_by_the_core(self):
        saved = self.core.call("settings_set", values=dict(RenderScale=2))
        self.assertEqual(saved["RenderScale"], 2)
        with self.assertRaises(CoreError):
            self.core.call("settings_set", values=dict(RenderScale=7))
        with self.assertRaises(CoreError):
            self.core.call("settings_set", values=dict(PlayerName="x"))        # only the launch settings
        self.assertEqual(self.core.call("hello")["settings"]["RenderScale"], 2)
        self.assertEqual(self.local("launcher-settings.json")["RenderScale"], 2)

    # ---------------------------------------------------------------- Ranked (the stand-in's game and service only)
    def test_ranked_hands_the_team_and_only_offered_outfits_to_the_core(self):
        self.core.call("sign_in", name="Tester", password=SECRET)
        result = self.core.call("ranked", team=[9, 14], costumes=[2, 7])
        self.assertEqual((result["kind"], result["outcome"], result["started_game"]), ("ranked", "searching", True))
        self.assertEqual(result["team"], [dict(id=9, slots=[0, 2]), dict(id=14, slots=[0, 2])])
        self.assertEqual(self.local("last-ranked.json"), dict(team=[9, 14], costumes=[2, -1]))   # 7 was not offered
        launch = self.local("last-launch.json")
        self.assertEqual((launch["online"], launch["ranked"], launch["offline_timing"]), (True, True, "0"))
        again = self.core.call("ranked", team=[14, 9], costumes=[-1, 0])
        self.assertEqual((again["pid"], again["started_game"]), (result["pid"], False))   # the game we own, no second one
        self.assertEqual(self.core.call("progress")["ranked_wins"], "3")

    def test_a_ranked_request_can_be_taken_back(self):
        self.core.call("sign_in", name="Tester", password=SECRET)
        self.steer(ranked_wait=True)
        call = self.core.request("ranked", team=[9, 14], costumes=[-1, -1])
        deadline = time.time() + 20
        while "Ranked profile" not in call.status and time.time() < deadline:
            time.sleep(0.05)
        with self.assertRaises(CoreError):
            self.core.call("ranked", team=[9, 14])                           # one request at a time
        self.core.call("ranked_cancel")
        with self.assertRaises(CoreError) as cancelled:
            call.wait(20)
        self.assertEqual(cancelled.exception.kind, "cancelled")
        self.assertFalse(os.path.exists(os.path.join(self.root, "local", "last-ranked.json")))


def contract_cases():
    return list(itertools.product(("d3d12", "vulkan"), (1, 2, 3), (False, True), (False, True), (False, True), (False, True)))


class LaunchContract:
    """tests/LaunchContract.cs of the TAG2 0.16.33 handover, on the bridge's start_info."""

    def game(self, **more):
        return dict(dict(AppRoot=self.root, Entrypoint=os.path.join(self.root, "never-executed.exe"),
                         DataRoot=os.path.join(self.root, "game"), Build=16, Protocol=3), **more)

    def test_the_96_argument_and_environment_cases(self):
        inert = os.path.join(self.root, "never-executed.exe")
        passed = 0
        for backend, scale, vsync, grouped, online, ranked in contract_cases():
            with self.subTest(backend=backend, scale=scale, vsync=vsync, grouped=grouped, online=online, ranked=ranked):
                info = self.core.call("start_info", game=self.game(), online=online, ranked=ranked, settings=dict(
                    GraphicsBackend=backend, RenderScale=scale, PresentVSync=vsync, ReadbackDeferred=grouped,
                    SkipStartupIntros=True, Internal540p=False))
                command, low = info["arguments"], str
                self.assertIn("--tag2_skip_startup_intros=true", command)                            # intro flag
                self.assertEqual("--tag2_launcher_ranked_start=true" in command, ranked)             # ranked flag
                self.assertIn("--vsync=true", command)                                               # 60 Hz simulation
                self.assertIn("--readback_resolve_deferred=" + low(backend == "d3d12" and grouped).lower(), command)
                self.assertEqual(info["environment"]["TAG2_OFFLINE_TIMING"], "0" if online else "1")
                self.assertFalse(info["shell"])
                self.assertEqual(os.path.normcase(info["file"]), os.path.normcase(inert))            # argument ownership
                self.assertEqual(os.path.normcase(info["cwd"]), os.path.normcase(self.root))         # working directory
                if backend == "vulkan":
                    self.assertIn("--vulkan_allow_present_mode_immediate=" + low(not vsync).lower(), command)
                else:
                    self.assertIn("--d3d12_present_vsync=" + low(vsync).lower(), command)
                self.assertEqual(info["environment"]["TAG2_PC_LOW_LATENCY_INPUT"], "1")
                self.assertEqual(info["environment"]["REX_PC_NATIVE_ROLLBACK"], "1")
                passed += 1
        self.assertEqual(passed, 96)
        print("LAUNCH_CONTRACT cases=%d core=%s" % (passed, self.label), file=sys.stderr)

    def test_the_540p_guards(self):
        wanted = dict(RenderScale=1, Internal540p=True)
        with self.assertRaises(CoreError):
            self.core.call("start_info", game=self.game(Native540p=False), online=False, ranked=False, settings=wanted)
        info = self.core.call("start_info", game=self.game(Native540p=True), online=False, ranked=False, settings=wanted)
        self.assertIn("--tag2_internal_540p=true", info["arguments"])

    def test_constructing_start_settings_changes_no_saved_setting_and_starts_nothing(self):
        before = self.core.call("hello")["settings"]
        self.core.call("start_info", game=self.game(), online=True, ranked=True,
                       settings=dict(GraphicsBackend="vulkan", RenderScale=3))
        self.assertEqual(self.core.call("hello")["settings"], before)
        self.assertFalse(self.core.call("game_status")["running"])


@unittest.skipUnless(WINDOWS, "the TAG2 Core host needs Windows PowerShell")
class LaunchContractStandIn(LaunchContract, HostedBase):
    label = "stand-in"


@unittest.skipUnless(WINDOWS and os.environ.get("OPENRECOMP_TAG2_CORE"), "set OPENRECOMP_TAG2_CORE to a TAG2 PC install's Core")
class LaunchContractPublishedCore(LaunchContract, unittest.TestCase):
    """The same cases with the Core of a TAG2 PC install: it must be one of the published Cores the adapter loads.
    Having compiled against it also shows the current Ranked team API is there (PreviewRankedTeamAsync,
    BeginRankedTeamIntent and PlayRankedAsync's team selector are used by Tag2Bridge.cs)."""
    label = "published"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.join(self.tmp.name, "empty-root")
        os.makedirs(os.path.join(self.root, "game"))
        with open(os.environ["OPENRECOMP_TAG2_CORE"], "rb") as source, open(os.path.join(self.root, tag2_core.CORE_FILE), "wb") as target:
            target.write(source.read())
        with open(os.path.join(self.root, "never-executed.exe"), "w", encoding="ascii") as inert:
            inert.write("INERT TEST FILE; NEVER EXECUTE")
        self.core = Core(self.root, cache=os.path.join(self.tmp.name, "cache"))
        self.assertEqual(self.core.problem(), "")
        self.addCleanup(self.core.close)


if __name__ == "__main__":
    unittest.main()
