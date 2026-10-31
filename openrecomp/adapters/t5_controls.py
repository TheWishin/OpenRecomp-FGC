"""Controller editing delegated to the installed launcher's editor and device reader."""
import importlib.util
import os
import sys
import tempfile
import time

from .base import add_path
from .t5_coexist import readonly_imports


class Controls:
    def _controls_import(self, name, path):
        path = os.path.realpath(path)
        cached = sys.modules.get(name)
        if cached is not None:
            if not self._controls_origin(cached, path):
                raise ImportError("@controls.unsupported")
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

    def _controls_api(self):
        if hasattr(self, "_controls_modules"):
            return self._controls_modules
        self._controls_modules = None
        launcher = os.path.join(self.root, "launcher")
        if not all(os.path.isfile(os.path.join(launcher, name)) for name in ("controls_edit.py", "controls_ui.py")):
            return None
        try:
            add_path(os.path.join(self.root, "lobby"))
            add_path(launcher)
            names = ("t5lobby", "t5lobby.padmap", "t5lobby.padnav", "controls_edit", "controls_ui")
            paths = (os.path.join(self.root, "lobby", "t5lobby", "__init__.py"),
                     os.path.join(self.root, "lobby", "t5lobby", "padmap.py"),
                     os.path.join(self.root, "lobby", "t5lobby", "padnav.py"),
                     os.path.join(launcher, "controls_edit.py"), os.path.join(launcher, "controls_ui.py"))
            for name, path in zip(names, paths):
                module = sys.modules.get(name)
                if module is not None and not self._controls_origin(module, path):
                    return None
            modules = []
            for name, path in zip(names, paths):
                module = self._controls_import(name, path)
                if not self._controls_origin(module, path):
                    return None
                modules.append(module)
            _package, pm, pn, ce, ui = modules
            required = ((ce, ("DeviceRef", "controls_path", "mask_text")),
                        (ce.ControlsEditor, ("load", "controls", "sources", "table", "bind", "save")),
                        (ui.DevicePoller, ("step", "drain")), (ui.Capture, ("update",)),
                        (pm.PortMap, ("update",)), (pn, ("default_sources",)))
            if not all(callable(getattr(owner, name, None)) for owner, attrs in required for name in attrs):
                return None
            if not ce.SLOTS or not ce.SCOPE_PORT or not all(slot.key and slot.mask for slot in ce.SLOTS):
                return None
            self._controls_modules = (ce, ui, pm, pn)
        except Exception:  # optional installed modules must never prevent the launcher from opening
            return None
        return self._controls_modules

    @staticmethod
    def _controls_origin(module, path):
        return os.path.normcase(os.path.realpath(getattr(module, "__file__", ""))) == os.path.normcase(os.path.realpath(path))

    def controls_supported(self):
        return self._controls_api() is not None

    def _controls_open(self):
        if getattr(self, "_controls_session", None) is not None:
            return self._controls_session
        api = self._controls_api()
        if api is None:
            raise RuntimeError("@controls.unsupported")
        ce, ui, pm, pn = api
        env = self.s.env_overrides()
        editor = ce.ControlsEditor.load(ce.controls_path(self.s.out_dir, env))
        session = dict(editor=editor, ports=pm.PortMap(editor.controls()), active=True,
                       capture=None, pending=None, state=dict(state="idle"), devices={})
        session["poller"] = ui.DevicePoller(pn.default_sources(), foreground=lambda: session["active"],
                                            controls=lambda: session["editor"].controls())
        self._controls_session = session
        return session

    @staticmethod
    def _control_label(key):
        return {"1": "@controls.slot.1", "2": "@controls.slot.2", "3": "@controls.slot.3", "4": "@controls.slot.4",
                "START": "@controls.slot.START", "SELECT": "@controls.slot.SELECT", "UP": "@controls.slot.UP",
                "DOWN": "@controls.slot.DOWN", "LEFT": "@controls.slot.LEFT", "RIGHT": "@controls.slot.RIGHT"}.get(key, key)

    def controls(self):
        session = getattr(self, "_controls_session", None)
        if session is None:
            return []
        ce = self._controls_modules[0]
        rows = []
        for key, dev in session["devices"].items():
            ref = ce.DeviceRef(dev.kind, session["ports"].port.get(key, -1), dev.vid, dev.pid)
            slots = [dict(id=slot.key, label=self._control_label(slot.key),
                          value=" / ".join(session["editor"].sources(ref, slot.key)) or "@controls.unbound")
                     for slot in ce.SLOTS]
            rows.append(dict(id=key, name=dev.name, port=ref.port,
                             label=self.message("controls.pad", port=ref.port + 1, name=dev.name)
                             if ref.port >= 0 else self.message("controls.unassigned", name=dev.name),
                             slots=slots, disabled=ref.port < 0))
        return rows

    def begin_binding(self, pad_id, slot_id):
        if self.running():
            raise RuntimeError("@controls.running")
        session = self._controls_open()
        self.poll_binding()
        ce, ui, _pm, _pn = self._controls_modules
        dev = session["devices"].get(pad_id)
        port = session["ports"].port.get(pad_id, -1)
        if dev is None or port < 0:
            raise RuntimeError("@controls.disconnected")
        if slot_id not in {slot.key for slot in ce.SLOTS}:
            raise ValueError("@controls.unsupported")
        session["poller"].drain()
        session["capture"] = ui.Capture(time.monotonic(), timeout_s=8.0,
                                         held=session["poller"].held.get(pad_id))
        session["pending"] = dict(pad=pad_id, slot=slot_id,
                                  dev=ce.DeviceRef(dev.kind, port, dev.vid, dev.pid), deadline=time.monotonic() + 8.0)
        session["state"] = dict(state="waiting")

    def poll_binding(self, active=True):
        session = getattr(self, "_controls_session", None)
        if session is None:
            if not active or not self.controls_supported():
                return dict(state="idle")
            session = self._controls_open()
        session["active"] = bool(active)
        poller = session["poller"]
        now = time.monotonic()
        poller.step(now)
        if not active:
            poller.drain()
            return session["state"]
        session["devices"] = {dev.key: dev for dev in poller.devices}
        session["ports"].update(poller.devices, session["editor"].controls())
        edges = poller.drain()
        pending = session["pending"]
        if pending is not None:
            dev = session["devices"].get(pending["pad"])
            ref = pending["dev"]
            if dev is None or session["ports"].port.get(dev.key, -1) != ref.port or (dev.kind, dev.vid, dev.pid) != (ref.kind, ref.vid, ref.pid):
                session["capture"] = session["pending"] = None
                session["state"] = dict(state="disconnected")
        if session["capture"] is not None:
            if now >= pending["deadline"]:
                session["capture"] = session["pending"] = None
                session["state"] = dict(state="timeout")
                return dict(session["state"])
            result = session["capture"].update(now, [edge for edge in edges if edge.key == pending["pad"]],
                                                held=poller.held.get(pending["pad"]))
            if result is not None:
                state, source = result
                if state == "ok":
                    ce = self._controls_modules[0]
                    old = session["editor"].table(pending["dev"]).mask_of(source)
                    target = next(slot.mask for slot in ce.SLOTS if slot.key == pending["slot"])
                    conflicts = [self._control_label(slot.key) for slot in ce.SLOTS if slot.mask == old and old != target]
                    if old and old != target and not conflicts:
                        conflicts = [ce.mask_text(old)]
                    pending["source"] = source
                    session["capture"] = None
                    session["state"] = dict(state="conflict" if conflicts else "ready", source=source, conflicts=conflicts)
                elif state == "multi":
                    ui = self._controls_modules[1]
                    session["capture"] = ui.Capture(now, timeout_s=max(0.0, pending["deadline"] - now),
                                                     held=poller.held.get(pending["pad"]))
                    session["state"] = dict(state="multi")
                else:
                    session["capture"] = session["pending"] = None
                    session["state"] = dict(state="timeout")
        return dict(session["state"])

    def accept_binding(self):
        if self.running():
            raise RuntimeError("@controls.running")
        session = self._controls_open()
        self.poll_binding()
        pending = session["pending"]
        if pending is None or "source" not in pending:
            raise RuntimeError("@controls.disconnected")
        ce = self._controls_modules[0]
        read_path = session["editor"].path
        temporary = None
        try:
            # The installed editor keeps unknown fields. Publish private edits only
            # after its complete save succeeds, keeping existing bindings on failure.
            target = getattr(self.s, "controls_write_path", None)
            if target is not None:
                folder = os.path.dirname(target)
                os.makedirs(folder, exist_ok=True)
                target = self.s.controls_write_path
                with tempfile.NamedTemporaryFile(dir=folder, prefix=".controls-", suffix=".json", delete=False) as stream:
                    temporary = stream.name
                session["editor"].path = temporary
            session["editor"].bind(pending["dev"], ce.SCOPE_PORT, pending["slot"], [pending["source"]])
            session["editor"].save()
            if target is not None:
                os.replace(temporary, self.s.controls_write_path)
                session["editor"].path = target
        except Exception:
            session["editor"] = ce.ControlsEditor.load(read_path)
            self.cancel_binding()
            raise
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)
        session["capture"] = session["pending"] = None
        session["state"] = dict(state="done")

    def cancel_binding(self):
        session = getattr(self, "_controls_session", None)
        if session is not None:
            session["capture"] = session["pending"] = None
            session["state"] = dict(state="idle")
            session["poller"].drain()

    def controls_close(self):
        session = getattr(self, "_controls_session", None)
        if session is not None:
            self.poll_binding(active=False)
            self._controls_session = None
