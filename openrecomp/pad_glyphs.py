"""What a bound input looks like on the Pad bindings page: the controller's own button as a glyph we draw ourselves
(PadGlyph.qml), and Tekken notation for the input test. No Qt, no game install: plain names in, plain dicts out.

Source names are controls.ini's (T5DR's padmap): XInput A B X Y LB RB LT RT BACK START LS RS DUP.. LUP.. RUP..,
DirectInput B1..B128 HAT_UP.. X+ X- Y+ Y- Z+ Z- RX+ .. (a PlayStation pad numbers its buttons in the pad's own order:
B1 square, B2 cross, B3 circle, B4 triangle), keyboard key names (A, ENTER, NUM4, SEMICOLON, ...).
"""
import re

XBOX, PS, GENERIC, KEYBOARD = "xbox", "ps", "generic", "keyboard"
VID_SONY = 0x054C
DIRS = ("up", "down", "left", "right")

_XBOX = {
    "A": ("face", "A", "green"), "B": ("face", "B", "red"), "X": ("face", "X", "blue"), "Y": ("face", "Y", "yellow"),
    "LB": ("bumper", "LB", ""), "RB": ("bumper", "RB", ""), "LT": ("trigger", "LT", ""), "RT": ("trigger", "RT", ""),
    "BACK": ("menu", "View", ""), "START": ("menu", "Menu", ""), "LS": ("click", "LS", ""), "RS": ("click", "RS", ""),
}
_PS = {
    "B1": ("ps", "square", "pink"), "B2": ("ps", "cross", "blue"), "B3": ("ps", "circle", "red"),
    "B4": ("ps", "triangle", "green"), "B5": ("bumper", "L1", ""), "B6": ("bumper", "R1", ""),
    "B7": ("trigger", "L2", ""), "B8": ("trigger", "R2", ""), "B9": ("menu", "Share", ""), "B10": ("menu", "Options", ""),
    "B11": ("click", "L3", ""), "B12": ("click", "R3", ""), "B13": ("menu", "PS", ""), "B14": ("touch", "Touchpad", ""),
    "B15": ("menu", "Mute", ""), "RX+": ("trigger", "L2", ""), "RY+": ("trigger", "R2", ""),
}
_STICK_DIR = {"UP": "up", "DOWN": "down", "LEFT": "left", "RIGHT": "right"}
# DirectInput axes: X/Y = left stick (Y- is up), Z/RZ = a PlayStation pad's right stick (RX/RY are its triggers)
_AXIS = {"X-": ("L", "left"), "X+": ("L", "right"), "Y-": ("L", "up"), "Y+": ("L", "down")}
_PS_AXIS = dict(_AXIS, **{"Z-": ("R", "left"), "Z+": ("R", "right"), "RZ-": ("R", "up"), "RZ+": ("R", "down")})
_KEY_TEXT = {
    "UP": "↑", "DOWN": "↓", "LEFT": "←", "RIGHT": "→", "ENTER": "Enter", "RETURN": "Enter", "TAB": "Tab",
    "SPACE": "Space", "BACKSPACE": "Bksp", "ESC": "Esc", "ESCAPE": "Esc", "LSHIFT": "L Shift", "RSHIFT": "R Shift",
    "SHIFT": "Shift", "LCTRL": "L Ctrl", "RCTRL": "R Ctrl", "CTRL": "Ctrl", "LALT": "L Alt", "RALT": "R Alt",
    "ALT": "Alt", "CAPSLOCK": "Caps", "INSERT": "Ins", "DELETE": "Del", "HOME": "Home", "END": "End",
    "PAGEUP": "PgUp", "PAGEDOWN": "PgDn", "SEMICOLON": ";", "COMMA": ",", "PERIOD": ".", "SLASH": "/",
    "BACKSLASH": "\\", "MINUS": "-", "EQUALS": "=", "QUOTE": "'", "APOSTROPHE": "'", "LBRACKET": "[",
    "RBRACKET": "]", "GRAVE": "`", "BACKQUOTE": "`", "NUMADD": "Num +", "NUMSUB": "Num -", "NUMMUL": "Num *",
    "NUMDIV": "Num /", "NUMDEC": "Num .", "NUMENTER": "Num Enter",
}


def device_type(kind, vid=0, pid=0):
    """xbox / ps / generic / keyboard, from the reader's kind (xinput, dinput, keys1, keys2) and the USB ids."""
    kind = str(kind or "").lower()
    if kind.startswith("keys"):
        return KEYBOARD
    if kind == "xinput":
        return XBOX
    if kind == "dinput" and int(vid or 0) == VID_SONY:
        return PS
    return GENERIC


def glyph(dtype, source):
    """One input as the page draws it: dict(shape, text, tone, dir). shape is one of face (round lettered button),
    ps (round button with a drawn square/cross/circle/triangle; text names the symbol), bumper, trigger, menu,
    click (stick press), touch, dpad, stick (text L or R), key (keycap), num (a numbered button)."""
    src = str(source or "").strip().upper()
    if dtype == KEYBOARD:
        if re.fullmatch(r"NUM\d", src):
            text = "Num " + src[3:]
        else:
            text = _KEY_TEXT.get(src) or (src if len(src) <= 3 else src.title())
        return dict(shape="key", text=text, tone="", dir="")
    if dtype == XBOX:
        if src in _XBOX:
            shape, text, tone = _XBOX[src]
            return dict(shape=shape, text=text, tone=tone, dir="")
        m = re.fullmatch(r"([DLR])(UP|DOWN|LEFT|RIGHT)", src)
        if m:
            side, d = m.group(1), _STICK_DIR[m.group(2)]
            return dict(shape="dpad", text="", tone="", dir=d) if side == "D" else dict(shape="stick", text=side, tone="", dir=d)
        return dict(shape="num", text=src, tone="", dir="")
    m = re.fullmatch(r"HAT\d?_(UP|DOWN|LEFT|RIGHT)", src)
    if m:
        return dict(shape="dpad", text="", tone="", dir=_STICK_DIR[m.group(1)])
    axes = _PS_AXIS if dtype == PS else _AXIS
    if src in axes:
        side, d = axes[src]
        return dict(shape="stick", text=side, tone="", dir=d)
    if dtype == PS and src in _PS:
        shape, text, tone = _PS[src]
        return dict(shape=shape, text=text, tone=tone, dir="")
    m = re.fullmatch(r"B(\d+)", src)
    if m:
        return dict(shape="num", text=m.group(1), tone="", dir="")
    return dict(shape="num", text=src, tone="", dir="")


# The same physical button in the other family's names (XInput <-> a PlayStation pad's DirectInput numbering).
_XBOX_TO_PS = {"X": "B1", "A": "B2", "B": "B3", "Y": "B4", "LB": "B5", "RB": "B6", "LT": "B7", "RT": "B8",
               "BACK": "B9", "START": "B10", "LS": "B11", "RS": "B12"}
_PS_TO_XBOX = {v: k for k, v in _XBOX_TO_PS.items()}


def restyle(dtype, source, style):
    """The glyph of `source` on a `dtype` pad drawn in the launcher's button-prompt style ("xbox", "ps"; anything else,
    a keyboard, or a button without a counterpart keeps the pad's own look)."""
    if style not in (XBOX, PS) or dtype not in (XBOX, PS) or style == dtype:
        return glyph(dtype, source)
    src = str(source or "").strip().upper()
    table = _XBOX_TO_PS if dtype == XBOX else _PS_TO_XBOX
    if src in table:
        return glyph(style, table[src])
    return glyph(dtype, source)           # d-pad and sticks look the same in both families


def glyph_text(dtype, source):
    """The same input as plain words (screen readers, the old row value, tests)."""
    g = glyph(dtype, source)
    if g["shape"] == "ps":
        return {"square": "□", "cross": "✕", "circle": "○", "triangle": "△"}[g["text"]]
    if g["shape"] == "dpad":
        return "D-pad " + {"up": "↑", "down": "↓", "left": "←", "right": "→"}[g["dir"]]
    if g["shape"] == "stick":
        return g["text"] + " stick " + {"up": "↑", "down": "↓", "left": "←", "right": "→"}[g["dir"]]
    return g["text"]


# ---------------------------------------------------------------------- Tekken notation for the input test

_FACE = (("SQUARE", "1"), ("TRIANGLE", "2"), ("CROSS", "3"), ("CIRCLE", "4"))
_OTHER = ("L1", "R1", "L2", "R2", "L3", "R3", "SELECT", "START")


def notation(buttons):
    """Held PS3 buttons (names: UP DOWN LEFT RIGHT SQUARE TRIANGLE CROSS CIRCLE L1 .. START) -> Tekken notation as a
    player facing right reads it: u d b f, d/f, 1+2, ... ("" when nothing is held). Opposite directions stay visible:
    these are held bindings, before the game's SOCD filtering."""
    held = {str(b).upper() for b in buttons}
    v = [text for name, text in (("UP", "u"), ("DOWN", "d")) if name in held]
    h = [text for name, text in (("LEFT", "b"), ("RIGHT", "f")) if name in held]
    parts = []
    if len(v) == len(h) == 1:
        parts.append(v[0] + "/" + h[0])
    elif v or h:
        parts.append("+".join(v + h))
    face = [digit for name, digit in _FACE if name in held]
    if face:
        parts.append("+".join(face))
    parts += [name for name in _OTHER if name in held]
    return "+".join(parts)
