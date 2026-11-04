"""On-screen keyboard actions and view."""
from .nav_common import OSK, OSK_ACTIONS
from . import i18n

ONLINE_KEYS = (
    ("1234567890", "qwertyuiop", "asdfghjkl-", "zxcvbnm_.,"),
    OSK,
    ("!@#$%^&*()", "[]{}<>/\\|=", "+:;\"'`~?-_", ".,01234567"),
)
ONLINE_PASSWORDS = ("online_password", "online_room_password", "online_current_password", "online_new_password",
                    "online_repeat_password", "online_recovery_code")
CHAT_TEXT_LIMITS = dict(online_private_chat=200, online_private_report_reason=200, support_note=300, support_contact=80)
PASTE_LIMIT = 256       # one paste: a password, an address, a name -- never a whole document
TEXT_FIELDS = {
    "library_repository": 140, "nickname": 64, "name": 64,
    "online_name": 64, "online_password": 128, "online_server": 256, "online_address": 256,
    "online_chat": 300, "online_room_name": 64, "online_room_password": 128, "online_room_code": 40,
    "online_friend_name": 64, "online_profile_name": 64, "online_tour_name": 64,
    "online_tour_clock": 32, "online_tour_dq": 32, "online_current_password": 128,
    "online_new_password": 128, "online_repeat_password": 128, "online_recovery_code": 128,
    "online_block_name": 64, "online_fingerprint": 256, **CHAT_TEXT_LIMITS,
}
CHAT_SUBMITS = {"online_chat": "send_chat", "online_private_chat": "private_send"}


def _free_text(tid):
    """Fields typed as they are (lower case, symbols page): the online fields, a game source, a report's note."""
    return tid.startswith(("online_", "support_")) or tid == "library_repository"


class Keyboard:
    def field_metadata(self, tid):
        """Stable native-edit contract; the view never calls an adapter directly."""
        if tid not in TEXT_FIELDS:
            return {}
        secret = tid in ONLINE_PASSWORDS
        draft = self.__dict__.get("native_repository", "") if tid == "library_repository" else self.game.a.text_value(tid)
        if secret and getattr(self, "native_edit", "") != tid:
            draft = "\u2022" * len(draft)
        return dict(fieldId=tid, fieldType="password" if secret else "chat" if tid in CHAT_SUBMITS else "text",
                    limit=TEXT_FIELDS[tid], secret=secret, draft=i18n.literal(draft),
                    submitId="library_preview" if tid == "library_repository" else CHAT_SUBMITS.get(tid, ""))

    def begin_edit(self, tid):
        library = tid == "library_repository" and self.overlay == "dialog" and self.confirm_kind == "library_source"
        if tid not in TEXT_FIELDS or self.overlay and not library:
            return False
        if library:
            self.device = "kb"
            self.native_edit = tid
            self.overlay = "native"
            return True
        items = self.items()
        index = next((n for n, it in enumerate(items) if (it.get("id") == tid or it.get("opens") == "text:" + tid)
                      and not it.get("disabled")), None)
        if index is None:
            return False
        self.device = "kb"
        self.native_edit = tid
        self.focus[self.key()] = index
        if tid in ("nickname", "name"):
            self.overlay = "native"
        return True

    def edit_text(self, tid, text):
        if tid != getattr(self, "native_edit", "") or tid not in TEXT_FIELDS or not isinstance(text, str):
            return False
        # TextInput owns selection, clipboard and composition. Only committed single-line text crosses this boundary.
        value = "".join(ch for ch in text if ch.isprintable())[:TEXT_FIELDS[tid]]
        if tid == "library_repository":
            self.native_repository = value
        elif not self.dry:
            self.game.a.set_text_value(tid, value)
        return True

    def finish_edit(self, tid, submit=False):
        if tid != getattr(self, "native_edit", "") or not tid:
            return False
        self.native_edit = ""
        if self.overlay == "native":
            self.overlay = None
        if tid == "library_repository":
            if submit:
                self._preview_game(self.__dict__.get("native_repository", "").strip())
            return True
        if submit:
            self._submit_field(tid)
        return True

    def _submit_field(self, tid):
        action = CHAT_SUBMITS.get(tid)
        if action and self.game.a.text_value(tid).strip():
            item = next((it for it in self.items() if it.get("id") == action and not it.get("disabled")), None)
            if item and item.get("run"):
                self.sounded("confirm", item["run"])

    def _native_action(self, action):
        tid = getattr(self, "native_edit", "")
        if action == "back":
            self.finish_edit(tid)
        elif action == "confirm" and self.device in ("xbox", "ps"):
            self.native_edit = ""
            if self.overlay == "native":
                self.overlay = None
            self._open_osk(tid)

    def _view_native(self, v):
        tid = getattr(self, "native_edit", "")
        field = self.field_metadata(tid)
        field["label"] = "@library.repository" if tid == "library_repository" else "@osk.player_name"
        v["nativeField"] = field
        v["nativeDone"], v["nativeCancel"] = "@osk.done", "@cancel"
        v["hint"] = "@library.repository_hint" if tid == "library_repository" else "@osk_hint"
        v["prompts"] = [self.prompt("back", "@cancel")]

    def _edit_field(self, tid):
        if self.device == "kb" and tid in TEXT_FIELDS:
            self.begin_edit(tid)
            return
        self._open_osk(tid)

    def _open_osk(self, tid):
        self.native_edit = ""
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
                 "online_block_name": "@online120.block_name", "online_fingerprint": "@online120.fingerprint",
                 "support_note": "@support.send.note", "support_contact": "@support.send.contact"}.get(tid, "@osk.player_name")
        self.osk = dict(tid=tid, text=self.__dict__.get("native_repository", "") if tid == "library_repository" else self.game.a.text_value(tid), row=1, col=0, title=title, page=0)
        if tid in TEXT_FIELDS:
            self.osk["text"] = self.osk["text"][:TEXT_FIELDS[tid]]
        self.overlay = "osk"

    def _osk_keys(self):
        return ONLINE_KEYS[self.osk["page"]] if _free_text(self.osk["tid"]) else OSK

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
        elif a == "social" and _free_text(o["tid"]):
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
        text = "".join(ch for ch in text if ch.isprintable())
        o["text"] = text if o.get("all") else o["text"] + text
        o["all"] = False
        if o["tid"] == "library_repository":
            o["text"] = o["text"][:140]
        if o["tid"] in TEXT_FIELDS:
            o["text"] = o["text"][:TEXT_FIELDS[o["tid"]]]

    def type_text(self, text):
        """A physical keyboard in the on-screen keyboard."""
        if self.overlay == "osk":
            self.device = "kb"
            self._osk_append(text if _free_text(self.osk["tid"]) else text.upper())

    def paste_text(self, text):
        """The clipboard into the on-screen keyboard's text (Ctrl+V, Shift+Insert, right-click Paste)."""
        if self.overlay != "osk" or not isinstance(text, str):
            return
        text = text.replace("\r\n", "\n").rstrip("\r\n")
        text = "".join(" " if ch in "\n\r\t" else ch for ch in text if ch.isprintable() or ch in "\n\r\t")
        if not text:
            return
        online = _free_text(self.osk["tid"])
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
        tid = self.osk["tid"]
        saved = not self._dry("@dry_text")
        if saved:
            text = self.osk["text"] if tid in ONLINE_PASSWORDS else self.osk["text"].strip()
            self.game.a.set_text_value(tid, text)
        self.overlay = None
        self.osk = None
        if saved:
            self._submit_field(tid)

    def _view_osk(self, v):
        o = self.osk
        keys = self._osk_keys()
        rows = [[dict(label=ch, row=r, col=c, focused=o["row"] == r and o["col"] == c) for c, ch in enumerate(line)] for r, line in enumerate(keys)]
        rows.append([dict(label="@" + label, row=len(keys), col=c, focused=o["row"] == len(keys) and o["col"] == c) for c, (_k, label) in enumerate(OSK_ACTIONS)])
        text = "•" * len(o["text"]) if o["tid"] in ONLINE_PASSWORDS else o["text"]
        v["osk"] = dict(rows=rows, text=text + ("" if o.get("all") else "_"), title=o["title"], selected=bool(o.get("all")),
                        paste="@osk.paste", copy="@osk.copy", canCopy=o["tid"] not in ONLINE_PASSWORDS)
        online = _free_text(o["tid"])
        v["hint"] = "@library.repository_hint" if o["tid"] == "library_repository" else ("@online.keyboard_hint" if online else "@osk_hint")
        v["prompts"] = [self.prompt("confirm", "@enter"), self.prompt("x", "@osk.delete"), self.prompt("play", "@osk.done"), self.prompt("back", "@cancel")]
        if online:
            v["prompts"].append(self.prompt("social", "@online.keyboard_page"))

    def click_key(self, row, col):
        if self.overlay == "osk":
            self.osk["row"], self.osk["col"] = row, col
            self.act("confirm")
