"""A game adapter with fake controllers for the Pad bindings page: bindings in memory, no devices, no files."""
from openrecomp import pad_glyphs, pad_presets
from openrecomp.adapters.base import Adapter
from test_nav import Fake, manifest

SLOTS = (("1", "attack"), ("2", "attack"), ("3", "attack"), ("4", "attack"), ("1+2", "macro"), ("3+4", "macro"),
         ("1+3", "macro"), ("2+4", "macro"), ("1+2+3+4", "macro"), ("START", "menu"), ("SELECT", "menu"),
         ("L1", "menu"), ("R1", "menu"), ("UP", "dir"), ("DOWN", "dir"), ("LEFT", "dir"), ("RIGHT", "dir"))
LABELS = {"1": "@controls.slot.1", "2": "@controls.slot.2", "3": "@controls.slot.3", "4": "@controls.slot.4",
          "START": "@controls.slot.START", "SELECT": "@controls.slot.SELECT", "UP": "@controls.slot.UP",
          "DOWN": "@controls.slot.DOWN", "LEFT": "@controls.slot.LEFT", "RIGHT": "@controls.slot.RIGHT"}
DEFAULTS = {
    "xinput": {"1": ["X"], "2": ["Y"], "3": ["A"], "4": ["B"], "START": ["START"], "SELECT": ["BACK"], "L1": ["LB"],
               "R1": ["RB"], "UP": ["DUP"], "DOWN": ["DDOWN"], "LEFT": ["DLEFT"], "RIGHT": ["DRIGHT"]},
    "dinput": {"1": ["B1"], "2": ["B4"], "3": ["B2"], "4": ["B3"], "START": ["B10"], "SELECT": ["B9"], "L1": ["B5"],
               "R1": ["B6"], "UP": ["HAT_UP"], "DOWN": ["HAT_DOWN"], "LEFT": ["HAT_LEFT"], "RIGHT": ["HAT_RIGHT"]},
    "keys1": {"1": ["A"], "2": ["S"], "3": ["Z"], "4": ["X"], "START": ["ENTER"], "SELECT": ["TAB"], "L1": ["Q"],
              "R1": ["W"], "UP": ["UP"], "DOWN": ["DOWN"], "LEFT": ["LEFT"], "RIGHT": ["RIGHT"]},
}
BITS = {"1": "SQUARE", "2": "TRIANGLE", "3": "CROSS", "4": "CIRCLE"}


def _label(key):
    if key in LABELS:
        return LABELS[key]
    if "+" in key:
        parts = key.split("+")
        label = _label(parts[0])
        for p in parts[1:]:
            label = Adapter.message("controls.slot.join", a=label, b=_label(p))
        return label
    return Adapter.message("controls.slot.ps3", name=key)


class PadsFake(Fake):
    """Three controllers: an Xbox pad (player 1), a DualSense (player 2) and the keyboard (player 1)."""

    def __init__(self):
        super().__init__(manifest())
        self.pads = [dict(id="xinput:0", name="Xbox pad", kind="xinput", vid=0, port=0),
                     dict(id="dinput:054C:0CE6", name="DualSense", kind="dinput", vid=0x054C, port=1),
                     dict(id="keys1", name="Keyboard", kind="keys1", vid=0, port=0)]
        self.binds = {p["id"]: {k: list(v) for k, v in DEFAULTS[p["kind"]].items()} for p in self.pads}
        self.preset = {p["id"]: "default" for p in self.pads}
        self.options = {0: dict(socd="neutral", stick="analog"), 1: dict(socd="neutral", stick="analog")}
        self.held = {}
        self.result = dict(state="waiting", left=5.0)

    def controls_supported(self):
        return True

    def controls(self):
        rows = []
        for p in self.pads:
            dtype = pad_glyphs.device_type(p["kind"], p["vid"])
            slots = []
            for key, group in SLOTS:
                sources = list(self.binds[p["id"]].get(key, []))
                slots.append(dict(id=key, label=_label(key), group=group, sources=sources,
                                  value=" / ".join(sources) or "@controls.unbound",
                                  glyphs=[pad_glyphs.glyph(dtype, s) for s in sources],
                                  text=" / ".join(pad_glyphs.glyph_text(dtype, s) for s in sources)))
            keys = p["kind"].startswith("keys")
            presets = [(pid, label) for pid, label, plan in pad_presets.PRESETS if pad_presets.step(plan, p["kind"])]
            row = dict(id=p["id"], name=p["name"], port=p["port"], kind=p["kind"], type=dtype,
                       label=self.message("controls.pad", port=p["port"] + 1, name=p["name"]), slots=slots,
                       disabled=p["port"] < 0, presets=presets, preset=self.preset[p["id"]], player=None,
                       features=dict(test=True, clear=True, reset=True, presets=True, options=not keys, player=True))
            if not keys:
                row["options"] = dict(self.options[p["port"]])
            rows.append(row)
        return rows

    def controls_input(self, pad_id):
        held = set(self.held.get(pad_id, ()))
        lit = [k for k, srcs in self.binds[pad_id].items() if held & set(srcs)]
        names = set()
        for key in lit:
            for part in key.split("+"):
                names.add(BITS.get(part, part))
        return dict(lit=lit, notation=pad_glyphs.notation(names))

    def begin_binding(self, pad, slot):
        self.calls.append(("bind", pad, slot))

    def begin_input_test(self, pad):
        self.calls.append(("test", pad))

    def poll_binding(self, active=True):
        return dict(self.result)

    def accept_binding(self, swap=True):
        self.calls.append(("accept", swap))

    def cancel_binding(self):
        self.calls.append(("cancel",))

    def controls_close(self):
        self.calls.append(("close",))

    def apply_preset(self, pad, preset):
        self.calls.append(("preset", pad, preset))
        self.preset[pad] = preset

    def reset_controls(self, pad):
        self.calls.append(("reset", pad))

    def clear_binding(self, pad, slot):
        self.calls.append(("clear", pad, slot))
        self.binds[pad][slot] = []

    def set_control_option(self, pad, key, value):
        self.calls.append(("option", pad, key, value))
        port = next(p["port"] for p in self.pads if p["id"] == pad)
        self.options[port][key] = value

    def set_control_player(self, pad, port):
        self.calls.append(("player", pad, port))
