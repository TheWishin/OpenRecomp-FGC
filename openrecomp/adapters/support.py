"""The installed T5DR launcher's local checks and report writer, and "Send to the developer".

Send makes the same cleaned zip as the installed launcher's "Save report" (its problem_report.py), small enough for
the developer's Discord post, and uploads it with openrecomp/report_upload.py to the install's own lobby server (the
default of its lobby/servers.json; the server's reports.py). Nothing is sent before the player presses Send. A server
that takes no reports (older than 1.2.x) answers the page's check that way: the Send rows go, Save stays.
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading

from .. import report_upload
from ..community import LAUNCHER_NAME
from .t5_coexist import readonly_imports

SEND_TARGET = 7900 * 1024       # what fits the developer's Discord post (the server's T5L_REPORT_WEBHOOK_MAX_KB)
NOTE_MAX = 300
CONTACT_MAX = 80


FINDINGS = {
    "package_version": ("@support.finding.package_version.title", "@support.finding.package_version.fix"),
    "package_damaged": ("@support.finding.package_damaged.title", "@support.finding.package_damaged.fix"),
    "unpack_memory": ("@support.finding.unpack_memory.title", "@support.finding.unpack_memory.fix"),
    "eu_offline": ("@support.finding.eu_offline.title", "@support.finding.eu_offline.fix"),
    "gpu_tier1": ("@support.finding.gpu_tier1.title", "@support.finding.gpu_tier1.fix"),
    "two_cores": ("@support.finding.two_cores.title", "@support.finding.two_cores.fix"),
    "wine": ("@support.finding.wine.title", "@support.finding.wine.fix"),
    "firewall": ("@support.finding.firewall.title", "@support.finding.firewall.fix"),
}


class T5Support:
    def _support_import(self, name):
        path = os.path.realpath(os.path.join(self.root, "launcher", name + ".py"))
        if not os.path.isfile(path):
            raise ImportError("@support.unavailable")
        cached = sys.modules.get(name)
        if cached is not None:
            if os.path.normcase(os.path.realpath(getattr(cached, "__file__", ""))) != os.path.normcase(path):
                raise ImportError("@support.unavailable")
            return cached
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            with readonly_imports():
                spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(name, None)
            raise
        return module

    def _support_runtime(self):
        modules = getattr(self, "_support_modules", None)
        if modules is None:
            # problem_check imports problem_report by name; load and verify that dependency first.
            cached = sys.modules.get("replays")
            expected = os.path.realpath(os.path.join(self.root, "launcher", "replays.py"))
            if cached is not None and os.path.normcase(os.path.realpath(getattr(cached, "__file__", ""))) != os.path.normcase(expected):
                raise ImportError("@support.unavailable")
            report = self._support_import("problem_report")
            check = self._support_import("problem_check")
            modules = self._support_modules = (check, report)
        return modules

    def support_available(self):
        try:
            check, report = self._support_runtime()
            return (callable(getattr(check, "check", None))
                    and all(callable(getattr(report, name, None))
                            for name in ("Context", "settings_lines", "build_info_for", "discover", "build"))
                    and callable(getattr(self.core, "desktop_dir", None)))
        except Exception:  # a missing optional module never prevents launching the game
            return False

    def support_state(self):
        state = getattr(self, "_support_status", None)
        if state is None:
            state = dict(running=False, operation="", checked=False, findings=[], report="", error="")
        state.setdefault("note", "")
        state.setdefault("contact", "")
        state.setdefault("sent", "")
        if getattr(self, "_support_send_ok", None) is False:
            state["send_available"] = False
        state.setdefault("send_available", None)
        return dict(state, findings=[dict(f) for f in state["findings"]])

    # ---------------------------------------------------------------- Send to the developer
    def _support_server(self):
        """(host, port, tls, fingerprint) of the install's own lobby server, or None. OPENRECOMP_REPORT_SERVER=host:port
        (plain TCP: tests and a local lobby only) sends elsewhere."""
        test = os.environ.get("OPENRECOMP_REPORT_SERVER", "").strip()
        if test:
            host, _sep, port = test.rpartition(":")
            return (host, int(port), "off", "") if host and port.isdigit() else None
        try:
            with open(os.path.join(self.root, "lobby", "servers.json"), encoding="utf-8") as stream:
                doc = json.load(stream)
        except (OSError, ValueError, TypeError):
            return None
        entries = [e for e in (doc.get("servers") if isinstance(doc, dict) else None) or []
                   if isinstance(e, dict) and str(e.get("host") or "").strip()]
        entry = next((e for e in entries if e.get("default")), entries[0] if entries else None)
        if entry is None:
            return None
        fp = str(entry.get("fingerprint") or "").replace(":", "").strip().lower()
        tls = str(entry.get("tls") or ("pin" if fp else "off"))
        try:
            port = int(entry.get("port", 7781))
        except (TypeError, ValueError):
            return None
        return str(entry["host"]).strip(), port, tls, fp

    def support_send_info(self):
        """dict(server) when this install has a server to send to, else None (the page shows Save only)."""
        server = self._support_server()
        return dict(server=server[0]) if server else None

    def support_probe(self):
        """Ask the server once whether it takes reports (an older one does not); the page hides Send if not."""
        if getattr(self, "_support_probing", False) or getattr(self, "_support_send_ok", None) is not None:
            return
        server = self._support_server()
        if server is None:
            self._support_send_ok = False
            return
        self._support_probing = True

        def work():
            try:
                self._support_send_ok = report_upload.server_takes_reports(*server, timeout=8.0) > 0
            except Exception:  # offline now: Send stays; sending says what is wrong
                pass
            self._support_probing = False
        threading.Thread(target=work, daemon=True).start()

    def support_text_value(self, tid):
        state = self.support_state()
        return {"support_note": state["note"], "support_contact": state["contact"]}.get(tid, "")

    def set_support_text_value(self, tid, value):
        state = self.support_state()
        if tid == "support_note":
            state["note"] = " ".join(str(value).split())[:NOTE_MAX]
        elif tid == "support_contact":
            state["contact"] = " ".join(str(value).split())[:CONTACT_MAX]
        self._support_status = state

    def _support_identity(self):
        """(lobby name, "account" | "guest" | "") the online settings know, for the report's facts."""
        try:
            cfg = self._online_config()
        except Exception:  # no online settings: sent without a name
            return "", ""
        if not isinstance(cfg, dict):
            return "", ""
        sessions = cfg.get("sessions") if isinstance(cfg.get("sessions"), dict) else {}
        for saved in sessions.values():
            if isinstance(saved, dict) and saved.get("token") and saved.get("name"):
                return str(saved["name"])[:32], "account"
        name = str(cfg.get("name") or "").strip()[:32]
        return (name, "guest") if name else ("", "")

    def support_start(self, kind="check"):
        if kind not in ("check", "report", "send") or not self.support_available():
            raise RuntimeError("@support.unavailable")
        state = self.support_state()
        if state["running"]:
            return False
        state.update(running=True, operation=kind, error="")
        if kind == "send":
            state["sent"] = ""
        self._support_status = state
        try:
            threading.Thread(target=self._support_work, args=(kind,), daemon=True).start()
        except Exception as e:
            state.update(running=False, error=self.message("support.failed", error=str(e)))
            self._support_status = state
            return False
        return True

    def _support_work(self, kind):
        state = self.support_state()
        try:
            check, report = self._support_runtime()
            if kind == "check":
                findings = []
                for finding in check.check(self.s.out_dir):
                    label, fix = FINDINGS.get(finding.key, ("@support.finding.unknown.title", "@support.finding.unknown.fix"))
                    findings.append(dict(id=finding.key, label=label, seen="", fix=fix,
                                         kind=getattr(finding, "kind", "problem")))
                state.update(checked=True, findings=findings)
            elif kind == "send":
                state.update(sent=self._support_send(report, state))
            else:
                dest = self.core.desktop_dir()
                # Reports belong to the player's folder, never the public launcher checkout.
                checkout = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
                if not dest or not os.path.isabs(dest):
                    raise RuntimeError("@support.unavailable")
                dest = os.path.realpath(dest)
                try:
                    inside_checkout = os.path.commonpath((checkout, dest)) == checkout
                except ValueError:  # the player's Desktop can be on another drive
                    inside_checkout = False
                if inside_checkout:
                    raise RuntimeError("@support.unavailable")
                release = self.release()
                context = report.Context(
                    self.s.out_dir, root=self.root,
                    launcher_log=os.path.join(self.root, "launcher.log"),
                    settings_lines=report.settings_lines(self.s, out_dir=self.s.out_dir),
                    release=release,
                    build_info=lambda: report.build_info_for(self.s.out_dir, release, self.root),
                    online_dir=os.path.dirname(self.online_cfg_path()))
                groups = report.discover(context)
                result = report.build(context, dest, groups=groups)
                state.update(report=result.path)
        except report_upload.ReportError as e:  # Save stays; an older server hides Send from now on
            if e.code in ("unsupported", "reports_off"):
                self._support_send_ok = False
                state["send_available"] = False
            state["error"] = self._support_send_error(e)
        except Exception as e:  # the UI keeps the last findings and lets the player retry
            state["error"] = self.message("support.failed", error=str(e))
        state["running"] = False
        now = getattr(self, "_support_status", None) or {}       # (what the player typed meanwhile is kept)
        state["note"], state["contact"] = now.get("note", state.get("note", "")), now.get("contact", state.get("contact", ""))
        self._support_status = state

    def _support_send_error(self, e):
        """What the page says when Send did not work (report_upload.ReportError codes); Save stays."""
        if e.code in ("unsupported", "reports_off"):
            return self.message("support.send.unsupported")
        if e.code in ("rate_limited",):
            return self.message("support.send.rate")
        if e.code in ("report_size",):
            return self.message("support.send.too_big")
        if e.code in ("connect_failed", "timeout", "disconnected", "tls_mismatch"):
            return self.message("support.send.offline")
        return self.message("support.send.failed", error=e.msg or e.code)

    def _support_context(self, report):
        release = self.release()
        return report.Context(
            self.s.out_dir, root=self.root,
            launcher_log=os.path.join(self.root, "launcher.log"),
            settings_lines=report.settings_lines(self.s, out_dir=self.s.out_dir),
            release=release,
            build_info=lambda: report.build_info_for(self.s.out_dir, release, self.root),
            online_dir=os.path.dirname(self.online_cfg_path())), release

    def _support_send(self, report, state):
        """Make the zip in a folder of its own, small enough for the Discord post, send it, remove it. -> report id."""
        server = self._support_server()
        if server is None:
            raise report_upload.ReportError(report_upload.UNSUPPORTED)
        context, release = self._support_context(report)
        note = state.get("note", "")
        tmp = tempfile.mkdtemp()
        try:
            if callable(getattr(report, "build_for_send", None)):
                result = report.build_for_send(context, tmp, note)
            else:       # an installed launcher before 1.2.x: the same zip, made smaller by its cap
                cap = getattr(report, "DEFAULT_CAP", 20 << 20)
                for _ in range(5):
                    result = report.build(context, tmp, note, cap=cap)
                    size = os.path.getsize(result.path)
                    if size <= SEND_TARGET:
                        break
                    os.remove(result.path)
                    cap = max(64 << 10, int(cap * SEND_TARGET / size * 0.85))
            try:
                info = context.build_info or {}
            except Exception:  # not built: no build id
                info = {}
            name, kind = self._support_identity()
            meta = dict(game="T5DR Online", version=str(release.get("version") or ""),
                        build_id=str(info.get("build_id") or ""), os=self._support_os(report), description=note,
                        contact=state.get("contact", ""), name=name, name_kind=kind, launcher=LAUNCHER_NAME,
                        language=str(self.config.get("language") or ""))
            reply = report_upload.upload(server[0], server[1], result.path, meta, server[2], server[3],
                                         build=dict(id=meta["build_id"], release=meta["version"]))
            return str(reply.get("id") or "")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @staticmethod
    def _support_os(report):
        try:
            return str(report.windows_version())
        except Exception:  # an older or partial installed report module
            import platform
            return platform.platform()
