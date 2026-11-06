"""Tekken 4's Pad bindings page, editable like T5DR's: pick the device, select an action, press the new button (X clears),
presets. It edits controls.ini in the game's save folder, which the T4 runtime reads (PS2Recomp patch
99-ps2xRuntime-pad-bindings; format and model: openrecomp/t4_controls_ini.py). The game has to be closed while editing.

Rows are devices, like the page's other games: the keyboard, and one row per XInput pad found. Which player a device plays
as is stored in the file (`device =` lines) and chosen with the page's "Plays as" setting; the bindings of a device are the
bindings of the player it plays. DirectInput pads (DualShock without DS4Windows/Steam, generic pads) keep the game's fixed
layout and have no row.

Tekken 4 on the PS2: 1 = left punch = Square, 2 = right punch = Triangle, 3 = left kick = Cross, 4 = right kick = Circle.
"""
import os
import time

from .. import pad_glyphs, t4_controls_ini as ini
from ..t4_pad_reader import Reader, pad_name

CAPTURE_S = 5.0            # "Press a button": the countdown the page shows
HOLD_CANCEL_S = 1.0        # holding the pad's Back button (B) this long cancels a capture or ends the input test
LABELS = {"1": "@controls.slot.1", "2": "@controls.slot.2", "3": "@controls.slot.3", "4": "@controls.slot.4",
          "START": "@controls.slot.START", "SELECT": "@controls.slot.SELECT", "UP": "@controls.slot.UP",
          "DOWN": "@controls.slot.DOWN", "LEFT": "@controls.slot.LEFT", "RIGHT": "@controls.slot.RIGHT"}


class T4Controls:
    """controls_supported() / controls() and the edits of the Pad bindings page, on controls.ini."""

    # ---------------------------------------------------------------- hooks (tests replace them)
    def _t4c_path(self):
        """controls.ini in the game's save folder (the folder the game runs in): the runtime's default, and what the
        launcher also hands it as TEKKEN4_CONTROLS."""
        return os.path.join(self.core.SAVE_DIR, ini.FILE_NAME)

    def _t4c_reader(self):
        return Reader()

    def _t4c_clock(self):
        return time.monotonic()

    def controls_supported(self):
        return True

    def _t4c_open(self):
        session = getattr(self, "_t4c_session", None)
        if session is None:
            reader = self._t4c_reader()
            session = dict(model=ini.Controls.load(self._t4c_path()), reader=reader, slots=set(reader.step()),
                           pending=None, state=dict(state="idle"), active=True)
            self._t4c_session = session
        return session

    # ---------------------------------------------------------------- what the page shows
    def _t4c_label(self, slot):
        if slot in ini.COMBO_TARGETS:
            label = None
            for part in ini.COMBO_TARGETS[slot]:
                one = self._t4c_label(part)
                label = one if label is None else self.message("controls.slot.join", a=label, b=one)
            return label
        return LABELS.get(slot) or self.message("controls.slot.ps2", name=slot)

    def _t4c_device(self, session, pad_id):
        """(kind, player or None, XInput slot or None) of a row; RuntimeError("@controls.disconnected") if it is gone."""
        model = session["model"]
        if pad_id == ini.KEYBOARD_ID:
            return ini.KIND_KEYS, model.keyboard_player(), None
        if isinstance(pad_id, str) and pad_id.startswith(ini.PAD_ID) and pad_id[len(ini.PAD_ID):].isdigit():
            slot = int(pad_id[len(ini.PAD_ID):])
            if slot in session["slots"]:
                return ini.KIND_PAD, model.resolve(session["slots"]).get(slot), slot
        raise RuntimeError("@controls.disconnected")

    def _t4c_row(self, session, pad_id, kind, player, name, slot=None):
        model = session["model"]
        device_kind = ini.DEVICE_KEYS if kind == ini.KIND_KEYS else ini.DEVICE_PAD
        dtype = pad_glyphs.device_type(device_kind)
        shown = 0 if player is None else player          # an unassigned device shows player 1's bindings, read only
        slots = []
        order = [(s, g) for s, g, _t in ini.SLOTS] + [(c, "macro") for c in ini.COMBO_IDS]
        for slot_id, group in order:
            sources = model.plain_sources(shown, kind, slot_id) if slot_id in ini.SLOT_IDS                 else model.sources(shown, kind, slot_id)
            slots.append(dict(id=slot_id, label=self._t4c_label(slot_id), group=group, sources=sources,
                              value=" / ".join(sources) or "@controls.unbound",
                              glyphs=[pad_glyphs.glyph(dtype, s) for s in sources],
                              text=" / ".join(pad_glyphs.glyph_text(dtype, s) for s in sources)))
        if kind == ini.KIND_KEYS:
            pinned = None if (model.players[0].keyboard and not model.players[1].keyboard) else model.keyboard_player()
        else:
            pinned = model.pinned_player(slot)
        return dict(id=pad_id, name=name, port=-1 if player is None else player, kind=device_kind, type=dtype,
                    label=self.message("controls.pad", port=shown + 1, name=name) if player is not None
                    else self.message("controls.unassigned", name=name),
                    slots=slots, disabled=player is None,
                    features=dict(test=True, clear=True, reset=True, presets=True, options=False, player=True),
                    presets=ini.presets_for(kind), preset=model.current_preset(shown, kind), player=pinned)

    def controls(self):
        session = self._t4c_open()
        model, slots = session["model"], session["slots"]
        resolved = model.resolve(slots)
        rows = [self._t4c_row(session, ini.KEYBOARD_ID, ini.KIND_KEYS, model.keyboard_player(), "@controls.t4_keyboard")]
        for slot in sorted(slots):
            rows.append(self._t4c_row(session, ini.PAD_ID + str(slot), ini.KIND_PAD, resolved.get(slot), pad_name(slot),
                                      slot))
        if not slots:
            row = self._t4c_row(session, ini.NO_PAD_ID, ini.KIND_PAD, None, "@controls.t4_pad_none")
            row.update(features={}, presets=[], preset=ini.PRESET_DEFAULT, player=None, label="@controls.t4_pad_none")
            rows.append(row)
        return rows

    # ---------------------------------------------------------------- the live strip and the input test
    def _t4c_held(self, session, kind, slot):
        return session["reader"].keys_held() if kind == ini.KIND_KEYS else session["reader"].pad_held(slot)

    def controls_input(self, pad_id):
        """Held bindings: dict(lit=[slot ids], notation). Only while the input test runs (the keyboard is not read otherwise)."""
        session = getattr(self, "_t4c_session", None)
        pending = session["pending"] if session else None
        if not pending or not pending.get("test") or pending["pad"] != pad_id:
            return dict(lit=[], notation="")
        held = self._t4c_held(session, pending["kind"], pending["devslot"])
        model, player, kind = session["model"], pending["player"], pending["kind"]
        lit = [slot for slot in ini.SLOT_IDS if held & set(model.sources(player, kind, slot))]
        names = [ini.PS2_BUTTON.get(slot, slot) for slot in lit]
        lit += [c for c in ini.COMBO_IDS if held & set(model.sources(player, kind, c))]
        return dict(lit=lit, notation=pad_glyphs.notation(names))

    def begin_input_test(self, pad_id):
        session = self._t4c_open()
        self.poll_binding()
        kind, player, slot = self._t4c_device(session, pad_id)
        if player is None:
            raise RuntimeError("@controls.disconnected")
        session["pending"] = dict(pad=pad_id, test=True, kind=kind, player=player, devslot=slot, back_since=None,
                                  baseline=set())
        session["state"] = dict(state="test")

    # ---------------------------------------------------------------- capture
    def _t4c_editable(self, pad_id, any_port=False):
        if self.running():
            raise RuntimeError("@controls.running")
        session = self._t4c_open()
        kind, player, slot = self._t4c_device(session, pad_id)
        if player is None and not any_port:
            raise RuntimeError("@controls.disconnected")
        return session, kind, player, slot

    def begin_binding(self, pad_id, slot_id):
        session, kind, player, slot = self._t4c_editable(pad_id)
        if slot_id not in ini.PAGE_SLOT_IDS:
            raise ValueError("@controls.unsupported")
        self.poll_binding()
        now = self._t4c_clock()
        session["pending"] = dict(pad=pad_id, slot=slot_id, kind=kind, player=player, devslot=slot, deadline=now + CAPTURE_S,
                                  baseline=set(self._t4c_held(session, kind, slot)), back_since=None)
        session["state"] = dict(state="waiting", left=CAPTURE_S)

    def poll_binding(self, active=True):
        session = getattr(self, "_t4c_session", None)
        if session is None:
            if not active:
                return dict(state="idle")
            session = self._t4c_open()
        session["active"] = bool(active)
        if not active:
            return dict(session["state"])
        now = self._t4c_clock()
        session["slots"] = set(session["reader"].step())
        pending = session["pending"]
        if pending is None:
            return dict(session["state"])
        try:
            kind, player, slot = self._t4c_device(session, pending["pad"])
        except RuntimeError:
            session["pending"] = None
            session["state"] = dict(state="disconnected")
            return dict(session["state"])
        if player != pending["player"]:
            session["pending"] = None
            session["state"] = dict(state="disconnected")
            return dict(session["state"])
        held = self._t4c_held(session, kind, slot)
        back = kind == ini.KIND_PAD and "B" in held
        if pending.get("test"):
            if back:
                pending["back_since"] = pending["back_since"] if pending["back_since"] is not None else now
                if now - pending["back_since"] >= HOLD_CANCEL_S:
                    session["pending"] = None
                    session["state"] = dict(state="cancelled")
                    return dict(session["state"])
            else:
                pending["back_since"] = None
            session["state"] = dict(state="test", back=pending["back_since"] is not None)
            return dict(session["state"])
        if pending.get("holding"):
            return self._t4c_holding(session, pending, held, now)
        if now >= pending["deadline"]:
            session["pending"] = None
            session["state"] = dict(state="timeout")
            return dict(session["state"])
        pending["baseline"] &= held                   # a button held when the capture began counts once it is let go
        pressed = held - pending["baseline"]
        if not pressed:
            session["state"] = dict(state="waiting", left=max(0.0, pending["deadline"] - now))
        elif len(pressed) > 1:
            pending["baseline"] = set(held)
            session["state"] = dict(state="multi")
        else:
            source = next(iter(pressed))
            pending["source"] = source
            if kind == ini.KIND_KEYS and source in ini.GAME_KEYS:
                session["pending"] = None
                session["state"] = dict(state="game_key", source=source)
            elif kind == ini.KIND_KEYS and source == "ESC":
                session["pending"] = None             # Esc is the launcher's own Back: it cancels instead of binding
                session["state"] = dict(state="cancelled")
            elif kind == ini.KIND_PAD and source == "B":
                pending["holding"] = True             # B is the pad's Back: a short tap binds B, one second cancels
                pending["back_since"] = now
                session["state"] = dict(state="waiting", left=0.0, holding=True)
            else:
                self._t4c_captured(session, pending)
        return dict(session["state"])

    def _t4c_holding(self, session, pending, held, now):
        if "B" in held and now - pending["back_since"] >= HOLD_CANCEL_S:
            session["pending"] = None
            session["state"] = dict(state="cancelled")
        elif "B" in held:
            session["state"] = dict(state="waiting", left=0.0, holding=True)
        else:
            pending.pop("holding")
            self._t4c_captured(session, pending)
        return dict(session["state"])

    def _t4c_captured(self, session, pending):
        """A button was chosen: ready, or a conflict naming the action(s) that have it and what the old owner would get."""
        model, source, slot = session["model"], pending["source"], pending["slot"]
        player, kind = pending["player"], pending["kind"]
        others = [o for o in model.holders(player, kind, source) if o != slot]
        if not others:
            session["state"] = dict(state="ready", source=source)
            return
        state = dict(state="conflict", source=source, conflicts=[self._t4c_label(o) for o in others])
        given = [s for s in model.sources(player, kind, slot) if s != source]
        pending.pop("swap_slot", None)
        combo = slot in ini.COMBO_TARGETS or others[0] in ini.COMBO_TARGETS
        if len(others) == 1 and given and not combo:
            pending["swap_slot"], pending["given"] = others[0], given
            state["swap"] = dict(slot=self._t4c_label(others[0]), sources=given)
        session["state"] = state

    def accept_binding(self, swap=True):
        """Saves the captured button. With `swap`, the action that had it gets this action's old button."""
        if self.running():
            raise RuntimeError("@controls.running")
        session = self._t4c_open()
        pending = session["pending"]
        if pending is None or "source" not in pending or pending.get("test"):
            raise RuntimeError("@controls.disconnected")
        player, kind, slot, source = pending["player"], pending["kind"], pending["slot"], pending["source"]
        other, given = pending.get("swap_slot"), pending.get("given") or []

        def change(model):
            if slot in ini.COMBO_TARGETS:
                model.bind_combo(player, kind, slot, [source])
                return
            model.set_plain(player, kind, slot, [source])
            model.release(player, kind, source, keep=slot)
            if swap and other is not None:
                kept = model.sources(player, kind, other)
                model.set_plain(player, kind, other, kept + [s for s in given if s not in kept])

        self._t4c_write(session, change)
        session["pending"] = None
        session["state"] = dict(state="done")

    def cancel_binding(self):
        session = getattr(self, "_t4c_session", None)
        if session is not None:
            session["pending"] = None
            session["state"] = dict(state="idle")

    def _t4c_write(self, session, change):
        """Runs `change(model)` and saves. On any failure the model is read from the file again (its old bindings)."""
        try:
            change(session["model"])
            session["model"].save()
        except Exception:
            session["model"] = ini.Controls.load(self._t4c_path())
            self.cancel_binding()
            raise

    # ---------------------------------------------------------------- whole-device edits
    def clear_binding(self, pad_id, slot_id):
        session, kind, player, _slot = self._t4c_editable(pad_id)
        if slot_id not in ini.PAGE_SLOT_IDS:
            raise ValueError("@controls.unsupported")
        if slot_id in ini.COMBO_TARGETS:
            self._t4c_write(session, lambda model: model.clear_combo(player, kind, slot_id))
        else:
            self._t4c_write(session, lambda model: model.set_plain(player, kind, slot_id, []))

    def reset_controls(self, pad_id):
        session, kind, player, _slot = self._t4c_editable(pad_id)
        self._t4c_write(session, lambda model: model.reset(player, kind))

    def apply_preset(self, pad_id, preset_id):
        session, kind, player, _slot = self._t4c_editable(pad_id)
        if preset_id not in {pid for pid, _label in ini.presets_for(kind)}:
            raise ValueError("@controls.unsupported")
        self._t4c_write(session, lambda model: model.apply_preset(player, kind, preset_id))

    def set_control_player(self, pad_id, port):
        """This device plays as player `port` (0-based); None: the game's own order again."""
        session, kind, _player, slot = self._t4c_editable(pad_id, any_port=True)
        if port not in (None, 0, 1):
            raise ValueError("@controls.unsupported")
        if kind == ini.KIND_KEYS:
            self._t4c_write(session, lambda model: model.assign_keyboard(port))
        else:
            self._t4c_write(session, lambda model: model.assign_pad(slot, port))

    def controls_close(self):
        self._t4c_session = None
