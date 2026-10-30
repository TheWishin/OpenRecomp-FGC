"""On-screen keyboard actions and view."""
from .nav_common import OSK, OSK_ACTIONS

ONLINE_KEYS = (
    ("1234567890", "qwertyuiop", "asdfghjkl-", "zxcvbnm_.,"),
    OSK,
    ("!@#$%^&*()", "[]{}<>/\\|=", "+:;\"'`~?-_", ".,01234567"),
)
ONLINE_PASSWORDS = ("online_password", "online_room_password")


class Keyboard:
    def _open_osk(self, tid):
        title = {"online_name": "@online.name", "online_password": "@online.password", "online_server": "@online.server",
                 "online_chat": "@online.chat", "online_room_name": "@online.room_name",
                 "online_room_password": "@online.room_password", "online_room_code": "@online.room_code",
                 "online_friend_name": "@online.friend_name"}.get(tid, "@osk.player_name")
        self.osk = dict(tid=tid, text=self.game.a.text_value(tid), row=1, col=0, title=title, page=0)
        self.overlay = "osk"

    def _osk_keys(self):
        return ONLINE_KEYS[self.osk["page"]] if self.osk["tid"].startswith("online_") else OSK

    def _osk(self, a):
        o = self.osk
        keys = self._osk_keys()
        length = len(OSK_ACTIONS) if o["row"] == len(keys) else len(keys[o["row"]])
        if a == "left":
            o["col"] = (o["col"] - 1) % length
        elif a == "right":
            o["col"] = (o["col"] + 1) % length
        elif a in ("up", "down"):
            to = o["row"] + (-1 if a == "up" else 1)
            if 0 <= to <= len(keys):
                if to == len(keys):
                    o["col"] = min(2, o["col"] * 3 // 10)
                elif o["row"] == len(keys):
                    o["col"] = o["col"] * 3 + 1
                o["row"] = to
        elif a == "x":
            o["text"] = o["text"][:-1]
        elif a == "play":
            self._osk_done()
        elif a == "back":
            self.overlay = None
            self.osk = None
        elif a == "social" and o["tid"].startswith("online_"):
            o["page"] = (o["page"] + 1) % len(ONLINE_KEYS)
        elif a == "confirm":
            if o["row"] == len(keys):
                kind = OSK_ACTIONS[o["col"]][0]
                if kind == "space":
                    o["text"] += " "
                elif kind == "del":
                    o["text"] = o["text"][:-1]
                else:
                    self._osk_done()
            else:
                o["text"] += keys[o["row"]][o["col"]]

    def type_text(self, text):
        """A physical keyboard in the on-screen keyboard."""
        if self.overlay == "osk":
            self.device = "kb"
            self.osk["text"] += text if self.osk["tid"].startswith("online_") else text.upper()

    def _osk_done(self):
        if not self._dry("@dry_text"):
            text = self.osk["text"] if self.osk["tid"] in ONLINE_PASSWORDS else self.osk["text"].strip()
            self.game.a.set_text_value(self.osk["tid"], text)
        self.overlay = None
        self.osk = None

    def _view_osk(self, v):
        o = self.osk
        keys = self._osk_keys()
        rows = [[dict(label=ch, row=r, col=c, focused=o["row"] == r and o["col"] == c) for c, ch in enumerate(line)] for r, line in enumerate(keys)]
        rows.append([dict(label="@" + label, row=len(keys), col=c, focused=o["row"] == len(keys) and o["col"] == c) for c, (_k, label) in enumerate(OSK_ACTIONS)])
        text = "•" * len(o["text"]) if o["tid"] in ONLINE_PASSWORDS else o["text"]
        v["osk"] = dict(rows=rows, text=text + "_", title=o["title"])
        online = o["tid"].startswith("online_")
        v["hint"] = "@online.keyboard_hint" if online else "@osk_hint"
        v["prompts"] = [self.prompt("confirm", "@enter"), self.prompt("x", "@osk.delete"), self.prompt("play", "@osk.done"), self.prompt("back", "@cancel")]
        if online:
            v["prompts"].append(self.prompt("social", "@online.keyboard_page"))

    def click_key(self, row, col):
        if self.overlay == "osk":
            self.osk["row"], self.osk["col"] = row, col
            self.act("confirm")
