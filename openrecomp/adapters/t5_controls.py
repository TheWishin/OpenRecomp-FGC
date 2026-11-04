"""Controller editing delegated to the installed launcher's editor and device reader.

The Pad bindings page (nav_controls_page) reads rows from controls() and edits through begin_binding / accept_binding,
apply_preset, reset_controls, clear_binding, set_control_option and set_control_player. Every edit is the installed
editor's own (controls_edit.ControlsEditor), so controls.ini keeps exactly the format the game reads."""
import importlib.util
import inspect
import os
import sys
import tempfile
import time

from .. import i18n, pad_glyphs, pad_presets
from .base import add_path
from .t5_coexist import readonly_imports

CAPTURE_S = 5.0            # "Press a button": the countdown the page shows
HOLD_CANCEL_S = 1.0        # holding the controller's Back button this long cancels a capture or ends the input test
BACK_SOURCE = {"xinput": "B", "dinput": "B3"}     # the launcher's own Back (pad.py): B / Circle
MAX_PLAYERS = 7            # [port1] .. [port7]


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
        session["poller"] = ui.DevicePoller(self._controls_sources(pn), foreground=lambda: session["active"],
                                            controls=lambda: session["editor"].controls())
        self._controls_session = session
        return session

    @staticmethod
    def _controls_sources(pn):
        """The installed reader's pads, and the keyboard too where that reader can read it (T5DR 1.1.2+)."""
        try:
            if "keyboard" in inspect.signature(pn.default_sources).parameters:
                return pn.default_sources(keyboard=True)
        except (TypeError, ValueError):
            pass
        return pn.default_sources()

    # ---------------------------------------------------------------- what the page shows
    @classmethod
    def _control_label(cls, key):
        """An action's name: 1 = Left punch, 1+2 = Left punch + Right punch, L1 = PS3 L1 button."""
        parts = key.split("+")
        if len(parts) > 1 and all(p in ("1", "2", "3", "4") for p in parts):
            label = cls._control_label(parts[0])
            for p in parts[1:]:
                label = i18n.message("controls.slot.join", a=label, b=cls._control_label(p))
            return label
        return {"1": "@controls.slot.1", "2": "@controls.slot.2", "3": "@controls.slot.3", "4": "@controls.slot.4",
                "START": "@controls.slot.START", "SELECT": "@controls.slot.SELECT", "UP": "@controls.slot.UP",
                "DOWN": "@controls.slot.DOWN", "LEFT": "@controls.slot.LEFT", "RIGHT": "@controls.slot.RIGHT"}.get(key) or (
            i18n.message("controls.slot.combo", keys=key) if "+" in key else
            i18n.message("controls.slot.ps3", name=key) if key in ("L1", "R1", "L2", "R2", "L3", "R3") else key)

    @staticmethod
    def _slot_group(slot):
        group = getattr(slot, "group", "")
        if group:
            return group
        key = slot.key
        return ("attack" if key in ("1", "2", "3", "4") else "macro" if "+" in key
                else "dir" if key in ("UP", "DOWN", "LEFT", "RIGHT") else "menu")

    @staticmethod
    def _scope(ce, ref):
        """A keyboard player has one section ([keys1]); a pad's edits go to its player's section ([port1.xinput])."""
        if str(ref.kind).startswith("keys"):
            return getattr(ce, "SCOPE_KIND", "kind")
        return ce.SCOPE_PORT

    def _ref(self, session, key):
        dev = session["devices"].get(key)
        if dev is None:
            return None, None
        port = session["ports"].port.get(key, -1)
        return dev, self._controls_modules[0].DeviceRef(dev.kind, port, dev.vid, dev.pid)

    def _editable(self, key, any_port=False):
        """(session, device, ref) of a connected controller that has a player (`any_port`: or none yet); the game
        must not run."""
        if self.running():
            raise RuntimeError("@controls.running")
        session = self._controls_open()
        dev, ref = self._ref(session, key)
        if dev is None or ref.port < 0 and not any_port:
            raise RuntimeError("@controls.disconnected")
        return session, dev, ref

    def _features(self, session, ref):
        ce = self._controls_modules[0]
        editor = session["editor"]
        pads = not str(ref.kind).startswith("keys")
        return dict(test=True, clear=callable(getattr(editor, "clear", None)), reset=callable(getattr(editor, "reset", None)),
                    presets=callable(getattr(editor, "apply_recipe", None)) and bool(getattr(ce, "RECIPE_BY_ID", None)),
                    options=pads and callable(getattr(editor, "set_port_option", None))
                    and callable(getattr(editor, "socd_of", None)) and callable(getattr(editor, "stick_of", None)),
                    player=callable(getattr(editor, "assign_port" if pads else "assign_keyboard", None)))

    def _presets(self, session, dev, ref):
        """[(id, label)] of pad_presets.PRESETS that the installed editor can apply to this controller."""
        ce = self._controls_modules[0]
        recipes = getattr(ce, "RECIPE_BY_ID", None) or {}
        out = []
        for pid, label, plan in pad_presets.PRESETS:
            step = pad_presets.step(plan, ref.kind)
            if step is None:
                continue
            kind, what = step
            if kind == "recipe" and (what not in recipes or ref.kind not in recipes[what].specs
                                     or not callable(getattr(session["editor"], "apply_recipe", None))):
                continue
            if kind in ("reset", "lines") and not callable(getattr(session["editor"], "reset", None)):
                continue
            out.append((pid, label))
        return out

    def _current_preset(self, session, ref):
        """The preset the controller's bindings equal now, or "custom"."""
        editor = session["editor"]
        for pid, _label, plan in pad_presets.PRESETS:
            step = pad_presets.step(plan, ref.kind)
            if step and step[0] == "lines":
                if all(list(editor.sources(ref, key)) == list(srcs) for key, srcs in pad_presets.LINES[step[1]]):
                    return pid
        detect = getattr(editor, "detect_recipe", None)
        recipe = detect(ref) if callable(detect) else None
        return pad_presets.RECIPE_PRESET.get(recipe, "custom") if recipe else "custom"

    def _pinned(self, session, dev, ref):
        editor = session["editor"]
        if str(ref.kind).startswith("keys"):
            pinned = getattr(editor, "keyboard_pinned", None)
            return pinned(ref.kind) if callable(pinned) else None
        pinned = getattr(editor, "pinned", None)
        if not callable(pinned):
            return None
        spec = pad_presets.device_spec(dev).lower()
        for p in range(MAX_PLAYERS):
            if str(pinned(p) or "").strip().lower() == spec:
                return p
        return None

    def controls(self):
        session = getattr(self, "_controls_session", None)
        if session is None:
            return []
        ce = self._controls_modules[0]
        editor = session["editor"]
        rows = []
        for key, dev in session["devices"].items():
            ref = ce.DeviceRef(dev.kind, session["ports"].port.get(key, -1), dev.vid, dev.pid)
            dtype = pad_glyphs.device_type(dev.kind, dev.vid, dev.pid)
            slots = []
            for slot in ce.SLOTS:
                sources = list(editor.sources(ref, slot.key))
                slots.append(dict(id=slot.key, label=self._control_label(slot.key), group=self._slot_group(slot),
                                  value=" / ".join(sources) or "@controls.unbound", sources=sources,
                                  glyphs=[pad_glyphs.glyph(dtype, s) for s in sources],
                                  text=" / ".join(pad_glyphs.glyph_text(dtype, s) for s in sources)))
            row = dict(id=key, name=dev.name, port=ref.port, kind=dev.kind, type=dtype,
                       label=self.message("controls.pad", port=ref.port + 1, name=dev.name)
                       if ref.port >= 0 else self.message("controls.unassigned", name=dev.name),
                       slots=slots, disabled=ref.port < 0, features={}, presets=[], preset="custom", player=None)
            try:
                features = self._features(session, ref)
                row.update(features=features, presets=self._presets(session, dev, ref) if features["presets"] else [],
                           preset=self._current_preset(session, ref), player=self._pinned(session, dev, ref))
                if features["options"] and ref.port >= 0:
                    row["options"] = dict(socd=editor.socd_of(ref.port), stick=editor.stick_of(ref.port))
            except Exception:  # noqa: BLE001 -- an older editor without these helpers keeps plain binding
                pass
            rows.append(row)
        return rows

    def controls_input(self, pad_id):
        """Held bindings before the game's stick/SOCD filtering: dict(lit=[slot ids], notation)."""
        session = getattr(self, "_controls_session", None)
        if session is None:
            return dict(lit=[], notation="")
        dev, ref = self._ref(session, pad_id)
        if dev is None:
            return dict(lit=[], notation="")
        ce, _ui, pm, _pn = self._controls_modules
        held = set(session["poller"].held.get(pad_id) or ())
        if not held:
            return dict(lit=[], notation="")
        editor = session["editor"]
        lit = [slot.key for slot in ce.SLOTS if held & set(editor.sources(ref, slot.key))]
        table = editor.table(ref)
        mask = 0
        for source in held:
            mask |= table.mask_of(source) or 0
        names = [name for name, bit in (getattr(pm, "PS3_BIT", None) or {}).items() if mask & bit]
        return dict(lit=lit, notation=pad_glyphs.notation(names))

    # ---------------------------------------------------------------- capture
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
        now = time.monotonic()
        session["capture"] = ui.Capture(now, timeout_s=CAPTURE_S, held=session["poller"].held.get(pad_id))
        session["pending"] = dict(pad=pad_id, slot=slot_id, dev=ce.DeviceRef(dev.kind, port, dev.vid, dev.pid),
                                  deadline=now + CAPTURE_S)
        session["state"] = dict(state="waiting", left=CAPTURE_S)

    def begin_input_test(self, pad_id):
        """The input test: nothing is captured or written; holding Back for HOLD_CANCEL_S ends it."""
        session = self._controls_open()
        self.poll_binding()
        if pad_id not in session["devices"]:
            raise RuntimeError("@controls.disconnected")
        session["poller"].drain()
        session["capture"] = None
        session["pending"] = dict(pad=pad_id, test=True, back_since=None)
        session["state"] = dict(state="test")

    def _back_held(self, pending, kind, held, now):
        """Seconds the controller's own Back button (B / Circle) has been held, or -1 when it is up."""
        back = BACK_SOURCE.get(kind)
        if back is None or back not in (held or ()):
            pending["back_since"] = None
            return -1.0
        if pending.get("back_since") is None:
            pending["back_since"] = now
        return now - pending["back_since"]

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
        if pending is not None and pending.get("test"):
            dev = session["devices"].get(pending["pad"])
            if dev is None:
                session["pending"] = None
                session["state"] = dict(state="disconnected")
            elif self._back_held(pending, dev.kind, poller.held.get(pending["pad"]), now) >= HOLD_CANCEL_S:
                session["pending"] = None
                session["state"] = dict(state="cancelled")
            else:
                session["state"] = dict(state="test", back=pending.get("back_since") is not None)
            return dict(session["state"])
        if pending is not None:
            dev = session["devices"].get(pending["pad"])
            ref = pending["dev"]
            if dev is None or session["ports"].port.get(dev.key, -1) != ref.port or (dev.kind, dev.vid, dev.pid) != (ref.kind, ref.vid, ref.pid):
                session["capture"] = session["pending"] = None
                session["state"] = dict(state="disconnected")
        pending = session["pending"]
        if pending is not None and pending.get("holding"):
            return self._holding(session, pending, poller.held.get(pending["pad"]) or (), now)
        if session["capture"] is not None:
            if now >= pending["deadline"]:
                session["capture"] = session["pending"] = None
                session["state"] = dict(state="timeout")
                return dict(session["state"])
            result = session["capture"].update(now, [edge for edge in edges if edge.key == pending["pad"]],
                                                held=poller.held.get(pending["pad"]))
            if result is None:
                session["state"] = dict(state="waiting", left=max(0.0, pending["deadline"] - now))
                return dict(session["state"])
            state, source = result
            if state == "ok":
                pressed = getattr(session["capture"], "first", None)
                session["capture"] = None
                pending["source"] = source
                game_keys = getattr(self._controls_modules[0], "GAME_KEYS", None) or {}
                if str(pending["dev"].kind).startswith("keys") and source in game_keys:
                    session["pending"] = None
                    session["state"] = dict(state="game_key", source=source)
                elif source == BACK_SOURCE.get(pending["dev"].kind) and source in (poller.held.get(pending["pad"]) or ()):
                    pending["holding"] = True
                    pending["back_since"] = pressed if isinstance(pressed, (int, float)) and pressed <= now else now
                    return self._holding(session, pending, poller.held.get(pending["pad"]) or (), now)
                else:
                    self._captured(session, pending)
            elif state == "multi":
                ui = self._controls_modules[1]
                session["capture"] = ui.Capture(now, timeout_s=max(0.0, pending["deadline"] - now),
                                                 held=poller.held.get(pending["pad"]))
                session["state"] = dict(state="multi")
            else:
                session["capture"] = session["pending"] = None
                session["state"] = dict(state="timeout")
        return dict(session["state"])

    def _holding(self, session, pending, held, now):
        """Back went down: let go quickly and it is the new button; hold it and the capture is cancelled."""
        if pending["source"] in held and now - pending["back_since"] >= HOLD_CANCEL_S:
            session["capture"] = session["pending"] = None
            session["state"] = dict(state="cancelled")
        elif pending["source"] not in held:
            pending.pop("holding")
            self._captured(session, pending)
        else:
            session["state"] = dict(state="waiting", left=0.0, holding=True)
        return dict(session["state"])

    def _captured(self, session, pending):
        """A button was chosen: ready, or a conflict naming the action that has it and the button that one gets."""
        ce = self._controls_modules[0]
        source = pending["source"]
        editor = session["editor"]
        old = editor.table(pending["dev"]).mask_of(source)
        target = next(slot.mask for slot in ce.SLOTS if slot.key == pending["slot"])
        others = [slot.key for slot in ce.SLOTS if slot.mask == old and old != target]
        conflicts = [self._control_label(key) for key in others]
        if old and old != target and not conflicts:
            conflicts = [ce.mask_text(old)]
        if not conflicts:
            session["state"] = dict(state="ready", source=source)
            return
        state = dict(state="conflict", source=source, conflicts=conflicts)
        given = [s for s in editor.sources(pending["dev"], pending["slot"]) if s != source]
        if len(others) == 1 and given:
            pending["swap"], pending["given"] = others[0], given
            state["swap"] = dict(slot=self._control_label(others[0]), sources=given)
        session["state"] = state

    def _controls_write(self, session, change):
        """Run `change(editor)` and save. A private settings copy is replaced only after the complete save, and on
        any failure the editor is loaded again from the file, which keeps its old bindings."""
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
            change(session["editor"])
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

    def accept_binding(self, swap=True):
        """Save the captured button. With `swap`, the action that had it gets this action's old button."""
        if self.running():
            raise RuntimeError("@controls.running")
        session = self._controls_open()
        self.poll_binding()
        pending = session["pending"]
        if pending is None or "source" not in pending:
            raise RuntimeError("@controls.disconnected")
        scope = self._scope(self._controls_modules[0], pending["dev"])

        def change(editor):
            editor.bind(pending["dev"], scope, pending["slot"], [pending["source"]])
            other = pending.get("swap")
            if swap and other is not None:
                kept = [s for s in editor.sources(pending["dev"], other) if s != pending["source"]]
                editor.bind(pending["dev"], scope, other, kept + [s for s in pending["given"] if s not in kept])

        self._controls_write(session, change)
        session["capture"] = session["pending"] = None
        session["state"] = dict(state="done")

    def cancel_binding(self):
        session = getattr(self, "_controls_session", None)
        if session is not None:
            session["capture"] = session["pending"] = None
            session["state"] = dict(state="idle")
            session["poller"].drain()

    # ---------------------------------------------------------------- whole-controller edits
    def clear_binding(self, pad_id, slot_id):
        session, _dev, ref = self._editable(pad_id)
        ce = self._controls_modules[0]
        if slot_id not in {slot.key for slot in ce.SLOTS} or not callable(getattr(session["editor"], "clear", None)):
            raise ValueError("@controls.unsupported")
        self._controls_write(session, lambda editor: editor.clear(ref, self._scope(ce, ref), slot_id))

    def reset_controls(self, pad_id):
        session, _dev, ref = self._editable(pad_id)
        if not callable(getattr(session["editor"], "reset", None)):
            raise ValueError("@controls.unsupported")
        self._controls_write(session, lambda editor: editor.reset(ref))

    def apply_preset(self, pad_id, preset_id):
        session, dev, ref = self._editable(pad_id)
        if preset_id not in {pid for pid, _label in self._presets(session, dev, ref)}:
            raise ValueError("@controls.unsupported")
        plan = next(plan for pid, _label, plan in pad_presets.PRESETS if pid == preset_id)
        kind, what = pad_presets.step(plan, ref.kind)
        scope = self._scope(self._controls_modules[0], ref)

        def change(editor):
            if kind == "recipe":
                editor.apply_recipe(ref, scope, what)
                return
            editor.reset(ref)
            if kind == "lines":
                for key, sources in pad_presets.LINES[what]:
                    editor.bind(ref, scope, key, list(sources))

        self._controls_write(session, change)

    def set_control_option(self, pad_id, key, value):
        """`[portN] socd` / `stick` of this controller's player."""
        session, _dev, ref = self._editable(pad_id)
        if str(ref.kind).startswith("keys") or not callable(getattr(session["editor"], "set_port_option", None)):
            raise ValueError("@controls.unsupported")
        self._controls_write(session, lambda editor: editor.set_port_option(ref.port, key, value))

    def set_control_player(self, pad_id, port):
        """This controller plays as player `port` (0-based); None: the game's own order again."""
        session, dev, ref = self._editable(pad_id, any_port=True)
        if str(ref.kind).startswith("keys"):
            self._controls_write(session, lambda editor: editor.assign_keyboard(ref.kind, port))
        else:
            self._controls_write(session, lambda editor: editor.assign_port(pad_presets.device_spec(dev), port))

    def controls_close(self):
        session = getattr(self, "_controls_session", None)
        if session is not None:
            self.poll_binding(active=False)
            self._controls_session = None
