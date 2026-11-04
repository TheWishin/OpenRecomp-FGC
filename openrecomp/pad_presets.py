"""The Pad bindings page's presets, as steps for the installed controls editor. No Qt, no game install.

A step is ("reset", None) -- the game's own default layout for that controller --, ("recipe", id) -- one of
controls_edit.RECIPES, which writes `preset = ...` / `macros = ...` lines the game knows --, or ("lines", name) --
the default layout, then plain `TARGET = SOURCE` lines from LINES. Every step ends in controls.ini lines the game
already reads; nothing here adds a format of its own.
"""
import re

PADS = ("xinput", "dinput")
KEYS = ("keys1", "keys2")

# (id, label, {reader kind: step}) in the order the page offers them
PRESETS = (
    ("default", "@controls.preset.default", {k: ("reset", None) for k in PADS + KEYS}),
    # face buttons 1 2 3 4, 1+2 on R1 / RB and 3+4 on R2 / RT (the 6-button recipe on a pad)
    ("tekken", "@controls.preset.tekken", dict({k: ("recipe", "astro") for k in PADS},
                                              **{k: ("recipe", "keys_tekken") for k in KEYS})),
    ("arcade", "@controls.preset.arcade", {k: ("recipe", "vewlix") for k in PADS}),
    ("hitbox", "@controls.preset.hitbox", {k: ("recipe", "hitbox") for k in PADS}),
    ("lefty", "@controls.preset.lefty", {"xinput": ("lines", "lefty_xinput"), "dinput": ("lines", "lefty_dinput")}),
    ("numpad", "@controls.preset.numpad", {k: ("recipe", "keys_numpad") for k in KEYS}),
)
PRESET_HINTS = {pid: "@controls.preset." + pid + "_hint" for pid, _label, _plan in PRESETS}

# Left-handed: the attacks on the d-pad / hat (left thumb), moving with the face buttons and the right stick.
LINES = {
    "lefty_xinput": (("1", ("DLEFT",)), ("2", ("DUP",)), ("3", ("DDOWN",)), ("4", ("DRIGHT",)),
                     ("UP", ("Y", "RUP")), ("DOWN", ("A", "RDOWN")), ("LEFT", ("X", "RLEFT")),
                     ("RIGHT", ("B", "RRIGHT"))),
    "lefty_dinput": (("1", ("HAT_LEFT",)), ("2", ("HAT_UP",)), ("3", ("HAT_DOWN",)), ("4", ("HAT_RIGHT",)),
                     ("UP", ("B4", "RZ-")), ("DOWN", ("B2", "RZ+")), ("LEFT", ("B1", "Z-")),
                     ("RIGHT", ("B3", "Z+"))),
}

# controls_edit.detect_recipe() ids -> the page's preset
RECIPE_PRESET = {"default": "default", "switch": "default", "xbox_hid": "default", "keys_classic": "default",
                 "astro": "tekken", "keys_tekken": "tekken", "vewlix": "arcade", "hitbox": "hitbox",
                 "keys_numpad": "numpad"}

SOCD = ("neutral", "up", "last", "off")
STICK = ("analog", "dpad")


def step(plan, kind):
    """The step of a preset for this reader kind, or None when the preset is not for it."""
    return plan.get(str(kind or "").lower())


def device_spec(dev):
    """How controls.ini names a controller in `[portN] device = ...` (as T5DR's Controls window does)."""
    if dev.kind == "xinput":
        return f"xinput:{dev.slot}"
    if dev.vid:
        return f"dinput:{dev.vid:04X}:{dev.pid:04X}"
    return "dinput:" + re.sub(r"[\s;#]+", " ", str(dev.name)).strip()
