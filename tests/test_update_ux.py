"""Update UX (owner: "when I click it does not stop, make the UX better"): progress, cancel, no double start, end messages.

Both flows: the launcher's own update (updater.stage_update + UpdateService + the update window) and the games'
install/update (game_releases + GameSetup + the setup window). Everything runs offline against fakes.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_game_setup as tgs  # noqa: E402
from test_game_setup_nav import Game5, Setup, text  # noqa: E402

from openrecomp import game_releases as gr  # noqa: E402
from openrecomp import game_setup as gs  # noqa: E402
from openrecomp import i18n  # noqa: E402
from openrecomp import updater as u  # noqa: E402
from openrecomp.nav import Game, Nav  # noqa: E402
from openrecomp.progress_meter import Meter, EVERY  # noqa: E402
from openrecomp.update_service import UpdateService, failure_reason  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NEW_KEYS = ("updates.waiting", "updates.ready", "updates.queued", "updates.restarting", "updates.restart_title", "updates.restart_text", "updates.restart_text_game", "updates.later", "updates.restart_now", "updates.home_available", "updates.home_ready", "updates.home_installing", "updates.home_join", "setup.queued", "setup.unqueued", "setup.queued_start", "setup.update_launcher_first", "setup.update_queue_note", "setup.rebuild_auto", "setup.found_updates", "setup.all_current",
            "setup.err_replace", "setup.cancelled", "setup.cancelled_install", "setup.installing_wait", "setup.ok_wait", "setup.done_update",
            "setup.done_install", "setup.step_check", "updates.cancelled", "updates.err_network", "updates.err_verify",
            "updates.err_space", "updates.progress_title", "updates.progress_text", "updates.step_lookup",
            "updates.step_prepare", "updates.step_restart", "updates.running_hint", "updates.cancel_hint")


class StalledResponse:
    """A server that sent some bytes and then says nothing: read() blocks until the connection is closed."""

    def __init__(self, first=b"x" * 1000):
        self.first, self.closed = first, threading.Event()
        self.headers = {"Content-Length": "100000000"}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self.closed.set()

    def read(self, n):
        if self.first:
            data, self.first = self.first, b""
            return data
        self.closed.wait(30)
        raise OSError("connection closed")


class Meters(unittest.TestCase):
    def test_progress_events_are_throttled_and_carry_mb_speed_and_time_left(self):
        clock = [100.0]
        meter = Meter(lambda: clock[0])
        first = meter.update("download", 0, 10_000_000)
        self.assertEqual((first["step"], first["done"], first["total"]), ("download", 0, 10_000_000))
        clock[0] += EVERY / 5
        self.assertIsNone(meter.update("download", 100_000, 10_000_000))      # too soon: dropped
        clock[0] += 1.0
        second = meter.update("download", 2_000_000, 10_000_000)
        self.assertEqual((second["done"], second["speed"], second["left"]), (2_000_000, 1_904_761, 4))
        clock[0] += EVERY / 5
        self.assertIsNotNone(meter.update("download", 10_000_000, 10_000_000))   # the end always passes
        self.assertIsNotNone(meter.update("check", 0, 0))                          # a new step always passes

    def test_a_download_reports_at_least_twice_a_second(self):
        # 256 KB chunks at 1 MB/s = 4 chunks a second; with the 0.25 s throttle that is 3-4 reports a second.
        clock = [0.0]
        meter = Meter(lambda: clock[0])
        seen = 0
        for _ in range(40):
            clock[0] += 0.25
            if meter.update("download", int(clock[0] * 1_000_000), 100_000_000):
                seen += 1
        self.assertGreaterEqual(seen / 10.0, 2.0)


class LauncherUpdateDownload(unittest.TestCase):
    def test_cancel_stops_a_download_that_waits_for_the_server_within_a_second(self):
        cancel = threading.Event()
        response = StalledResponse()
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            target = Path(folder) / "release.zip"
            threading.Timer(0.2, cancel.set).start()
            started = time.monotonic()
            with mock.patch.object(u, "_open", return_value=response):
                with self.assertRaises(u.UpdateCancelled):
                    u._download("https://x", None, 10 ** 9, target, progress=lambda *_: None, cancel=cancel)
            self.assertLess(time.monotonic() - started, 1.0)
            self.assertFalse(target.exists())                                # the partial file is gone

    def test_stage_cancel_leaves_no_folder_beside_the_installation(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            install = Path(folder) / "install"
            install.mkdir()
            cancel = threading.Event()
            steps = []

            def download(url, channel, limit, destination=None, progress=None, cancel=None):
                if not destination:
                    return b"x"
                Path(destination).write_bytes(b"partial")
                progress(7, 100)
                Path(destination).unlink()           # what the real _download does on a cancel
                steps.append("downloading")
                cancel.set()
                raise u.UpdateCancelled()
            channel = u.Channel("example/OpenRecomp", "1", "test", ("0" * 64,))
            with mock.patch.object(u, "_download", side_effect=download), mock.patch.object(u, "verify_signature"), \
                    mock.patch.object(u, "_signed_checksum", return_value="a" * 64):
                with self.assertRaises(u.UpdateCancelled) as raised:
                    u.stage_update(install, dict(version="v1.2.3", sums_url="s", sig_url="g", zip_url="z",
                                                 digest="a" * 64, size=100), channel, progress=lambda *a: None,
                                   cancel=cancel)
            self.assertEqual(raised.exception.key, "update_cancelled")
            self.assertEqual(steps, ["downloading"])
            self.assertFalse(u._work_root(install).exists())
            self.assertEqual(os.listdir(install), [])

    def test_discard_stage_removes_only_its_own_transaction(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            install = Path(folder) / "install"
            install.mkdir()
            staged = u._work_root(install) / "abc" / "new"
            staged.mkdir(parents=True)
            (staged / "file").write_text("x")
            self.assertTrue(u.discard_stage(staged))
            self.assertFalse(u._work_root(install).exists())
            self.assertFalse(u.discard_stage(install))                       # not a stage: refused, untouched
            self.assertTrue(install.exists())


class LauncherUpdateService(unittest.TestCase):
    def service(self, api, **kw):
        self.threads = []

        def worker(fn):
            thread = threading.Thread(target=fn, daemon=True)
            self.threads.append(thread)
            thread.start()
        return UpdateService("fake-install", api=api, worker=worker, busy=lambda: False, quit=mock.Mock(), **kw)

    def api(self, stage):
        return SimpleNamespace(check_release=lambda *_a, **_k: dict(version="v1.2.3", notes="n", size=50_000_000),
                               stage_update=stage, prepare_update=mock.Mock(return_value=Path("plan")),
                               launch_update=mock.Mock(), discard_stage=mock.Mock())

    def wait(self, service, phase, seconds=3.0):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            service.poll()
            if service.state["phase"] == phase:
                return True
            time.sleep(0.01)
        return False

    def offered(self, service):
        service.check()
        self.assertTrue(self.wait(service, "available"))

    def test_progress_reaches_the_state_while_downloading(self):
        started, release = threading.Event(), threading.Event()
        clock = [0.0]

        def stage(root, rel, progress=None, cancel=None):
            progress("download", 0, 50_000_000)
            clock[0] += 1.0
            progress("download", 10_000_000, 50_000_000)
            started.set()
            release.wait(5)
            return Path("staged")
        service = self.service(self.api(stage), now=lambda: clock[0])
        self.offered(service)
        self.assertTrue(service.install())
        self.assertTrue(started.wait(3))
        st = service.state
        self.assertEqual((st["phase"], st["step"], st["done"], st["total"]), ("installing", "download", 10_000_000, 50_000_000))
        self.assertEqual((st["speed"], st["left"], st["can_cancel"]), (10_000_000, 4, True))
        release.set()

    def test_cancel_during_download_stops_the_worker_discards_and_never_launches(self):
        started = threading.Event()

        def stage(root, rel, progress=None, cancel=None):
            progress("download", 1, 100)
            started.set()
            cancel.wait(5)                          # the real download watches the same flag
            raise u.UpdateCancelled()
        api = self.api(stage)
        service = self.service(api)
        self.offered(service)
        service.install()
        self.assertTrue(started.wait(3))
        began = time.monotonic()
        self.assertTrue(service.cancel())
        self.assertTrue(service.state["cancelling"])
        self.assertTrue(self.wait(service, "cancelled"))
        self.assertLess(time.monotonic() - began, 1.0)
        api.prepare_update.assert_not_called()
        api.launch_update.assert_not_called()
        self.assertIsNone(service.prepared)
        self.assertFalse(service.applying)

    def test_a_cancel_that_arrives_after_the_download_discards_the_staged_folder(self):
        gate = threading.Event()

        def stage(root, rel, progress=None, cancel=None):
            gate.wait(5)
            return Path("staged")
        api = self.api(stage)
        service = self.service(api)
        self.offered(service)
        service.install()
        service.cancel()
        gate.set()
        self.assertTrue(self.wait(service, "cancelled"))
        api.discard_stage.assert_called_once_with(Path("staged"))
        api.prepare_update.assert_not_called()
        api.launch_update.assert_not_called()

    def test_no_double_start(self):
        gate = threading.Event()
        calls = []

        def stage(root, rel, progress=None, cancel=None):
            calls.append(1)
            gate.wait(5)
            return Path("staged")
        service = self.service(self.api(stage))
        self.offered(service)
        self.assertTrue(service.install())
        self.assertFalse(service.install())                  # a second press starts nothing
        service.check()                                      # nor does a check over a running update
        self.assertEqual(service.state["phase"], "installing")
        self.assertFalse(service.install_for("0.1.0"))
        gate.set()
        self.assertEqual(calls, [1])

    def test_cancel_is_not_offered_once_the_restart_begins(self):
        service = UpdateService("fake-install", api=self.api(lambda *a, **k: Path("staged")), worker=lambda fn: fn(),
                                busy=lambda: False, quit=mock.Mock())
        service.check()
        service.poll()
        service.install()
        launched = []
        service.api.launch_update = lambda root, plan: launched.append(service.state.copy())
        service.poll()                                       # prepared -> the helper starts, the launcher quits
        self.assertEqual(launched[0]["step"], "restart")
        self.assertFalse(launched[0]["can_cancel"])
        self.assertFalse(service.cancel())

    def test_cancel_while_waiting_for_games_to_close_discards_the_staged_update(self):
        busy = [True]
        api = self.api(lambda *a, **k: Path("staged"))
        service = UpdateService("fake-install", api=api, worker=lambda fn: fn(), busy=lambda: busy[0], quit=mock.Mock())
        service.check()
        service.poll()
        service.state["phase"] = "available"
        service.release = dict(version="v1.2.3", size=1)
        busy[0] = False
        service.install()
        busy[0] = True
        service.poll()
        self.assertEqual(service.state["phase"], "waiting")
        self.assertTrue(service.cancel())
        self.assertEqual(service.state["phase"], "cancelled")
        api.discard_stage.assert_called_once_with(Path("staged"))
        self.assertIsNone(service.prepared)

    def test_cancel_while_checking_drops_the_late_answer(self):
        gate = threading.Event()
        api = self.api(None)
        api.check_release = lambda *a, **k: (gate.wait(5), dict(version="v9"))[1]
        service = self.service(api)
        service.check()
        self.assertTrue(service.cancel())
        self.assertEqual(service.state["phase"], "cancelled")
        gate.set()
        time.sleep(0.1)
        service.poll()
        self.assertEqual(service.state["phase"], "cancelled")      # the answer of the cancelled check is not used

    def test_failures_say_the_reason_in_plain_words(self):
        import urllib.error
        self.assertEqual(failure_reason(urllib.error.URLError("down")), "network")
        self.assertEqual(failure_reason(TimeoutError()), "network")
        self.assertEqual(failure_reason(u.UpdateError("bad sha")), "verify")
        self.assertEqual(failure_reason(OSError(28, "No space left on device")), "space")
        self.assertEqual(failure_reason(RuntimeError("x")), "unknown")

        def stage(root, rel, progress=None, cancel=None):
            raise urllib.error.URLError("no route")
        service = self.service(self.api(stage))
        self.offered(service)
        service.install()
        self.assertTrue(self.wait(service, "error"))
        self.assertEqual(service.state["reason"], "network")
        for code in i18n.LANGUAGES:
            for key in NEW_KEYS:
                self.assertIn(key, i18n.catalog(code), (code, key))

    def test_an_install_after_a_quiet_check_still_says_when_it_fails(self):
        def stage(root, rel, progress=None, cancel=None):
            raise RuntimeError("boom")
        service = self.service(self.api(stage))
        service.check(quiet=True)
        self.assertTrue(self.wait(service, "available"))
        service.install()
        self.assertFalse(service.quiet)


class LauncherUpdateWindow(unittest.TestCase):
    def nav(self):
        self.cancels = []
        self.installs = []
        game = Game5("t5dr")
        nav = Nav([Game(game.m, game)], language="en", on_setup=Setup(),
                  on_update_install=lambda: self.installs.append(1) or True)
        nav.on_update_cancel = lambda: self.cancels.append(1) or True
        nav.on_update_check = lambda: self.installs.append("check")
        return nav

    def running(self, nav, **kw):
        state = dict(phase="installing", version="v1.2.3", step="download", done=10_000_000, total=50_000_000,
                     speed=5_000_000, left=8, can_cancel=True, cancelling=False, reason="")
        state.update(kw)
        nav.update_state = state

    def test_confirming_the_offer_opens_the_progress_window(self):
        nav = self.nav()
        nav.update_state = dict(phase="available", version="v1.2.3", notes="", size=50_000_000)
        nav.offer_update(force=True)
        nav.act("right", device="xbox")
        nav.act("confirm", device="xbox")
        self.assertEqual(self.installs, [1])
        self.assertEqual((nav.overlay, nav.confirm_kind), ("dialog", "update_progress"))

    def test_the_window_shows_step_mb_percent_speed_and_time_left(self):
        nav = self.nav()
        self.running(nav)
        nav._ask("update_progress")
        view = text(nav, nav.view()["dialog"])
        self.assertIn("Downloading 20 % · 10 of 50 MB · 5.0 MB/s · 8 s left", view["text"])
        self.assertEqual([o["label"] for o in view["options"]], ["Cancel"])
        self.running(nav, step="verify", total=0, done=0)
        self.assertIn("Verifying", text(nav, nav.view()["dialog"])["text"])

    def test_back_esc_and_the_cancel_button_all_cancel_once(self):
        nav = self.nav()
        self.running(nav)
        nav._ask("update_progress")
        nav.act("back", device="xbox")
        self.assertEqual(self.cancels, [1])
        self.running(nav, cancelling=True)
        self.assertIn("Cancelling", text(nav, nav.view()["dialog"])["text"])
        nav.act("confirm", device="xbox")                    # the Cancel button: nothing second
        nav.act("back", device="xbox")
        self.assertEqual(self.cancels, [1])
        self.assertEqual(nav.overlay, "dialog")              # stays until the worker has stopped

    def test_pressing_the_entry_again_shows_the_progress_and_starts_nothing(self):
        nav = self.nav()
        self.running(nav)
        nav._check_update()
        self.assertEqual((nav.overlay, nav.confirm_kind), ("dialog", "update_progress"))
        self.assertEqual(self.installs, [])                  # neither a check nor an install
        row = next(item for item in nav._drawer_items() if item["id"] == "updates")
        self.assertIn("Downloading 20 %", text(nav, row["hint"]))

    def test_no_cancel_during_the_install_step_and_the_window_says_so(self):
        nav = self.nav()
        self.running(nav, step="restart", can_cancel=False, done=0, total=0)
        nav._ask("update_progress")
        view = text(nav, nav.view()["dialog"])
        self.assertIn("do not close the launcher", view["text"])
        self.assertEqual([o["label"] for o in view["options"]], ["OK"])
        nav.act("back", device="xbox")
        nav.act("confirm", device="xbox")
        self.assertEqual(self.cancels, [])
        self.assertIn("do not close the launcher", text(nav, nav.toast))

    def test_the_window_closes_when_the_run_is_over(self):
        nav = self.nav()
        self.running(nav)
        nav._ask("update_progress")
        self.assertFalse(nav.poll_update())
        nav.update_state = dict(nav.update_state, phase="cancelled")
        self.assertTrue(nav.poll_update())
        self.assertIsNone(nav.overlay)

    def test_every_end_state_has_a_message(self):
        from openrecomp import app
        said = []
        phases = [("cancelled", ""), ("error", "network"), ("error", "verify"), ("error", "space"), ("error", ""),
                  ("waiting", "")]
        for phase, reason in phases:
            updates = SimpleNamespace(state=dict(phase=phase, reason=reason), quiet=False, poll=lambda: False)
            backend = SimpleNamespace(updates=updates, _update_phase="installing", _offered_update=True,
                                      _update_busy=lambda: False, _auto_update_pending=False,
                                      nav=SimpleNamespace(update_state={}, say=lambda *a: said.append(a[0])))
            app.Backend._poll_updates(backend)
        self.assertEqual(said, ["@updates.cancelled", "@updates.err_network", "@updates.err_verify",
                                "@updates.err_space", "@updates.failed"])
        for key in said:
            self.assertIn(key[1:], i18n.catalog("en"))
        self.assertIn("Nothing was changed", i18n.catalog("en")["updates.cancelled"])
        self.assertIn("Nothing was changed", i18n.catalog("en")["updates.err_network"])


class GameDownloads(tgs.Env):
    def test_cancel_stops_a_download_that_waits_for_the_server_within_a_second(self):
        cancel = threading.Event()
        response = StalledResponse()
        dest = str(self.dir / "release.zip")
        threading.Timer(0.2, cancel.set).start()
        began = time.monotonic()
        with self.assertRaises(gr.ReleaseError) as raised:
            gr.download(gr.SOURCES["t5dr"], "https://x", dest, limit=10 ** 9,
                        opener=lambda *a: response, cancel=cancel)
        self.assertEqual(raised.exception.key, "@setup.cancelled")
        self.assertLess(time.monotonic() - began, 1.0)
        self.assertEqual(os.listdir(self.dir), ["home"] if (self.dir / "home").exists() else [])

    def test_cancel_during_an_update_download_removes_partial_files_and_keeps_the_old_install(self):
        self.gh.add_t5dr("1.2.0")
        root = gr.install_fresh("t5dr", self.offer(), str(self.dir / "games"))
        before = sorted(str(p.relative_to(root)) for p in Path(root).rglob("*"))
        self.gh.add_t5dr("1.2.1", zip_data=os.urandom(3_000_000))

        def update(gid, offer, folder, progress=None, cancel=None, **kw):
            def watching(step, done, total):
                progress(step, done, total)
                if step == "download" and done:
                    cancel.set()                    # the player pressed Cancel in the middle of the download
            return gr.update_in_place(gid, offer, folder, progress=watching, cancel=cancel, **kw)
        setup = gs.GameSetup({}, worker=lambda fn: threading.Thread(target=fn, daemon=True).start(), update=update)
        setup.check("t5dr", root, force=True)
        for _ in range(300):
            if setup.poll():
                break
            time.sleep(0.02)
        self.assertTrue(setup.update("t5dr", root))
        events = []
        for _ in range(500):
            events += setup.poll()
            if events:
                break
            time.sleep(0.02)
        self.assertEqual(events[0][3][0], "@setup.cancelled")
        self.assertEqual(setup.view("t5dr")["phase"], "ready")
        self.assertEqual(gr.installed_version("t5dr", root), "1.2.0")
        self.assertEqual(sorted(str(p.relative_to(root)) for p in Path(root).rglob("*")), before)
        self.assertFalse(Path(gr.update_stage(root)).exists())
        left = [p for p in self.dir.rglob("*.part")]
        self.assertEqual(left, [])
        self.assertIn("Nothing was changed", i18n.catalog("en")["setup.cancelled"])

    def test_the_view_gets_step_mb_speed_and_time_left_a_few_times_a_second(self):
        clock = [10.0]
        setup = gs.GameSetup({}, worker=lambda fn: fn(), now=lambda: clock[0],
                             update=lambda *a, **k: None)
        setup.offers["t5dr"] = dict(version="1.2.1", zip=dict(size=40_000_000), name="v1.2.1", prerelease=False, notes="")
        report = setup._progress("t5dr")
        report("download", 0, 40_000_000)
        clock[0] += 0.05
        report("download", 500_000, 40_000_000)                    # throttled
        self.assertEqual(setup.view("t5dr")["done"], 0)
        clock[0] += 1.0
        report("download", 8_000_000, 40_000_000)
        view = setup.view("t5dr")
        self.assertEqual((view["done"], view["total"]), (8_000_000, 40_000_000))
        self.assertGreater(view["speed"], 0)
        self.assertGreater(view["left"], 0)

    def test_cancel_is_refused_once_files_are_being_replaced(self):
        setup = gs.GameSetup({}, worker=lambda fn: None)
        setup.offers["t5dr"] = dict(version="1.2.1", zip=dict(size=1), name="v1.2.1", prerelease=False, notes="")
        self.assertTrue(setup.update("t5dr", str(self.dir)))
        self.assertFalse(setup.update("t5dr", str(self.dir)))        # no second start
        self.assertFalse(setup.install("t5dr", str(self.dir)))
        report = setup._progress("t5dr")
        report("download", 1, 10)
        self.assertTrue(setup.view("t5dr")["can_cancel"])
        report("swap", 0, 0)
        self.assertFalse(setup.view("t5dr")["can_cancel"])
        self.assertFalse(setup.cancel("t5dr"))
        self.assertFalse(setup.cancels["t5dr"].is_set())            # the exchange is never interrupted
        self.assertEqual(setup.running(), "t5dr")


class GameWindow(unittest.TestCase):
    def nav(self):
        self.setup = Setup()
        game = Game5("t5dr")
        return Nav([Game(game.m, game)], language="en", on_setup=self.setup)

    def state(self, nav, **kw):
        st = dict(phase="updating", installed="1.2.0", latest="1.2.1", required=False, available=True, size=95_000_000,
                  step="download", done=19_000_000, total=95_000_000, speed=4_000_000, left=19, can_cancel=True,
                  offer=dict(version="1.2.1", size=95_000_000, name="v1.2.1", prerelease=False, notes=""))
        st.update(kw)
        nav.setup_state = {"t5dr": st}

    def test_pressing_the_update_entry_again_shows_the_running_progress(self):
        nav = self.nav()
        self.state(nav)
        nav.setup_offer_update(nav.games[0])
        self.assertEqual((nav.overlay, nav.confirm_kind), ("dialog", "setup_progress"))
        self.assertEqual([c for c in self.setup.calls if c[0] in ("update", "install", "check")], [])
        self.assertIn("Downloading 20 %", text(nav, nav.view()["dialog"])["text"])
        nav.overlay = None
        nav.setup_begin(nav.games[0])
        self.assertEqual(nav.confirm_kind, "setup_progress")
        self.assertEqual([c for c in self.setup.calls if c[0] in ("update", "install", "check")], [])

    def test_cancel_is_not_offered_while_files_are_replaced(self):
        nav = self.nav()
        self.state(nav, step="swap", can_cancel=False, done=0, total=0)
        nav.setup_game = "t5dr"
        nav._ask("setup_progress")
        view = text(nav, nav.view()["dialog"])
        self.assertIn("do not close the launcher", view["text"])
        self.assertEqual([o["label"] for o in view["options"]], ["OK"])
        nav.act("back", device="xbox")
        nav.act("confirm", device="xbox")
        self.assertNotIn("cancel", [c[0] for c in self.setup.calls])
        self.assertEqual(nav.confirm_kind, "setup_progress")

    def test_cancel_during_the_download_is_offered_and_says_nothing_was_changed(self):
        nav = self.nav()
        self.state(nav)
        nav.setup_game = "t5dr"
        nav._ask("setup_progress")
        self.assertEqual([o["label"] for o in text(nav, nav.view()["dialog"])["options"]], ["Cancel"])
        nav.act("back", device="xbox")
        self.assertEqual(self.setup.calls[-1], ("cancel", "t5dr", None))
        nav.setup_state["t5dr"].update(phase="ready")
        nav.poll_setup([("t5dr", "update", None, ("@setup.cancelled", ""))])
        self.assertEqual(text(nav, nav.toast), "Update cancelled. Nothing was changed.")
        nav.poll_setup([("t5dr", "install", None, ("@setup.cancelled", ""))])
        self.assertIn("Installation cancelled. Nothing was changed", text(nav, nav.toast))

    def test_done_says_the_version(self):
        nav = self.nav()
        nav.poll_setup([("t5dr", "update", dict(version="1.2.1", rebuild=False, restart=False), None)])
        self.assertIn("Updated to 1.2.1.", text(nav, nav.toast))


class ExchangeIsVerified(tgs.Env):
    """A player's T4 update ended "successfully" with deps/ps2recomp missing: the exchange is checked afterwards."""

    def t4_zip_entries(self, tag):
        from release_fixtures import t4_entries
        return t4_entries(tag, extra=[("T4/deps/ps2recomp/src/main.cpp", f"// {tag}\n"),
                                      ("T4/deps/ps2recomp/CMakeLists.txt", f"# {tag}\n")])

    def installed_t4(self):
        from release_fixtures import zip_bytes
        self.gh.add_t4("v0.1.0", zip_data=zip_bytes(self.t4_zip_entries("v0.1.0")))
        root = gr.install_fresh("t4", self.offer("t4", "prerelease"), str(self.dir / "games"))
        from release_fixtures import zip_bytes as zb
        self.gh.add_t4("v0.1.1", zip_data=zb(self.t4_zip_entries("v0.1.1")))
        return root

    def swap_that_loses(self, folder):
        real = gr.swap

        def swap(src, root, new, backup):
            out = real(src, root, new, backup)
            import shutil
            shutil.rmtree(os.path.join(root, *folder.split("/")))      # the folder never arrived
            return out
        return swap

    def test_a_folder_missing_after_the_exchange_is_extracted_again_from_the_verified_zip(self):
        root = self.installed_t4()
        with mock.patch.object(gr, "swap", self.swap_that_loses("deps/ps2recomp")):
            result = gr.update_in_place("t4", self.offer("t4", "prerelease"), root)
        self.assertEqual(result["version"], "0.1.1")
        self.assertIn("v0.1.1", (Path(root) / "deps" / "ps2recomp" / "src" / "main.cpp").read_text())
        self.assertTrue((Path(root) / "deps" / "ps2recomp" / "CMakeLists.txt").is_file())
        self.assertFalse(Path(gr.update_stage(root)).exists())

    def test_when_it_cannot_be_written_again_the_old_version_is_put_back_and_the_folder_is_named(self):
        root = self.installed_t4()
        with mock.patch.object(gr, "swap", self.swap_that_loses("deps/ps2recomp")),                 mock.patch.object(gr, "extract_entries", side_effect=PermissionError(5, "locked by antivirus")):
            with self.assertRaises(gr.ReleaseError) as raised:
                gr.update_in_place("t4", self.offer("t4", "prerelease"), root)
        self.assertEqual((raised.exception.key, str(raised.exception)), ("@setup.err_replace", "deps"))
        self.assertEqual(gr.installed_version("t4", root), "0.1.0")
        self.assertIn("v0.1.0", (Path(root) / "deps" / "ps2recomp" / "src" / "main.cpp").read_text())
        self.assertIn("v0.1.0", (Path(root) / "tools" / "build_game.ps1").read_text())
        self.assertFalse(Path(gr.update_stage(root)).exists())
        from openrecomp.nav_game_setup import GameSetupNav
        text_ = i18n.localize(GameSetupNav._setup_error_text(SimpleNamespace(), ("@setup.err_replace", "deps")), "en")
        self.assertIn("could not replace deps", text_)
        self.assertIn("antivirus", text_)

    def test_a_locked_file_during_the_exchange_puts_everything_back_and_says_nothing_changed(self):
        root = self.installed_t4()
        real, seen = gr._move, []

        def locked(a, b, timeout=20.0):
            seen.append(a)
            if len(seen) == 4:
                raise PermissionError(32, "in use by another process")
            return real(a, b, timeout)
        with mock.patch.object(gr, "_move", side_effect=locked), self.assertRaises(gr.ReleaseError) as raised:
            gr.update_in_place("t4", self.offer("t4", "prerelease"), root)
        self.assertEqual(raised.exception.key, "@setup.err_busy")
        self.assertEqual(gr.installed_version("t4", root), "0.1.0")
        self.assertIn("v0.1.0", (Path(root) / "deps" / "ps2recomp" / "src" / "main.cpp").read_text())
        self.assertIn("Nothing was changed", i18n.catalog("en")["setup.err_busy"])


class SeamlessUpdate(unittest.TestCase):
    """Owner: "the update should be seamless and not buggy": quiet background check, one Update that does everything
    in order, never a half state, nothing that interrupts a running game."""

    def nav(self, **kw):
        self.setup = Setup()
        self.installed = []
        game = Game5("t5dr")
        nav = Nav([Game(game.m, game)], language="en", on_setup=self.setup,
                  on_update_install=lambda: self.installed.append(1) or True, **kw)
        nav.on_update_apply = lambda: self.installed.append("apply") or True
        return nav

    def ready_game(self, nav, **kw):
        st = dict(phase="ready", installed="1.2.0", latest="1.2.1", required=False, available=True, size=95_000_000,
                  step="", done=0, total=0, offer=dict(version="1.2.1", size=95_000_000, name="v1.2.1", prerelease=False,
                                                       notes=""))
        st.update(kw)
        nav.setup_state = {"t5dr": st}

    # ---- 1. quiet check: a line, never a dialog
    def test_a_background_found_update_is_a_line_on_the_home_screen_and_no_dialog(self):
        from openrecomp import app
        nav = self.nav()
        updates = SimpleNamespace(state=dict(phase="available", version="v1.2.3"), quiet=True, poll=lambda: False)
        backend = SimpleNamespace(updates=updates, _update_busy=lambda: False, _update_phase="idle", _offered_update=False,
                                  _auto_update_pending=False, nav=nav)
        app.Backend._poll_updates(backend)
        self.assertIsNone(nav.overlay)                                  # nothing popped up by itself
        view = nav.view()
        self.assertIn("Update available: launcher v1.2.3.", text(nav, view["hint"]))
        self.assertIn(("x", "Update"), [(p["action"], text(nav, p["label"])) for p in view["prompts"]])
        nav.act("x", device="xbox")                                     # the player asks: now the question comes
        self.assertEqual((nav.overlay, nav.confirm_kind), ("dialog", "update"))

    def test_a_game_update_shows_on_its_tile(self):
        nav = self.nav()
        self.ready_game(nav)
        tile = nav.view()["shelf"]["tiles"][0]
        self.assertTrue(tile["update"])

    # ---- 2. one Update, in order
    def test_one_update_does_the_launcher_first_then_asks_once_to_restart_then_the_game_continues(self):
        nav = self.nav()
        self.ready_game(nav)
        nav.update_state = dict(phase="available", version="v1.2.3", size=40_000_000, can_cancel=True)
        nav.setup_offer_update(nav.games[0])
        self.assertIn("The launcher updates first (v1.2.3)", text(nav, nav.view()["dialog"])["text"])
        nav.act("right", device="xbox")
        nav.act("confirm", device="xbox")
        self.assertEqual(self.setup.calls[-1], ("update_with_launcher", "t5dr", "v1.2.3"))
        self.assertEqual(nav.confirm_kind, "update_progress")
        # the launcher's download finished: one prompt, "Restart to finish"
        nav.update_state = dict(phase="ready", version="v1.2.3", can_cancel=True)
        self.assertTrue(nav.poll_update())
        self.assertEqual(nav.confirm_kind, "update_restart")
        view = text(nav, nav.view()["dialog"])
        self.assertEqual(view["title"], "Restart to finish")
        self.assertIn("continues by itself", view["text"])
        self.assertFalse(nav.poll_update())                           # asked once, not again every tick
        nav.act("right", device="xbox")
        nav.act("confirm", device="xbox")
        self.assertEqual(self.installed, ["apply"])

    def test_the_backend_remembers_the_game_update_and_resumes_it_after_the_restart(self):
        from openrecomp import app_game_setup as ags
        said = []
        nav = SimpleNamespace(say=lambda *a: said.append(a[0]), setup_game="", setup_cancelling=False,
                              _ask=lambda kind: said.append(kind))
        backend = SimpleNamespace(config={}, nav=nav,
                                  updates=SimpleNamespace(state=dict(phase="available", version="v1.2.3")),
                                  _install_update=lambda: True, _update_busy=lambda allow_lobby=False: False)
        with mock.patch.object(ags.mf, "save_config"):
            self.assertTrue(ags.GameSetupBackend._setup_update_with_launcher(backend, "t5dr"))
        self.assertEqual(backend.config["pending_game_update"], dict(game="t5dr", launcher="v1.2.3"))
        # after the restart: the check is in, the update starts by itself (no second click)
        started = []
        setup = SimpleNamespace(state={"t5dr": dict(phase="ready", available=True, needs_launcher="")},
                                update=lambda gid, root: started.append((gid, root)) or True)
        backend2 = SimpleNamespace(config=dict(backend.config), nav=nav, _setup=setup, setup=setup,
                                   _update_busy=lambda allow_lobby=False: False, _setup_root=lambda gid: "C:/games/t5dr")
        with mock.patch.object(ags.mf, "save_config"):
            self.assertTrue(ags.GameSetupBackend._resume_game_update(backend2))
        self.assertEqual(started, [("t5dr", "C:/games/t5dr")])
        self.assertNotIn("pending_game_update", backend2.config)

    def test_a_rebuild_starts_by_itself_with_a_line_that_says_so(self):
        nav = self.nav()
        built = []
        nav._start_build = lambda g, force=False: built.append(g.id)
        nav.poll_setup([("t5dr", "update", dict(version="1.2.1", rebuild=True, restart=False), None)])
        self.assertEqual(built, ["t5dr"])
        self.assertIn("is building it now", text(nav, nav.toast))
        nav.poll_setup([("t5dr", "update", dict(version="1.2.1", rebuild=False, restart=False), None)])
        self.assertEqual(built, ["t5dr"])                              # no build needed: none started

    def test_a_rebuild_after_the_launcher_restart_is_remembered_and_run_when_nothing_else_runs(self):
        from openrecomp import app_game_setup as ags
        nav = self.nav()
        nav.poll_setup([("t5dr", "update", dict(version="1.2.1", rebuild=True, restart=True), None)])
        self.assertEqual(self.setup.calls[-1], ("pending_build", "t5dr", None))
        built = []
        busy = [True]
        backend = SimpleNamespace(config={"pending_build": "t5dr"}, nav=SimpleNamespace(
            setup_auto_build=built.append, game_by_id=lambda gid: SimpleNamespace(a=SimpleNamespace(found=lambda: True)),
            setup_queued=""), _setup_started=True, _queued_update="", _update_busy=lambda allow_lobby=False: busy[0])
        with mock.patch.object(ags.mf, "save_config"):
            ags.GameSetupBackend._run_queued_and_pending(backend)
            self.assertEqual(built, [])
            busy[0] = False
            ags.GameSetupBackend._run_queued_and_pending(backend)
        self.assertEqual(built, ["t5dr"])
        self.assertNotIn("pending_build", backend.config)

    # ---- 3. never a half state
    def test_a_verified_launcher_download_is_reused_by_the_next_try(self):
        import hashlib
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            install = Path(folder) / "install"
            install.mkdir()
            data = b"launcher zip bytes"
            digest = hashlib.sha256(data).hexdigest()
            downloads = []

            def download(url, channel, limit, destination=None, progress=None, cancel=None):
                if not destination:
                    return b"x"
                downloads.append(url)
                Path(destination).write_bytes(data)
                return len(data)
            channel = u.Channel("example/OpenRecomp", "1", "test", ("0" * 64,))
            release = dict(version="v1.2.3", sums_url="s", sig_url="g", zip_url="z", digest=digest, size=len(data))
            with mock.patch.object(u, "_download", side_effect=download), mock.patch.object(u, "verify_signature"), \
                    mock.patch.object(u, "_signed_checksum", return_value=digest), \
                    mock.patch.object(u.zipfile, "ZipFile", side_effect=OSError("disk error while unpacking")):
                with self.assertRaises(OSError):
                    u.stage_update(install, release, channel)           # fails after the download was verified
                self.assertTrue((u._work_root(install) / u.cache_name("v1.2.3")).is_file())
                self.assertEqual([d for d in u._work_root(install).iterdir() if d.is_dir()], [])   # no half stage
                with self.assertRaises(OSError):
                    u.stage_update(install, release, channel)
            self.assertEqual(downloads, ["z"])                            # downloaded once, reused for the retry

    def test_a_download_with_the_wrong_hash_is_not_kept(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            install = Path(folder) / "install"
            install.mkdir()

            def download(url, channel, limit, destination=None, progress=None, cancel=None):
                if destination:
                    Path(destination).write_bytes(b"corrupt!")
                    return 8
                return b"x"
            channel = u.Channel("example/OpenRecomp", "1", "test", ("0" * 64,))
            release = dict(version="v1.2.3", sums_url="s", sig_url="g", zip_url="z", digest="a" * 64, size=8)
            with mock.patch.object(u, "_download", side_effect=download), mock.patch.object(u, "verify_signature"), \
                    mock.patch.object(u, "_signed_checksum", return_value="a" * 64):
                with self.assertRaises(u.UpdateError):
                    u.stage_update(install, release, channel)
            self.assertFalse(u._work_root(install).exists())

    def test_cache_files_of_installed_versions_are_cleaned_up(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            install = Path(folder) / "install"
            install.mkdir()
            (install / "release.json").write_text(json.dumps(dict(version="v1.2.3")), encoding="utf-8")
            work = u._work_root(install)
            work.mkdir()
            (work / u.cache_name("v1.2.3")).write_bytes(b"old")
            (work / u.cache_name("v1.3.0")).write_bytes(b"newer, not installed yet")
            u.clean_finished(install)
            self.assertEqual(sorted(p.name for p in work.iterdir()), [u.cache_name("v1.3.0")])


class GameCache(tgs.Env):
    def zip_requests(self):
        return [r for r in self.gh.requests if r.endswith(".zip")]

    def test_a_cancelled_or_failed_update_reuses_the_verified_download(self):
        self.gh.add_t5dr("1.2.0")
        root = gr.install_fresh("t5dr", self.offer(), str(self.dir / "games"))
        self.gh.add_t5dr("1.2.1")
        cancel = threading.Event()

        def progress(step, done, total):
            if step == "unpack":
                cancel.set()                                         # cancelled after the download was verified
        with self.assertRaises(gr.ReleaseError):
            gr.update_in_place("t5dr", self.offer(), root, progress=progress, cancel=cancel)
        self.assertEqual(gr.installed_version("t5dr", root), "1.2.0")
        kept = Path(gr.download_keep("t5dr", Path(root).parent))
        self.assertEqual([p.name for p in kept.iterdir()], ["T5DR-Online-1.2.1.zip"])
        before = len(self.zip_requests())
        result = gr.update_in_place("t5dr", self.offer(), root)
        self.assertEqual(result["version"], "1.2.1")
        self.assertEqual(len(self.zip_requests()), before)            # the retry did not download the zip again
        self.assertFalse(kept.exists())                               # and the kept file went away with the success

    def test_a_cancel_during_the_download_keeps_nothing(self):
        self.gh.add_t5dr("1.2.0", zip_data=os.urandom(2_000_000))
        cancel = threading.Event()

        def progress(step, done, total):
            if step == "download" and done:
                cancel.set()
        with self.assertRaises(gr.ReleaseError):
            gr.install_fresh("t5dr", self.offer(), str(self.dir / "games"), progress=progress, cancel=cancel)
        self.assertEqual(list((self.dir / "games").iterdir()), [])


class QueuedUpdate(unittest.TestCase):
    """4. No surprise while a game, build or match runs: the update waits and says so."""

    def nav(self, busy):
        self.setup = Setup()
        game = Game5("t5dr")
        nav = Nav([Game(game.m, game)], language="en", on_setup=self.setup)
        nav._update_busy = lambda allow_lobby=False: busy[0]
        nav.setup_state = {"t5dr": dict(phase="ready", installed="1.2.0", latest="1.2.1", required=False, available=True,
                                        size=1_000_000, step="", offer=dict(version="1.2.1", size=1_000_000, name="v",
                                                                            prerelease=False, notes=""))}
        return nav

    def test_pressing_update_while_the_game_runs_queues_it_and_pressing_again_unqueues(self):
        busy = [True]
        nav = self.nav(busy)
        nav.setup_offer_update(nav.games[0])
        self.assertIsNone(nav.overlay)                                  # no dialog over the running game
        self.assertEqual(self.setup.calls[-1], ("queue_update", "t5dr", None))
        self.assertEqual(text(nav, nav.toast), "Update will install when you close the game.")
        nav.setup_queued = "t5dr"
        nav.setup_offer_update(nav.games[0])
        self.assertEqual(self.setup.calls[-1], ("unqueue", "t5dr", None))

    def test_the_queued_update_starts_by_itself_when_the_game_is_closed(self):
        from openrecomp import app_game_setup as ags
        started, said = [], []
        busy = [True]
        nav = SimpleNamespace(setup_queued="t5dr", say=lambda *a: said.append(a[0]))
        setup = SimpleNamespace(update=lambda gid, root: started.append((gid, root)) or True)
        backend = SimpleNamespace(config={}, nav=nav, setup=setup, _queued_update="t5dr", _setup_started=True,
                                  _update_busy=lambda allow_lobby=False: busy[0], _setup_root=lambda gid: "C:/t5dr")
        ags.GameSetupBackend._run_queued_and_pending(backend)
        self.assertEqual(started, [])                                   # still running: waits
        busy[0] = False
        ags.GameSetupBackend._run_queued_and_pending(backend)
        self.assertEqual(started, [("t5dr", "C:/t5dr")])
        self.assertEqual((backend._queued_update, nav.setup_queued), ("", ""))
        self.assertEqual(said, ["@setup.queued_start"])

    def test_a_launcher_update_downloads_while_a_game_runs_and_waits_for_the_restart(self):
        api = SimpleNamespace(check_release=lambda *a, **k: dict(version="v1.2.3", size=5),
                              stage_update=lambda *a, **k: Path("staged"), prepare_update=lambda *a: Path("plan"),
                              launch_update=mock.Mock(), discard_stage=mock.Mock())
        busy = [True]
        service = UpdateService("fake", api=api, worker=lambda fn: fn(), busy=lambda: busy[0], quit=mock.Mock(),
                                ask_restart=True)
        service.check()
        service.poll()
        self.assertTrue(service.install())                              # downloading is fine while the game runs
        service.poll()
        self.assertEqual(service.state["phase"], "ready")               # the prompt waits for the player
        self.assertTrue(service.apply())
        service.poll()
        self.assertEqual(service.state["phase"], "waiting")             # "will install when you close the game"
        api.launch_update.assert_not_called()
        busy[0] = False
        service.poll()
        api.launch_update.assert_called_once()

    def test_the_restart_prompt_never_opens_over_a_running_game_or_another_dialog(self):
        game = Game5("t5dr")
        nav = Nav([Game(game.m, game)], language="en", on_setup=Setup())
        nav.update_state = dict(phase="ready", version="v1.2.3")
        nav._update_busy = lambda allow_lobby=False: True
        self.assertFalse(nav.poll_update())
        self.assertIsNone(nav.overlay)
        nav._update_busy = lambda allow_lobby=False: False
        nav._ask("exit")
        self.assertFalse(nav.poll_update())
        self.assertEqual(nav.confirm_kind, "exit")
        nav.overlay = None
        self.assertTrue(nav.poll_update())
        self.assertEqual(nav.confirm_kind, "update_restart")


class ManualCheckFeedback(unittest.TestCase):
    def test_checking_for_game_updates_ends_with_a_sentence(self):
        setup = Setup()
        game = Game5("t5dr")
        nav = Nav([Game(game.m, game)], language="en", on_setup=setup)
        nav.setup_state = {"t5dr": dict(phase="ready", installed="1.2.0", latest="1.2.0", required=False, available=False)}
        nav.setup_check_manual()
        self.assertEqual(text(nav, nav.toast), "Looking for game updates...")
        nav.setup_state["t5dr"]["phase"] = "checking"
        nav.poll_setup([])
        nav.setup_state["t5dr"]["phase"] = "ready"
        nav.poll_setup([("t5dr", "check", dict(), None)])
        self.assertEqual(text(nav, nav.toast), "The games are up to date.")
        nav.setup_state["t5dr"].update(available=True, latest="1.2.1", offer=dict(version="1.2.1", size=1, name="v",
                                                                                prerelease=False, notes=""))
        nav.setup_check_manual()
        nav.poll_setup([("t5dr", "check", dict(), None)])
        self.assertIn("Updates available:", text(nav, nav.toast))


class Catalogs(unittest.TestCase):
    def test_every_new_text_exists_in_all_seven_catalogs_with_its_placeholders(self):
        import re
        en = i18n.catalog("en")
        for code in i18n.LANGUAGES:
            catalog = i18n.catalog(code)
            for key in NEW_KEYS:
                self.assertIn(key, catalog, (code, key))
                self.assertEqual(sorted(re.findall(r"{(\w+)}", catalog[key])), sorted(re.findall(r"{(\w+)}", en[key])),
                                 (code, key))
        self.assertEqual(len(i18n.LANGUAGES), 7)


if __name__ == "__main__":
    unittest.main()
