"""Quick access drawer actions and view."""
from . import i18n


class Drawer:
    def _drawer_items(self):
        out = [dict(label="@language", value="@language." + self.language, language=True)]
        for g in self.games:
            if g.a.found() and g.a.native_label:
                out.append(dict(label=g.a.native_label, value=g.short, game=g))
        return out

    def _drawer(self, a):
        items = self._drawer_items()
        if a == "up":
            self.drawer_focus = max(0, self.drawer_focus - 1)
        elif a == "down":
            self.drawer_focus = min(len(items) - 1, self.drawer_focus + 1)
        elif a in ("left", "right") and items[self.drawer_focus].get("language"):
            self._cycle_language(1 if a == "right" else -1)
        elif a in ("back", "social"):
            self.overlay = None
        elif a == "confirm":
            if items[self.drawer_focus].get("language"):
                self._cycle_language(1)
                return
            g = items[self.drawer_focus].get("game")
            if g and not self._dry(i18n.message("dry_open", name=g.a.native_label)):
                g.a.open_native()
                self.overlay = None
                self.say(i18n.message("opening", name=g.a.native_label))

    def _cycle_language(self, step):
        codes = i18n.LANGUAGES
        self.language = codes[(codes.index(self.language) + step) % len(codes)]
        self.on_language(self.language)

    def _view_drawer(self, v):
        items = self._drawer_items()
        v["drawer"] = dict(rows=[dict(index=i, label=it["label"], value=it["value"], focused=i == self.drawer_focus) for i, it in enumerate(items)])
        v["hint"] = "@drawer_hint"
        v["prompts"] = [self.prompt("confirm", "@open"), self.prompt("back", "@close")]
