"""On-screen keyboard actions and view."""
from .nav_common import OSK, OSK_ACTIONS


class Keyboard:
    def _open_osk(self, tid):
        self.osk = dict(tid=tid, text=self.game.a.text_value(tid), row=1, col=0, title="@osk.player_name")
        self.overlay = "osk"

    def _osk(self, a):
        o = self.osk
        length = len(OSK_ACTIONS) if o["row"] == len(OSK) else len(OSK[o["row"]])
        if a == "left":
            o["col"] = (o["col"] - 1) % length
        elif a == "right":
            o["col"] = (o["col"] + 1) % length
        elif a in ("up", "down"):
            to = o["row"] + (-1 if a == "up" else 1)
            if 0 <= to <= len(OSK):
                if to == len(OSK):
                    o["col"] = min(2, o["col"] * 3 // 10)
                elif o["row"] == len(OSK):
                    o["col"] = o["col"] * 3 + 1
                o["row"] = to
        elif a == "x":
            o["text"] = o["text"][:-1]
        elif a == "play":
            self._osk_done()
        elif a == "back":
            self.overlay = None
        elif a == "confirm":
            if o["row"] == len(OSK):
                kind = OSK_ACTIONS[o["col"]][0]
                if kind == "space":
                    o["text"] += " "
                elif kind == "del":
                    o["text"] = o["text"][:-1]
                else:
                    self._osk_done()
            else:
                o["text"] += OSK[o["row"]][o["col"]]

    def type_text(self, text):
        """A physical keyboard in the on-screen keyboard."""
        if self.overlay == "osk":
            self.device = "kb"
            self.osk["text"] += text

    def _osk_done(self):
        if not self._dry("@dry_text"):
            self.game.a.set_text_value(self.osk["tid"], self.osk["text"].strip())
        self.overlay = None

    def _view_osk(self, v):
        o = self.osk
        rows = [[dict(label=ch, row=r, col=c, focused=o["row"] == r and o["col"] == c) for c, ch in enumerate(line)] for r, line in enumerate(OSK)]
        rows.append([dict(label="@" + label, row=len(OSK), col=c, focused=o["row"] == len(OSK) and o["col"] == c) for c, (_k, label) in enumerate(OSK_ACTIONS)])
        v["osk"] = dict(rows=rows, text=o["text"] + "_", title=o["title"])
        v["hint"] = "@osk_hint"
        v["prompts"] = [self.prompt("confirm", "@enter"), self.prompt("x", "@osk.delete"), self.prompt("play", "@osk.done"), self.prompt("back", "@cancel")]

    def click_key(self, row, col):
        if self.overlay == "osk":
            self.osk["row"], self.osk["col"] = row, col
            self.act("confirm")
