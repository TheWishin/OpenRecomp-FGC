"""Tekken 4's Pad bindings page: its buttons are fixed in the T4 runtime (no mapping file it could read yet), so the page
shows the layout the game uses, read only, instead of having no entry at all (player report 2026-11-06: "where are the
bindings?"). The layout is the runtime's own (PS2Recomp patches 29/60: ps2_input_latency.cpp sampleKeyboard,
ps2_host_pad.cpp): keyboard WASD + arrows, a controller by position like a PS2 pad.

Tekken 4 on the PS2: 1 = left punch = Square, 2 = right punch = Triangle, 3 = left kick = Cross, 4 = right kick = Circle.
"""
from .. import pad_glyphs

# (slot, group, keyboard keys, XInput buttons): slot names are the Pad bindings page's (Tekken notation, PS buttons).
LAYOUT = (
    ("1", "attack", ("LEFT", "Z"), ("X",)),
    ("2", "attack", ("UP", "V"), ("Y",)),
    ("3", "attack", ("DOWN", "X"), ("A",)),
    ("4", "attack", ("RIGHT", "C"), ("B",)),
    ("START", "menu", ("ENTER",), ("START",)),
    ("SELECT", "menu", ("TAB",), ("BACK",)),
    ("L1", "menu", ("Q",), ("LB",)),
    ("R1", "menu", ("E",), ("RB",)),
    ("L2", "menu", ("LSHIFT",), ("LT",)),
    ("R2", "menu", ("RSHIFT",), ("RT",)),
    ("UP", "dir", ("W",), ("DUP", "LUP")),
    ("DOWN", "dir", ("S",), ("DDOWN", "LDOWN")),
    ("LEFT", "dir", ("A",), ("DLEFT", "LLEFT")),
    ("RIGHT", "dir", ("D",), ("DRIGHT", "LRIGHT")),
)
TABS = (dict(id="t4:keyboard", kind="keys1", name="@controls.t4_keyboard", column=2),
        dict(id="t4:pad", kind="xinput", name="@controls.t4_pad", column=3))
LABELS = {"1": "@controls.slot.1", "2": "@controls.slot.2", "3": "@controls.slot.3", "4": "@controls.slot.4",
          "START": "@controls.slot.START", "SELECT": "@controls.slot.SELECT", "UP": "@controls.slot.UP",
          "DOWN": "@controls.slot.DOWN", "LEFT": "@controls.slot.LEFT", "RIGHT": "@controls.slot.RIGHT"}


class T4Controls:
    """controls_supported() / controls(): the fixed layout as two read-only tabs (keyboard, controller). Every edit
    stays the base Adapter's "@controls.unsupported"."""

    def controls_supported(self):
        return True

    def controls(self):
        rows = []
        for tab in TABS:
            pad_id, kind, name, column = tab["id"], tab["kind"], tab["name"], tab["column"]
            dtype = pad_glyphs.device_type(kind)
            slots = []
            for entry in LAYOUT:
                key, group, sources = entry[0], entry[1], list(entry[column])
                slots.append(dict(id=key, label=LABELS.get(key) or self.message("controls.slot.ps3", name=key),
                                  group=group, sources=sources, value=" / ".join(sources),
                                  glyphs=[pad_glyphs.glyph(dtype, s) for s in sources],
                                  text=" / ".join(pad_glyphs.glyph_text(dtype, s) for s in sources)))
            rows.append(dict(id=pad_id, name=name, port=0, kind=kind, type=dtype, label=name, slots=slots,
                             disabled=False, fixed=True, features={}, presets=[], preset="custom", player=None))
        return rows
