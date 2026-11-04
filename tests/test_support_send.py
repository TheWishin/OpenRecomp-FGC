"""Problem report page: "Send to the developer" (adapters/support.py + openrecomp/report_upload.py) and the
OpenRecomp-FGC Discord button (community.py, nav, drawer). The server is a stand-in on 127.0.0.1 that speaks the
lobby's report protocol (T5DR lobby/t5lobby/server/reports.py); no real lobby, no browser, no internet."""
import hashlib
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import unittest
import zipfile
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from openrecomp import report_upload  # noqa: E402
from openrecomp.adapters.base import Adapter  # noqa: E402
from openrecomp.adapters.support import T5Support  # noqa: E402
from openrecomp.community import DISCORD_URL  # noqa: E402
from openrecomp.nav import Game, Nav  # noqa: E402
from test_nav import Fake, manifest  # noqa: E402


class StandIn:
    """The lobby's report protocol, minimal: hello -> report_begin -> report_data + bytes -> report_done."""

    def __init__(self, takes=True, refuse=None):
        self.takes, self.refuse = takes, refuse
        self.got = []
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def close(self):
        self.sock.close()

    def _serve(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._one, args=(c,), daemon=True).start()

    def _one(self, c):
        f = c.makefile("rb")
        try:
            begin = None
            while True:
                line = f.readline()
                if not line:
                    return
                m = json.loads(line)
                rid = m.get("rid")
                if m["t"] == "hello":
                    w = {"t": "welcome", "re": rid, "features": ["problem_reports"] if self.takes else []}
                    if self.takes:
                        w["reports"] = {"v": 1, "max_bytes": 15 << 20}
                    c.sendall(json.dumps(w).encode() + b"\n")
                elif m["t"] == "report_begin":
                    if self.refuse:
                        c.sendall(json.dumps({"t": "error", "re": rid, "code": self.refuse, "msg": "no"}).encode() + b"\n")
                        continue
                    begin = m
                    c.sendall(json.dumps({"t": "report_go", "re": rid, "id": "K7QF2M"}).encode() + b"\n")
                elif m["t"] == "report_data":
                    data = f.read(begin["size"])
                    ok = hashlib.sha256(data).hexdigest() == begin["sha256"]
                    self.got.append(dict(meta=begin["meta"], data=data, ok=ok))
                    c.sendall(json.dumps({"t": "report_done", "re": rid, "id": "K7QF2M", "webhook": True}).encode() + b"\n")
        finally:
            c.close()


def fake_report(dest_files):
    def build_for_send(ctx, dest, note="", enabled=None):
        path = os.path.join(dest, "T5DR-report.zip")
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("contents.txt", "report\n")
            z.writestr("report.txt", note)
        dest_files.append(path)
        return SimpleNamespace(path=path, zip_size=os.path.getsize(path))
    return SimpleNamespace(
        Context=mock.Mock(side_effect=lambda *a, **k: SimpleNamespace(out_dir=a[0], **dict(k, build_info={"build_id": "b1d"}))),
        settings_lines=mock.Mock(return_value=[]), build_info_for=mock.Mock(return_value={"build_id": "b1d"}),
        discover=mock.Mock(return_value=[]), build=mock.Mock(), build_for_send=build_for_send,
        windows_version=lambda: "Windows 11 (test)")


class FakeT5(T5Support, Adapter):
    def __init__(self, root):
        super().__init__(dict(id="t5dr", short="T5DR"), {"language": "de"})
        self.root = root
        self.s = SimpleNamespace(out_dir=os.path.join(root, "native"))
        self.core = SimpleNamespace(desktop_dir=lambda: root)
        self.check = SimpleNamespace(check=mock.Mock(return_value=[]))
        self.files = []
        self.report = fake_report(self.files)
        self._support_modules = (self.check, self.report)

    def release(self):
        return dict(version="1.2.1")

    def online_cfg_path(self):
        return os.path.join(self.root, "online", "online.json")

    def _online_config(self):
        return {"name": "Zed", "sessions": {"x": {"name": "Zed", "token": "t"}}}


class AdapterSend(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="or-send-")
        self.addCleanup(shutil.rmtree, self.d, True)
        os.makedirs(os.path.join(self.d, "lobby"))
        with open(os.path.join(self.d, "lobby", "servers.json"), "w", encoding="utf-8") as f:
            json.dump({"format": "t5dr-servers/1", "servers": [
                {"name": "T5DR Online", "host": "lobby.example.invalid", "port": 7781, "tls": "pin",
                 "fingerprint": "ab" * 32, "default": True}]}, f)
        self.a = FakeT5(self.d)

    def run_send(self, server):
        with mock.patch.dict(os.environ, {"OPENRECOMP_REPORT_SERVER": f"127.0.0.1:{server.port}"}):
            self.a.set_support_text_value("support_note", "black screen\nafter the intro")
            self.a.set_support_text_value("support_contact", "Zed#1")
            self.assertTrue(self.a.support_start("send"))
            for _ in range(500):
                if not self.a.support_state()["running"]:
                    break
                threading.Event().wait(0.02)
        return self.a.support_state()

    def test_the_install_server_is_the_default_entry(self):
        self.assertEqual(self.a._support_server(), ("lobby.example.invalid", 7781, "pin", "ab" * 32))
        self.assertEqual(self.a.support_send_info(), {"server": "lobby.example.invalid"})

    def test_send_uploads_the_zip_with_the_facts(self):
        srv = StandIn()
        self.addCleanup(srv.close)
        state = self.run_send(srv)
        self.assertEqual(state["error"], "")
        self.assertEqual(state["sent"], "K7QF2M")
        got = srv.got[0]
        self.assertTrue(got["ok"])
        with zipfile.ZipFile(__import__("io").BytesIO(got["data"])) as z:
            self.assertEqual(z.read("report.txt").decode(), "black screen after the intro")
        meta = got["meta"]
        self.assertEqual((meta["game"], meta["version"], meta["build_id"], meta["os"]),
                         ("T5DR Online", "1.2.1", "b1d", "Windows 11 (test)"))
        self.assertEqual((meta["description"], meta["contact"], meta["name"], meta["name_kind"]),
                         ("black screen after the intro", "Zed#1", "Zed", "account"))
        self.assertEqual(meta["launcher"], "OpenRecomp-FGC")
        self.assertFalse(any(os.path.exists(p) for p in self.a.files))      # the zip went, its copy is gone
        self.assertEqual(state["note"], "black screen after the intro")      # kept for another try

    def test_an_older_server_hides_send(self):
        srv = StandIn(takes=False)
        self.addCleanup(srv.close)
        state = self.run_send(srv)
        self.assertEqual(state["error"], Adapter.message("support.send.unsupported"))
        self.assertFalse(state["send_available"])
        self.assertEqual(srv.got, [])

    def test_rate_limited(self):
        srv = StandIn(refuse="rate_limited")
        self.addCleanup(srv.close)
        state = self.run_send(srv)
        self.assertEqual(state["error"], Adapter.message("support.send.rate"))
        self.assertEqual(state["sent"], "")

    def test_probe_asks_once(self):
        srv = StandIn(takes=False)
        self.addCleanup(srv.close)
        with mock.patch.dict(os.environ, {"OPENRECOMP_REPORT_SERVER": f"127.0.0.1:{srv.port}"}):
            self.a.support_probe()
            for _ in range(200):
                if getattr(self.a, "_support_send_ok", None) is not None:
                    break
                threading.Event().wait(0.02)
        self.assertIs(self.a._support_send_ok, False)
        self.assertFalse(self.a.support_state()["send_available"])

    def test_no_server_file_no_send(self):
        os.remove(os.path.join(self.d, "lobby", "servers.json"))
        self.assertIsNone(self.a.support_send_info())


class SendFake(Fake):
    def __init__(self):
        super().__init__(manifest())
        self.state = dict(running=False, operation="", checked=False, findings=[], report="", error="", note="",
                          contact="", sent="", send_available=None)
        self.probes = 0
        self.texts = {}

    def support_available(self):
        return True

    def support_send_info(self):
        return {"server": "lobby"}

    def support_probe(self):
        self.probes += 1

    def support_start(self, kind="check"):
        self.calls.append(("support", kind))
        self.state = dict(self.state, running=True, operation=kind)
        return True

    def support_state(self):
        return dict(self.state)

    def text_value(self, tid):
        return self.texts.get(tid, "")

    def set_text_value(self, tid, value):
        self.texts[tid] = value
        self.state[{"support_note": "note", "support_contact": "contact"}[tid]] = value


class NavSend(unittest.TestCase):
    def setUp(self):
        self.a = SendFake()
        self.nav = Nav([Game(self.a.m, self.a)], language="en")
        self.nav.screen = "hub"
        self.nav.sec[self.nav.game.id] = "support"

    def test_send_is_first_and_one_press_sends(self):
        ids = [it["id"] for it in self.nav.items()]
        self.assertEqual(ids[:3], ["send", "support_note", "support_contact"])
        self.assertIn("discord", ids)
        v = self.nav.view()
        self.assertEqual(v["detail"]["title"], "Send to the developer")
        self.assertIn("No game files, no keys", v["detail"]["lead"])
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.a.calls, [("support", "send")])
        self.assertGreaterEqual(self.a.probes, 1)

    def test_note_opens_the_keyboard_with_lower_case_keys(self):
        self.nav.act("down", device="xbox")
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.nav.overlay, "osk")
        self.assertEqual(self.nav.osk["tid"], "support_note")
        self.nav.type_text("Froze")
        self.assertEqual(self.nav.osk["text"], "Froze")                      # (not upper-cased)
        self.nav.act("play", device="xbox")
        self.assertEqual(self.a.state["note"], "Froze")
        self.assertEqual(self.nav.items()[1]["value"], "Froze")

    def test_sent_says_thanks_with_the_id(self):
        self.a.state = dict(self.a.state, sent="K7QF2M")
        labels = [str(it["label"]) for it in self.nav.items()]
        self.assertTrue(any("K7QF2M" in str(i18n_view(self.nav, lab)) for lab in labels))

    def test_older_server_hides_send(self):
        self.a.state = dict(self.a.state, send_available=False)
        ids = [it["id"] for it in self.nav.items()]
        self.assertNotIn("send", ids)
        self.assertIn("report", ids)

    def test_dry_send_does_not_send(self):
        self.nav.dry = True
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.a.calls, [])


def i18n_view(nav, value):
    from openrecomp import i18n
    return i18n.localize(value, nav.language)


class DiscordButton(unittest.TestCase):
    def setUp(self):
        self.a = Fake(manifest())
        self.nav = Nav([Game(self.a.m, self.a)], language="en")

    def test_header_label_and_mouse_action(self):
        self.assertEqual(self.nav.view()["discord"], "OpenRecomp-FGC Discord")
        self.nav.act("discord")
        self.assertEqual(self.nav.pending_url, DISCORD_URL)
        self.assertEqual(DISCORD_URL, "https://discord.gg/4DwDHAkk2x")

    def test_quick_access_row_for_pads(self):
        self.nav.act("social", device="xbox")
        rows = self.nav.view()["drawer"]["rows"]
        index = next(r["index"] for r in rows if r["label"] == "OpenRecomp-FGC Discord")
        for _ in range(index):
            self.nav.act("down", device="xbox")
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.nav.pending_url, DISCORD_URL)

    def test_dry_run_opens_nothing(self):
        self.nav.dry = True
        self.nav.act("discord")
        self.assertIsNone(getattr(self.nav, "pending_url", None))

    def test_every_language_names_the_one_server(self):
        from openrecomp import i18n
        for code in i18n.LANGUAGES:
            self.assertEqual(i18n.localize("@community.discord", code), "OpenRecomp-FGC Discord", code)


if __name__ == "__main__":
    unittest.main()
