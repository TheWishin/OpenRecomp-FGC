"""T4 reports use synthetic diagnostics and a local report server; no game install is opened."""
import io
import json
import os
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from openrecomp import i18n, t4_report
from openrecomp.adapters.t4 import T4
from openrecomp.nav import Game, Nav
from test_support_send import StandIn
from test_t4 import FakeCore, MANIFEST

WORK = Path(__file__).resolve().parents[1]


class T4Reports(unittest.TestCase):
    def setUp(self):
        (WORK / "build").mkdir(exist_ok=True)
        self.temp = self.enterContext(tempfile.TemporaryDirectory(dir=WORK / "build", prefix="t4-support-"))
        self.folder = Path(self.temp)
        self.root, self.home = self.folder / "install", self.folder / "home"
        self.root.mkdir()
        self.home.mkdir()
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_HOME=str(self.home)))
        self.core = FakeCore()
        self.a = T4(MANIFEST, {"language": "en", "t4_lobby_server": "127.0.0.1:7791"}, str(self.root), core=self.core)
        self.a.hero = lambda: ""
        self.a._online_config = lambda: {"name": "FixturePlayer", "sessions": {
            "test": {"name": "FixturePlayer", "token": "fixture-long-token"}}}
        self.a._direct_local_identity = lambda: {"build_id": "0123456789abcdef"}
        self.write(self.root / "logs" / "latest" / "net.log", "NETSUMMARY rollback=2 peer 192.0.2.12\n")
        self.write(self.root / "logs" / "latest" / "stdout.txt", "game diagnostic\n")
        self.write(self.root / "logs" / "latest" / "build_identity.json", json.dumps({
            "build_id": "0123456789abcdef", "compiler": "MSVC 19.44", "token": "fixture-secret",
            "nested": {"email": "fixture" + "@example.invalid"}}))
        self.write(self.root / "logs" / "build.log", "BUILD completed\n")
        self.write(self.root / "launcher.log", "T4 launcher diagnostic\n")
        self.write(self.home / "launcher.log", "OpenRecomp diagnostic\n")

    @staticmethod
    def write(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def finish(self):
        deadline = time.monotonic() + 10
        while self.a.support_state()["running"] and time.monotonic() < deadline:
            threading.Event().wait(0.01)
        state = self.a.support_state()
        self.assertFalse(state["running"])
        return state

    def build(self, **kwargs):
        return t4_report.build(str(self.root), str(self.home), self.folder / "reports", **kwargs)

    def test_report_collects_diagnostics_and_scrubs_all_private_fields(self):
        profile = "C:/Users/FixtureUser"
        email = "fixture" + "@example.invalid"
        raw = "\n".join((profile, profile.replace("/", "\\"), "FixtureUser FixturePC FixturePlayer",
                         email, "198.51.100.24 2001:db8::1234 ::1 fe80::1234%eth0 ::ffff:192.0.2.1",
                         "Authorization: Bearer abc-fixture-secret", "token=unknown-token password=unknown-password",
                         '"access_token": "json-secret"', "fixture-long-token", "NETSUMMARY rollback=3"))
        self.write(self.root / "logs" / "latest" / "net.log", raw)
        with mock.patch.dict(os.environ, USERNAME="FixtureUser", COMPUTERNAME="FixturePC", USERPROFILE=profile):
            self.assertTrue(self.a.support_start("report"))
            state = self.finish()
        self.assertEqual(state["error"], "")
        with zipfile.ZipFile(state["report"]) as archive:
            names = archive.namelist()
            self.assertIn("contents.txt", names)
            self.assertIn("build_identity.json", names)
            self.assertIn("system.txt", names)
            data = "\n".join(archive.read(n).decode() for n in names)
            for secret in ("FixtureUser", "FixturePC", "FixturePlayer", email, profile, "198.51.100.24",
                           "2001:db8::1234", "fe80::1234", "::1", "192.0.2.1", "abc-fixture-secret",
                           "unknown-token", "unknown-password", "json-secret", "fixture-long-token", "fixture-secret"):
                self.assertNotIn(secret, data)
            for expected in ("NETSUMMARY", "rollback=3", "MSVC 19.44", "0123456789abcdef", "BUILD completed",
                             "OpenRecomp diagnostic", "T4 launcher diagnostic", "game diagnostic"):
                self.assertIn(expected, data)
            self.assertEqual(json.loads(archive.read("build_identity.json"))["token"], "[private]")

    def test_only_allowlisted_text_and_latest_logs_are_collected(self):
        for name in ("disc.iso", "card.ps2", "generated.cpp", "runtime.exe", "game.bin", "settings.json", "screen.png"):
            self.write(self.root / "logs" / name, "excluded-fixture-marker")
        self.write(self.root / "logs" / "game-binary.log", "binary\0excluded-fixture-marker")
        self.write(self.root / "game" / "game.log", "excluded-fixture-marker")
        for n in range(12):
            p = self.root / "logs" / f"net-{n}.log"
            self.write(p, f"latest-marker-{n:02d}")
            os.utime(p, (2000000000 + n, 2000000000 + n))
        with zipfile.ZipFile(self.build()) as archive:
            data = b"\n".join(archive.read(n) for n in archive.namelist())
            self.assertNotIn(b"excluded-fixture-marker", data)
            self.assertNotIn(b"latest-marker-00", data)
            self.assertIn(b"latest-marker-11", data)
            self.assertEqual(len([n for n in archive.namelist() if n.startswith("online/")]), 8)

    def test_links_cannot_escape_diagnostic_directories(self):
        outside = self.folder / "outside.log"
        self.write(outside, "excluded-link-marker")
        link = self.root / "logs" / "net-link.log"
        try:
            link.symlink_to(outside)
        except OSError:
            # Windows developer mode is not required: simulate the lstat reparse flag instead.
            self.write(link, "excluded-link-marker")
            real = Path.lstat

            def lstat(path):
                if path == link:
                    return type("Reparse", (), {"st_mode": 0, "st_file_attributes": 0x400})()
                return real(path)

            self.enterContext(mock.patch.object(Path, "lstat", lstat))
        with zipfile.ZipFile(self.build()) as archive:
            self.assertNotIn(b"excluded-link-marker", b"".join(archive.read(n) for n in archive.namelist()))

    def test_bounded_report_fits_upload_and_server_expansion_limits(self):
        for n in range(12):
            self.write(self.root / "logs" / f"net-{n}.log", "diagnostic line\n" * 100000)
            self.write(self.root / "logs" / f"game-{n}.log", "diagnostic line\n" * 100000)
            self.write(self.root / "logs" / f"build-{n}.log", "diagnostic line\n" * 100000)
        path = self.build(build_lines=["build output" * 100000])
        self.assertLessEqual(Path(path).stat().st_size, t4_report.SEND_TARGET)
        with zipfile.ZipFile(path) as archive:
            self.assertIsNone(archive.testzip())
            for group in ("logs/", "online/", "compile/"):
                self.assertTrue(any(n.startswith(group) and archive.read(n) for n in archive.namelist()))
            self.assertLessEqual(len(archive.infolist()), 200)
            for entry in archive.infolist():
                self.assertRegex(entry.filename, r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+){0,4}$")
                self.assertLessEqual(entry.file_size, 32 << 20)
                self.assertEqual(entry.compress_type, zipfile.ZIP_STORED)

    def test_one_press_uploads_real_cleaned_zip_to_fake_t4_server(self):
        server = StandIn()
        self.addCleanup(server.close)
        self.a.config["t4_lobby_server"] = f"127.0.0.1:{server.port}"
        self.a.set_text_value("support_note", "Froze after intro")
        self.a.set_text_value("support_contact", "Fixture#123")
        nav = Nav([Game(self.a.m, self.a)], language="en")
        nav.screen = "hub"
        nav.sec["t4"] = "support"
        self.assertIn("support", nav.sections())
        self.assertEqual(nav.items()[0]["id"], "send")
        nav.act("confirm", device="xbox")
        state = self.finish()
        self.assertEqual(state["error"], "")
        self.assertEqual(state["sent"], "K7QF2M")
        got = server.got[0]
        self.assertTrue(got["ok"])
        self.assertEqual(got["meta"]["game"], "Tekken 4 Online")
        self.assertEqual(got["meta"]["description"], "Froze after intro")
        self.assertEqual(got["meta"]["contact"], "Fixture#123")
        self.assertEqual(got["meta"]["name"], "FixturePlayer")
        self.assertEqual(got["meta"]["name_kind"], "account")
        self.assertEqual(got["meta"]["build_id"], "0123456789abcdef")
        with zipfile.ZipFile(io.BytesIO(got["data"])) as archive:
            self.assertIn("contents.txt", archive.namelist())
            self.assertNotIn(b"192.0.2.12", b"".join(archive.read(n) for n in archive.namelist()))
        self.assertFalse(list(self.home.glob("t4-report-*")))
        self.assertFalse(list(self.home.rglob("*.zip")))

    def test_old_server_hides_send_and_pad_can_save(self):
        server = StandIn(takes=False)
        self.addCleanup(server.close)
        self.a.config["t4_lobby_server"] = f"127.0.0.1:{server.port}"
        self.assertTrue(self.a.support_start("send"))
        state = self.finish()
        self.assertFalse(state["send_available"])
        self.assertFalse(server.got)
        nav = Nav([Game(self.a.m, self.a)], language="en")
        nav.screen, nav.sec["t4"] = "hub", "support"
        self.assertEqual(nav.items()[0]["id"], "report")
        nav.act("confirm", device="xbox")
        self.assertIn("Nothing is sent", nav.view()["dialog"]["text"])
        nav.act("right", device="xbox")
        nav.act("confirm", device="xbox")
        state = self.finish()
        self.assertTrue(Path(state["report"]).is_file())
        self.assertFalse(server.got)

    def test_failed_send_keeps_save_and_removes_temporary_zip(self):
        server = StandIn(refuse="rate_limited")
        self.addCleanup(server.close)
        self.a.config["t4_lobby_server"] = f"127.0.0.1:{server.port}"
        self.a.support_start("send")
        self.assertTrue(self.finish()["error"])
        self.assertFalse(list(self.home.glob("t4-report-*")))
        self.a.support_start("report")
        state = self.finish()
        self.assertEqual(state["error"], "")
        self.assertTrue(Path(state["report"]).is_file())

    def test_server_selection_uses_t4_default_and_tls_pin(self):
        self.a.config.clear()
        self.a.config["t5_lobby_server"] = "wrong.example.invalid:7781"
        self.a._t4_listed_entries = lambda: {"T4 fixture": {
            "name": "T4 fixture", "host": "t4.example.invalid", "default": True,
            "tls": "pin", "fingerprint": "ab" * 32}}
        self.assertEqual(self.a._support_server(), ("t4.example.invalid", 7791, "pin", "ab" * 32))

    def test_saved_t4_server_and_separate_pin_work_without_opening_online_page(self):
        self.a.config.clear()
        self.a._online_config = lambda: {"server": "saved-t4.example.invalid:7791", "fingerprint": "cd" * 32}
        self.assertFalse(hasattr(self.a, "_online_fields"))
        self.assertEqual(self.a._support_server(), ("saved-t4.example.invalid", 7791, "pin", "cd" * 32))

    def test_page_probe_hides_send_on_old_server_before_an_upload(self):
        server = StandIn(takes=False)
        self.addCleanup(server.close)
        self.a.config["t4_lobby_server"] = f"127.0.0.1:{server.port}"
        self.a.support_probe()
        deadline = time.monotonic() + 10
        while getattr(self.a, "_support_probing", False) and time.monotonic() < deadline:
            threading.Event().wait(0.01)
        self.assertIs(self.a.support_state()["send_available"], False)
        self.assertFalse(server.got)
        self.assertFalse(list(self.home.rglob("*.zip")))

    def test_unbuilt_install_and_malformed_identity_can_still_save_offline(self):
        self.write(self.root / "logs" / "latest" / "build_identity.json", "invalid JSON")
        self.a.core.find_runtime = lambda settings: (None, "not built")
        with mock.patch("openrecomp.report_upload.upload", side_effect=AssertionError("save must stay local")):
            self.a.support_start("report")
            state = self.finish()
        self.assertEqual(state["error"], "")
        with zipfile.ZipFile(state["report"]) as archive:
            self.assertEqual(json.loads(archive.read("build_identity.json")), {"available": False})

    def test_cleaner_handles_other_profiles_escaped_paths_and_key_spellings(self):
        cleaner = t4_report.Cleaner(private=("xy",))
        for raw, hidden in (("/home/OtherUser/game/log", "OtherUser"),
                            (r"C:\Users\Other User\game", "Other User"),
                            (r"C:\\Users\\OtherUser\\game", "OtherUser"),
                            ("user_name=OtherUser", "OtherUser"),
                            ("computer_name=OtherPC", "OtherPC"),
                            ("xy", "xy")):
            with self.subTest(raw=raw):
                self.assertNotIn(hidden, cleaner.text(raw))
        self.assertEqual(cleaner.text("NETSUMMARY rollback=2 compiler MSVC 19.44"),
                         "NETSUMMARY rollback=2 compiler MSVC 19.44")

    def test_note_and_contact_are_controller_editable_in_both_online_modes(self):
        for mode in ("direct", "lobby"):
            self.a.config["t4_online_mode"] = mode
            nav = Nav([Game(self.a.m, self.a)], language="en")
            nav.screen, nav.sec["t4"] = "hub", "support"
            with mock.patch.object(self.a, "support_probe"):
                nav.act("down", device="xbox")
                nav.act("confirm", device="xbox")
                self.assertEqual(nav.osk["tid"], "support_note")
                nav.type_text("Froze")
                nav.act("play", device="xbox")
                self.assertIn("Froze", self.a.text_value("support_note"))
                nav.act("down", device="xbox")
                nav.act("confirm", device="xbox")
                self.assertEqual(nav.osk["tid"], "support_contact")
                nav.type_text("Pad#123")
                nav.act("play", device="xbox")
                self.assertIn("Pad#123", self.a.text_value("support_contact"))

    def test_t4_report_page_renders_offscreen_in_all_seven_catalogs(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
        from openrecomp.app import UI_DIR
        from test_ui_loads import FakeBackend, spin

        app = QGuiApplication.instance() or QGuiApplication([])
        nav = Nav([Game(self.a.m, self.a)], language="en")
        nav.screen, nav.sec["t4"] = "hub", "support"
        backend = FakeBackend(nav)
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda messages: warnings.extend(m.toString() for m in messages))
        engine.setInitialProperties({"backend": backend, "wantFull": False})
        with mock.patch.object(self.a, "support_probe"):
            engine.load(QUrl.fromLocalFile(os.path.join(UI_DIR, "Main.qml")))
            self.assertTrue(engine.rootObjects(), warnings)
            self.assertEqual(len(i18n.LANGUAGES), 7)
            for language in i18n.LANGUAGES:
                nav.language = language
                backend._v = nav.view()
                backend.viewChanged.emit()
                spin()
                for suffix in ("save", "hint", "confirm", "notice"):
                    key = "t4.support." + suffix
                    self.assertIn(key, i18n.catalog(language))
                    if language != "en":
                        self.assertNotEqual(i18n.catalog(language)[key], i18n.catalog("en")[key])
                self.assertNotIn("@t4.support", str(backend._v))
        self.assertEqual(warnings, [])
        del engine
        del app


if __name__ == "__main__":
    unittest.main()
