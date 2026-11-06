"""Tekken 4's controls.ini: the file the T4 runtime reads for its pad bindings (PS2Recomp patch 99-ps2xRuntime-pad-bindings,
ps2_pad_bindings.h; docs/INPUT.md section 4 of the Tekken 4 repo). No Qt, no game install, no devices: text in, text out.

    [player1]            ; player1 = pad port 1, player2 = port 2
    device = auto        ; auto | none | keyboard | xinput | xinput:0..3, joined with + (keyboard+xinput:1)
    [player1.pad]        ; XInput bindings: TARGET = SOURCE SOURCE ... (a button that is not listed keeps its default)
    1 = X LB
    [player1.keys]       ; keyboard bindings, same rules (player 2 has no default keys)
    1 = U

Only which physical input is which PS2 button is stored here; the game, its state and netplay's data never see the file.
The launcher stores overrides only, so a file that lists nothing and says `device = auto` is the game's fixed layout.
"""
import os
import re
import tempfile
import time


def _replace_with_retry(temporary, path, text, seconds=2.0):
    """os.replace onto an existing controls.ini fails on Windows while another program has it open (the running game
    re-reads it every second, an antivirus scans the file the first save just wrote): a player's FIRST binding saved,
    the second did not. Retry for a moment; if the file stays held, write it in place (the runtime ignores a file it
    cannot parse and re-reads it a second later), and only fail when even that is refused."""
    deadline = time.monotonic() + seconds
    delay = 0.05
    while True:
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                break
            time.sleep(delay)
            delay = min(delay * 2, 0.4)
    with open(path, "w", encoding="utf-8", newline="\r\n") as stream:
        stream.write(text)
    try:
        os.unlink(temporary)
    except OSError:
        pass

PLAYERS = 2
KIND_PAD, KIND_KEYS = "pad", "keys"
KINDS = (KIND_PAD, KIND_KEYS)
DEVICE_KEYS, DEVICE_PAD = "keys1", "xinput"         # the page's device kinds (pad_glyphs.device_type)
KEYBOARD_ID, PAD_ID, NO_PAD_ID = "t4:keyboard", "t4:xinput:", "t4:pad"      # the page's row ids
FILE_NAME = "controls.ini"
PRESET_DEFAULT = "default"
AUTO_PAD = -1                      # `xinput`: the next free XInput pad in order

# (slot the Pad bindings page shows, group, target written to the file). 1 2 3 4 are Tekken's names for the four attacks.
SLOTS = (("1", "attack", "1"), ("2", "attack", "2"), ("3", "attack", "3"), ("4", "attack", "4"),
         ("START", "menu", "START"), ("SELECT", "menu", "SELECT"), ("L1", "menu", "L1"), ("R1", "menu", "R1"),
         ("L2", "menu", "L2"), ("R2", "menu", "R2"), ("L3", "menu", "L3"), ("R3", "menu", "R3"),
         ("UP", "dir", "UP"), ("DOWN", "dir", "DOWN"), ("LEFT", "dir", "LEFT"), ("RIGHT", "dir", "RIGHT"))
SLOT_IDS = tuple(s for s, _g, _t in SLOTS)
GROUP = {s: g for s, g, _t in SLOTS}
# Combo slots: one source pressing several attacks at once. The file has no such thing: the runtime presses every target
# a source is listed under, so a combo is "this source is in the lists of 1 and 3 and 4". Page slot id = "1+3+4".
COMBO_IDS = ("1+2", "3+4", "1+3", "2+4", "1+2+3+4", "1+4", "2+3", "1+2+3", "1+3+4", "2+3+4", "1+2+4")
COMBO_TARGETS = {c: tuple(c.split("+")) for c in COMBO_IDS}
COMBO_BY_SET = {frozenset(t): c for c, t in COMBO_TARGETS.items()}
PAGE_SLOT_IDS = SLOT_IDS + COMBO_IDS               # what the page shows and edits (the file only has SLOT_IDS)
GROUP.update({c: "macro" for c in COMBO_IDS})
# the PS2 button each slot presses (the page's input test names)
PS2_BUTTON = {"1": "SQUARE", "2": "TRIANGLE", "3": "CROSS", "4": "CIRCLE"}
TARGET_SLOT = {"1": "1", "2": "2", "3": "3", "4": "4", "LP": "1", "RP": "2", "LK": "3", "RK": "4",
               "SQUARE": "1", "TRIANGLE": "2", "CROSS": "3", "CIRCLE": "4"}
for _slot in SLOT_IDS:
    TARGET_SLOT.setdefault(_slot, _slot)

# The runtime's fixed layout (patch 60 fromXInput, patch 31 asyncPadMask): what an unlisted button does.
PAD_DEFAULT = {"1": ("X",), "2": ("Y",), "3": ("A",), "4": ("B",), "START": ("START",), "SELECT": ("BACK",),
               "L1": ("LB",), "R1": ("RB",), "L2": ("LT",), "R2": ("RT",), "L3": ("LS",), "R3": ("RS",),
               "UP": ("DUP", "LUP"), "DOWN": ("DDOWN", "LDOWN"), "LEFT": ("DLEFT", "LLEFT"), "RIGHT": ("DRIGHT", "LRIGHT")}
KEYS_DEFAULT = ({"1": ("LEFT", "Z", "NUM0"), "2": ("UP", "V", "NUM1"), "3": ("DOWN", "X", "SPACE"),
                 "4": ("RIGHT", "C", "ESC"), "START": ("ENTER",), "SELECT": ("TAB",), "L1": ("Q",), "R1": ("E",),
                 "L2": ("LSHIFT",), "R2": ("RSHIFT",), "L3": (), "R3": (),
                 "UP": ("W",), "DOWN": ("S",), "LEFT": ("A",), "RIGHT": ("D",)},
                {slot: () for slot in SLOT_IDS})                       # player 2 has no keyboard by default

PAD_SOURCES = ("A", "B", "X", "Y", "LB", "RB", "LT", "RT", "BACK", "START", "LS", "RS", "DUP", "DDOWN", "DLEFT",
               "DRIGHT", "LUP", "LDOWN", "LLEFT", "LRIGHT", "RUP", "RDOWN", "RLEFT", "RRIGHT")
# Keyboard names -> virtual-key codes (ps2_pad_bindings.h kKeyNames; the first name of a code is the one written).
KEY_NAMES = (
    ("UP", 0x26), ("DOWN", 0x28), ("LEFT", 0x25), ("RIGHT", 0x27), ("SPACE", 0x20), ("ENTER", 0x0D), ("RETURN", 0x0D),
    ("TAB", 0x09), ("ESC", 0x1B), ("ESCAPE", 0x1B), ("BACKSPACE", 0x08), ("LSHIFT", 0xA0), ("RSHIFT", 0xA1),
    ("LCTRL", 0xA2), ("RCTRL", 0xA3), ("LALT", 0xA4), ("RALT", 0xA5), ("CAPSLOCK", 0x14), ("INSERT", 0x2D),
    ("DELETE", 0x2E), ("HOME", 0x24), ("END", 0x23), ("PGUP", 0x21), ("PGDN", 0x22),
    ("NUM0", 0x60), ("NUM1", 0x61), ("NUM2", 0x62), ("NUM3", 0x63), ("NUM4", 0x64), ("NUM5", 0x65), ("NUM6", 0x66),
    ("NUM7", 0x67), ("NUM8", 0x68), ("NUM9", 0x69), ("NUMADD", 0x6B), ("NUMSUB", 0x6D), ("NUMMUL", 0x6A),
    ("NUMDIV", 0x6F), ("NUMDEC", 0x6E), ("SEMICOLON", 0xBA), ("EQUALS", 0xBB), ("COMMA", 0xBC), ("MINUS", 0xBD),
    ("PERIOD", 0xBE), ("SLASH", 0xBF), ("GRAVE", 0xC0), ("LBRACKET", 0xDB), ("BACKSLASH", 0xDC), ("RBRACKET", 0xDD),
    ("APOSTROPHE", 0xDE), ("QUOTE", 0xDE),
    ("F1", 0x70), ("F2", 0x71), ("F3", 0x72), ("F4", 0x73), ("F5", 0x74), ("F6", 0x75), ("F7", 0x76), ("F8", 0x77),
    ("F9", 0x78), ("F10", 0x79), ("F11", 0x7A), ("F12", 0x7B))
KEY_VK = {name: vk for name, vk in KEY_NAMES}
KEY_VK.update({chr(c): c for c in range(ord("A"), ord("Z") + 1)})
KEY_VK.update({chr(c): c for c in range(ord("0"), ord("9") + 1)})
VK_NAME = {}
for _name, _vk in KEY_NAMES:
    VK_NAME.setdefault(_vk, _name)
VK_NAME.update({vk: name for name, vk in KEY_VK.items() if len(name) == 1})
GAME_KEYS = ("F11",)               # the game window's fullscreen key: never a game button

# Presets: (id, label key, hint key, {kind: {slot: sources}}). `default` is "no overrides at all".
PRESETS = (
    ("default", "@controls.preset.default", "@controls.preset.default_hint", {"pad": {}, "keys": {}}),
    ("t4_arcade", "@controls.preset.t4_arcade", "@controls.preset.t4_arcade_hint", {
        # 1 2 3 4 in a row: X Y RB RT; the face buttons A B and the bumpers' neighbours stay useful as R1 R2
        "pad": {"1": ("X",), "2": ("Y",), "3": ("RB",), "4": ("RT",), "L1": ("LB",), "R1": ("A",), "L2": ("LT",),
                "R2": ("B",)},
        "keys": {"1": ("U",), "2": ("I",), "3": ("J",), "4": ("K",), "L1": ("Y",), "R1": ("P",), "L2": ("H",),
                 "R2": ("SEMICOLON",), "START": ("ENTER",), "SELECT": ("BACKSPACE",), "UP": ("W",), "DOWN": ("S",),
                 "LEFT": ("A",), "RIGHT": ("D",)}}),
    ("t4_combos", "@controls.preset.t4_combos", "@controls.preset.t4_combos_hint", {
        # 1 2 on X Y and 3 4 on A B as before; 1+2 on RB, 3+4 on RT (they stop being R1 / R2), 1+3+4 left for you
        "pad": {"1+2": ("RB",), "3+4": ("RT",)},
        "keys": {"1": ("U",), "2": ("I",), "3": ("J",), "4": ("K",), "1+2": ("O",), "3+4": ("L",), "START": ("ENTER",),
                 "SELECT": ("BACKSPACE",), "UP": ("W",), "DOWN": ("S",), "LEFT": ("A",), "RIGHT": ("D",)}}),
    ("numpad", "@controls.preset.numpad", "@controls.preset.numpad_hint", {
        "keys": {"1": ("NUM4",), "2": ("NUM5",), "3": ("NUM1",), "4": ("NUM2",), "L1": ("NUM7",), "R1": ("NUM8",),
                 "L2": ("NUM9",), "R2": ("NUM0",), "START": ("NUMADD",), "SELECT": ("NUMSUB",), "UP": ("UP",),
                 "DOWN": ("DOWN",), "LEFT": ("LEFT",), "RIGHT": ("RIGHT",)}}),
)
PRESET_BY_ID = {p[0]: p for p in PRESETS}


def presets_for(kind):
    return [(pid, label) for pid, label, _hint, plans in PRESETS if kind in plans]


def preset_hint(preset_id):
    return PRESET_BY_ID[preset_id][2]


def _upper(text):
    return str(text).strip().upper()


def key_ok(name):
    return _upper(name) in KEY_VK


def canonical_key(name):
    """A key name as the file writes it (the first name of its code): RETURN -> ENTER, QUOTE -> APOSTROPHE."""
    return VK_NAME.get(KEY_VK.get(_upper(name), -1), _upper(name))


class Player:
    """One player's devices and overrides. `pad`: None = no pad, AUTO_PAD (-1) = the next free one, 0..3 = that slot."""

    def __init__(self, index):
        self.index = index
        self.keyboard = index == 0
        self.pad = AUTO_PAD
        self.maps = {"pad": {}, "keys": {}}      # slot -> list of sources; only the overrides

    def default_device(self):
        return self.keyboard == (self.index == 0) and self.pad == AUTO_PAD

    def device_text(self):
        if self.default_device():
            return "auto"
        parts = []
        if self.keyboard:
            parts.append("keyboard")
        if self.pad is not None:
            parts.append("xinput" if self.pad == AUTO_PAD else "xinput:%d" % self.pad)
        return "+".join(parts) or "none"

    def set_device(self, text):
        """Parses a `device =` value like the runtime: unknown words leave the device as it is."""
        tokens = [t for t in re.split(r"[\s+,]+", str(text).strip()) if t]
        if not tokens:
            return False
        keyboard, pad, auto = False, None, False
        for token in tokens:
            t = token.upper()
            if t == "AUTO":
                auto = True
            elif t == "NONE":
                pass
            elif t == "KEYBOARD":
                keyboard = True
            elif t == "XINPUT":
                pad = AUTO_PAD
            elif re.fullmatch(r"XINPUT:[0-3]", t):
                pad = int(t[-1])
            else:
                return False
        if auto:
            keyboard, pad = self.index == 0, AUTO_PAD
        self.keyboard, self.pad = keyboard, pad
        return True


class Controls:
    """The whole file. `load` never fails on a missing file (that is the default layout); `save` writes atomically."""

    def __init__(self, path=None):
        self.path = path
        self.players = [Player(i) for i in range(PLAYERS)]
        self.extra = []                    # lines of sections this launcher does not know, kept as they are
        self.warnings = []

    # ------------------------------------------------------------------ reading
    @classmethod
    def load(cls, path):
        controls = cls(path)
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as stream:
                controls.parse(stream.read())
        except OSError:
            pass
        return controls

    def parse(self, text):
        self.warnings = []
        player, part = None, None
        extra, in_extra = [], False
        for number, raw in enumerate(text.splitlines(), 1):
            line = re.split(r"[;#]", raw, 1)[0].strip()
            if not line:
                if in_extra:
                    extra.append(raw)
                continue
            if line.startswith("["):
                name = line[1:line.find("]")].strip().upper() if "]" in line else ""
                m = re.fullmatch(r"PLAYER([12])(?:\.(PAD|KEYS))?", name)
                in_extra = not m
                if m:
                    player, part = self.players[int(m.group(1)) - 1], (m.group(2) or "device").lower()
                else:
                    player, part = None, None
                    if in_extra:
                        extra.append(raw)
                continue
            if player is None:
                if in_extra:
                    extra.append(raw)
                continue
            if "=" not in line:
                self.warnings.append((number, raw))
                continue
            key, value = (s.strip() for s in line.split("=", 1))
            if part == "device":
                if key.upper() == "DEVICE" and not player.set_device(value):
                    self.warnings.append((number, raw))
                continue
            slot = TARGET_SLOT.get(key.upper())
            if slot is None:
                self.warnings.append((number, raw))
                continue
            kind = "pad" if part == "pad" else "keys"
            names = []
            for word in re.split(r"[\s,]+", value):
                if not word or word.upper() == "NONE":
                    continue
                if kind == "pad" and word.upper() in PAD_SOURCES:
                    names.append(word.upper())
                elif kind == "keys" and key_ok(word):
                    names.append(canonical_key(word))
                else:
                    self.warnings.append((number, raw))
            player.maps[kind][slot] = list(dict.fromkeys(names))
        self.extra = extra
        return self

    # ------------------------------------------------------------------ what the buttons do
    def sources(self, player, kind, slot):
        """The sources that press `slot` for this player: the file's list, else the fixed layout's. A combo slot id
        ("1+3+4") answers with the sources that press exactly those attacks together."""
        if slot in COMBO_TARGETS:
            return self.combo_sources(player, kind, slot)
        p = self.players[player]
        if slot in p.maps[kind]:
            return list(p.maps[kind][slot])
        return list((PAD_DEFAULT if kind == "pad" else KEYS_DEFAULT[player])[slot])

    # ------------------------------------------------------------------ combos
    def attack_set(self, player, kind, source):
        """The attacks (1 2 3 4) this source presses now."""
        return frozenset(t for t in ("1", "2", "3", "4") if source in self.sources(player, kind, t))

    def _attack_sources(self, player, kind):
        out = []
        for t in ("1", "2", "3", "4"):
            out += [s for s in self.sources(player, kind, t) if s not in out]
        return out

    def combo_sources(self, player, kind, combo):
        want = frozenset(COMBO_TARGETS[combo])
        return [s for s in self._attack_sources(player, kind) if self.attack_set(player, kind, s) == want]

    def is_combo_source(self, player, kind, source):
        return len(self.attack_set(player, kind, source)) > 1

    def plain_sources(self, player, kind, slot):
        """What the page shows for a plain slot: its sources without the ones that are a combo."""
        return [s for s in self.sources(player, kind, slot) if not (slot in ("1", "2", "3", "4")
                                                                     and self.is_combo_source(player, kind, s))]

    def holders(self, player, kind, source):
        """The page slots this source presses now (a combo counts once, as its own slot)."""
        attacks = self.attack_set(player, kind, source)
        out = []
        for slot in SLOT_IDS:
            if slot in attacks and len(attacks) > 1:
                continue
            if source in self.sources(player, kind, slot):
                out.append(slot)
        if len(attacks) > 1 and attacks in COMBO_BY_SET:
            out.append(COMBO_BY_SET[attacks])
        return out

    def bind_combo(self, player, kind, combo, sources):
        """Makes `sources` press exactly the attacks of `combo`: each is added to those targets' lists (the targets' other
        sources stay, defaults written out) and taken off every other slot. Sources the combo had before are dropped."""
        targets = COMBO_TARGETS[combo]
        for old in self.combo_sources(player, kind, combo):
            if old not in sources:
                self.unbind_source(player, kind, old, targets)
        for source in dict.fromkeys(sources):
            self.release(player, kind, source, keep=None, except_slots=targets)
            for t in targets:
                have = self.sources(player, kind, t)
                if source not in have:
                    self.bind(player, kind, t, have + [source])

    def unbind_source(self, player, kind, source, slots):
        for t in slots:
            self.bind(player, kind, t, [s for s in self.sources(player, kind, t) if s != source])

    def clear_combo(self, player, kind, combo):
        """The combo's sources stop pressing those attacks; nothing else changes."""
        for source in self.combo_sources(player, kind, combo):
            self.unbind_source(player, kind, source, COMBO_TARGETS[combo])

    def set_plain(self, player, kind, slot, sources):
        """bind() for a plain slot that keeps the combo sources listed under it (a combo is not this slot's)."""
        keep = [s for s in self.sources(player, kind, slot) if slot in ("1", "2", "3", "4")
                and self.is_combo_source(player, kind, s)]
        self.bind(player, kind, slot, list(sources) + [s for s in keep if s not in sources])

    def overridden(self, player, kind, slot):
        return slot in self.players[player].maps[kind]

    def is_default(self):
        return all(p.default_device() and not p.maps["pad"] and not p.maps["keys"] for p in self.players)

    def users(self, player, kind, source, exclude=None):
        """The slots (other than `exclude`) that `source` presses now."""
        return [slot for slot in SLOT_IDS if slot != exclude and source in self.sources(player, kind, slot)]

    # ------------------------------------------------------------------ editing
    def bind(self, player, kind, slot, sources):
        self.players[player].maps[kind][slot] = list(dict.fromkeys(sources))

    def clear(self, player, kind, slot):
        self.players[player].maps[kind][slot] = []

    def release(self, player, kind, source, keep=None, except_slots=()):
        """Takes `source` off every slot but `keep` / `except_slots` (a binding moved to another slot)."""
        for slot in SLOT_IDS:
            if slot != keep and slot not in except_slots and source in self.sources(player, kind, slot):
                self.bind(player, kind, slot, [s for s in self.sources(player, kind, slot) if s != source])

    def reset(self, player, kind):
        self.players[player].maps[kind] = {}

    def apply_preset(self, player, kind, preset_id):
        plans = PRESET_BY_ID[preset_id][3]
        if kind not in plans:
            raise KeyError(preset_id)
        self.reset(player, kind)
        for slot, sources in plans[kind].items():
            if slot not in COMBO_TARGETS:
                self.bind(player, kind, slot, sources)
        for slot, sources in plans[kind].items():
            if slot in COMBO_TARGETS:
                self.bind_combo(player, kind, slot, sources)

    def effective(self, player, kind):
        return {slot: self.sources(player, kind, slot) for slot in SLOT_IDS}

    def current_preset(self, player, kind):
        """The preset this player's bindings equal now, or "custom"."""
        mine = self.effective(player, kind)
        for pid, _label, _hint, plans in PRESETS:
            if kind in plans:
                probe = Controls()
                probe.apply_preset(player, kind, pid)
                if probe.effective(player, kind) == mine:
                    return pid
        return "custom"

    # ------------------------------------------------------------------ devices
    def resolve(self, connected):
        """{XInput slot: player} for the connected slots, the way the runtime orders them: pinned slots first, the
        auto players take the free slots in player order. (keyboard player = keyboard_player())"""
        connected = sorted(set(connected))
        pinned = {p.pad for p in self.players if isinstance(p.pad, int) and p.pad >= 0}
        free = [s for s in connected if s not in pinned]
        out, rank = {}, 0
        for p in self.players:
            if p.pad is None:
                continue
            if p.pad >= 0:
                if p.pad in connected:
                    out[p.pad] = p.index
            else:
                if rank < len(free):
                    out[free[rank]] = p.index
                rank += 1
        return out

    def keyboard_player(self):
        return next((p.index for p in self.players if p.keyboard), None)

    def pinned_player(self, slot):
        return next((p.index for p in self.players if p.pad == slot), None)

    def assign_keyboard(self, player):
        """None: the game's own order (player 1). Otherwise only that player has the keyboard."""
        target = 0 if player is None else player
        for p in self.players:
            p.keyboard = p.index == target

    def assign_pad(self, slot, player):
        """Pins XInput slot `slot` to `player`; None frees it again (a player pinned to it goes back to `next free`)."""
        for p in self.players:
            if p.pad == slot and p.index != player:
                p.pad = AUTO_PAD
        if player is not None:
            self.players[player].pad = slot

    # ------------------------------------------------------------------ writing
    def text(self):
        out = ["; Tekken 4 controls, written by the OpenRecomp launcher. The game reads it at start and when it changes.",
               "; Only the buttons listed here differ from the game's fixed layout; delete this file to go back to it.",
               "; device = auto | none | keyboard | xinput | xinput:0..3 (joined with +)",
               "; Pad sources: A B X Y LB RB LT RT BACK START LS RS DUP DDOWN DLEFT DRIGHT LUP LDOWN LLEFT LRIGHT RUP ...",
               "; Targets: 1 2 3 4 (Square Triangle Cross Circle) START SELECT L1 R1 L2 R2 L3 R3 UP DOWN LEFT RIGHT"]
        for p in self.players:
            out += ["", "[player%d]" % (p.index + 1), "device = " + p.device_text()]
            for kind in KINDS:
                lines = [(slot, p.maps[kind][slot]) for slot in SLOT_IDS if slot in p.maps[kind]]
                if lines:
                    out += ["[player%d.%s]" % (p.index + 1, kind)]
                    out += ["%s = %s" % (slot, " ".join(sources) if sources else "NONE") for slot, sources in lines]
        if self.extra:
            out += [""] + self.extra
        return "\n".join(out) + "\n"

    def save(self, path=None):
        """Writes the file through a temporary one and a rename, so the game never reads half of it."""
        path = path or self.path
        folder = os.path.dirname(os.path.abspath(path))
        os.makedirs(folder, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=folder, prefix=".controls-", suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\r\n") as stream:
                stream.write(self.text())
            _replace_with_retry(temporary, path, self.text())
        except Exception:
            if os.path.exists(temporary):
                os.unlink(temporary)
            raise
        self.path = path
