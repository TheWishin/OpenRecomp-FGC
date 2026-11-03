"""On-screen keyboard actions and view."""
from .nav_common import OSK, OSK_ACTIONS

ONLINE_KEYS = (
    ("1234567890", "qwertyuiop", "asdfghjkl-", "zxcvbnm_.,"),
    OSK,
    ("!@#$%^&*()", "[]{}<>/\\|=", "+:;\"'`~?-_", ".,01234567"),
)
ONLINE_PASSWORDS = ("online_password", "online_room_password", "online_current_password", "online_new_password",
                    "online_repeat_password", "online_recovery_code")
CHAT_TEXT_LIMITS = dict(online_private_chat=200, online_private_report_reason=200)
PASTE_LIMIT = 256       # one paste: a password, an address, a name -- never a whole document


class Keyboard:
    def _open_osk(self, tid):
        title = {"library_repository": "@library.repository", "online_name": "@online.name", "online_password": "@online.password", "online_server": "@online.server",
                 "online_address": "@t4.direct_address",
                 "online_chat": "@online.chat", "online_room_name": "@online.room_name",
                 "online_private_chat": "@online_chat.private_compose",
                 "online_private_report_reason": "@online_chat.report_reason",
                 "online_room_password": "@online.room_password", "online_room_code": "@online.room_code",
                 "online_friend_name": "@online.friend_name", "online_tour_name": "@online.tour_name",
                 "online_tour_clock": "@online.tour_clock", "online_tour_dq": "@online.tour_dq",
                 "online_profile_name": "@online.profile_lookup",
                 "online_current_password": "@online120.current_password", "online_new_password": "@online120.new_password",
                 "online_repeat_password": "@online120.repeat_password", "online_recovery_code": "@online120.recovery_code",
                 "online_block_name": "@online120.block_name", "online_fingerprint": "@online120.fingerprint"}.get(tid, "@osk.player_name")
        self.osk = dict(tid=tid, text="" if tid == "library_repository" else self.game.a.text_value(tid), row=1, col=0, title=title, page=0)
        if tid in CHAT_TEXT_LIMITS:
            self.osk["text"] = self.osk["text"][:CHAT_TEXT_LIMITS[tid]]
        self.overlay = "osk"

    def _osk_keys(self):
        return ONLINE_KEYS[self.osk["page"]] if self.osk["tid"].startswith("online_") or self.osk["tid"] == "library_repository" else OSK

    def _osk(self, a):
        o = self.osk
        keys = self._osk_keys()
        if a in ("left", "right", "up", "down", "social"):
            o["all"] = False
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
            self._osk_delete()
        elif a == "play":
            self._osk_done()
        elif a == "back":
            self.overlay = None
            self.osk = None
        elif a == "social" and (o["tid"].startswith("online_") or o["tid"] == "library_repository"):
            o["page"] = (o["page"] + 1) % len(ONLINE_KEYS)
        elif a == "confirm":
            if o["row"] == len(keys):
                kind = OSK_ACTIONS[o["col"]][0]
                if kind == "space":
                    self._osk_append(" ")
                elif kind == "del":
                    self._osk_delete()
                else:
                    self._osk_done()
            else:
                self._osk_append(keys[o["row"]][o["col"]])

    def _osk_delete(self):
        o = self.osk
        o["text"] = "" if o.get("all") else o["text"][:-1]
        o["all"] = False

    def _osk_append(self, text):
        o = self.osk
        o["text"] = text if o.get("all") else o["text"] + text
        o["all"] = False
        if o["tid"] == "library_repository":
            o["text"] = o["text"][:140]
        if o["tid"] in CHAT_TEXT_LIMITS:
            o["text"] = o["text"][:CHAT_TEXT_LIMITS[o["tid"]]]

    def type_text(self, text):
        """A physical keyboard in the on-screen keyboard."""
        if self.overlay == "osk":
            self.device = "kb"
            self._osk_append(text if self.osk["tid"].startswith("online_") or self.osk["tid"] == "library_repository" else text.upper())

    def paste_text(self, text):
        """The clipboard into the on-screen keyboard's text (Ctrl+V, Shift+Insert, right-click Paste)."""
        if self.overlay != "osk" or not isinstance(text, str):
            return
        text = text.replace("\r\n", "\n").rstrip("\r\n")
        text = "".join(" " if ch in "\n\r\t" else ch for ch in text if ch.isprintable() or ch in "\n\r\t")
        if not text:
            return
        online = self.osk["tid"].startswith("online_") or self.osk["tid"] == "library_repository"
        self._osk_append(text[:PASTE_LIMIT] if online else text[:PASTE_LIMIT].upper())

    def osk_copy(self, cut=False):
        """The text to the clipboard (there is no cursor: all of it). A password never leaves the launcher."""
        if self.overlay != "osk":
            return
        if self.osk["tid"] in ONLINE_PASSWORDS:
            self.say("@osk.copy_password_blocked")
            return
        if self.osk["text"]:
            self.copy_text(self.osk["text"])
            if cut:
                self.osk["text"] = ""
        self.osk["all"] = False

    def osk_select_all(self):
        """Ctrl+A: the next letter, paste or Delete replaces the whole text."""
        if self.overlay == "osk" and self.osk["text"]:
            self.osk["all"] = True

    def _osk_done(self):
        if self.osk["tid"] == "library_repository":
            source = self.osk["text"].strip()
            self.overlay = None
            self.osk = None
            self._preview_game(source)
            return
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
        v["osk"] = dict(rows=rows, text=text + ("" if o.get("all") else "_"), title=o["title"], selected=bool(o.get("all")),
                        paste="@osk.paste", copy="@osk.copy", canCopy=o["tid"] not in ONLINE_PASSWORDS)
        online = o["tid"].startswith("online_") or o["tid"] == "library_repository"
        v["hint"] = "@library.repository_hint" if o["tid"] == "library_repository" else ("@online.keyboard_hint" if online else "@osk_hint")
        v["prompts"] = [self.prompt("confirm", "@enter"), self.prompt("x", "@osk.delete"), self.prompt("play", "@osk.done"), self.prompt("back", "@cancel")]
        if online:
            v["prompts"].append(self.prompt("social", "@online.keyboard_page"))

    def click_key(self, row, col):
        if self.overlay == "osk":
            self.osk["row"], self.osk["col"] = row, col
            self.act("confirm")
