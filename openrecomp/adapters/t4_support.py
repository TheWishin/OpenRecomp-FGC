"""T4's problem report uses the common page and lobby upload, without requiring a built game or login."""
import os
import platform
import tempfile
from pathlib import Path

from .support import T5Support
from .. import report_upload, t4_report
from ..community import LAUNCHER_NAME
from ..manifest import user_dir
from ..vendor.t4lobby import servers


class T4Support(T5Support):
    def support_available(self):
        return bool(self.root)

    def support_state(self):
        return dict(super().support_state(), check_available=False,
                    report_label="@t4.support.save", report_hint="@t4.support.hint",
                    confirm_text="@t4.support.confirm", send_notice="@t4.support.notice")

    def text_value(self, tid):
        if tid.startswith("support_"):
            return self.support_text_value(tid)
        return super().text_value(tid)

    def set_text_value(self, tid, value):
        if tid.startswith("support_"):
            self.set_support_text_value(tid, value)
            return
        super().set_text_value(tid, value)

    def _support_server(self):
        override = os.environ.get("OPENRECOMP_REPORT_SERVER", "").strip()
        try:
            if override:
                entry = servers.parse_address(override)
            else:
                # Exactly the T4 lobby's selected/default endpoint and certificate policy; never T5DR's.
                fields = getattr(self, "_online_fields", {})
                cfg = self._online_config()
                selected = (self._t4_explicit_server() or fields.get("online_server")
                            or cfg.get("server") or self._online_default_server())
                if not selected:
                    return None
                listed = self._t4_listed_entries().get(selected)
                entry = servers.ServerEntry.from_json(listed) if listed else servers.parse_address(selected)
                fingerprint = fields.get("online_fingerprint", cfg.get("fingerprint"))
                if entry.tls != "pin" and fingerprint:
                    entry = servers.ServerEntry(entry.name, entry.host, entry.port, "pin", fingerprint)
            return entry.host, entry.port, entry.tls, entry.fingerprint
        except (ValueError, TypeError):
            return None

    def _support_private(self):
        values = []

        def collect(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if t4_report.PRIVATE_KEY.search(str(key)) and isinstance(child, str):
                        values.append(child)
                    else:
                        collect(child)
            elif isinstance(value, (list, tuple)):
                for child in value:
                    collect(child)

        collect(self.config)
        collect(getattr(self, "_online_fields", {}))
        values.append(getattr(self, "_online_name", ""))
        try:
            collect(self._online_config())
        except Exception:  # missing online settings never prevent a local report
            pass
        return values

    def _support_work(self, kind):
        state = self.support_state()
        try:
            if kind not in ("report", "send"):
                raise RuntimeError("@support.unavailable")
            home = user_dir()
            dest = Path(home) / "reports"
            # A send's zip lives only until its own connection has finished, including on failure.
            Path(home).mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="t4-report-", dir=home) as temporary:
                path = t4_report.build(self.root, home, temporary if kind == "send" else dest,
                                       note=state.get("note", ""), private=self._support_private(),
                                       build_lines=list(self.build_lines), save_dir=getattr(self.core, "SAVE_DIR", None),
                                       version=self._t4_release())
                if kind == "report":
                    state["report"] = path
                else:
                    server = self._support_server()
                    if server is None:
                        raise report_upload.ReportError(report_upload.UNSUPPORTED)
                    name, name_kind = self._support_identity()
                    identity = self._direct_local_identity()
                    meta = dict(game="Tekken 4 Online", version=self._t4_release(),
                                build_id=str(identity.get("build_id") or ""),
                                os=platform.system() + " " + platform.release(), description=state.get("note", ""),
                                contact=state.get("contact", ""), name=name, name_kind=name_kind,
                                launcher=LAUNCHER_NAME, language=str(self.config.get("language") or ""))
                    state["sent"] = report_upload.upload(*server[:2], path, meta, *server[2:],
                                                         build=dict(id=meta["build_id"], release=meta["version"]))["id"]
        except report_upload.ReportError as error:
            if error.code in ("unsupported", "reports_off"):
                self._support_send_ok = False
                state["send_available"] = False
            state["error"] = self._support_send_error(error)
        except Exception:  # no raw paths or credentials in error messages
            state["error"] = self.message("support.send.failed", error="@support.unavailable")
        state["running"] = False
        now = getattr(self, "_support_status", None) or {}
        state["note"], state["contact"] = now.get("note", state["note"]), now.get("contact", state["contact"])
        self._support_status = state
