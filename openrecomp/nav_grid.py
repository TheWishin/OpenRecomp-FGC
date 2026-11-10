"""Fighter grid actions and view."""
from . import i18n
from .nav_common import GRID_COLS, uri


class Grid:
    def _fighter_list(self):
        return [dict(key="random", name="@random", image="")] + self.game.a.fighters()

    def _open_fighters(self):
        self.overlay = "fighters"
        keys = [f["key"] for f in self._fighter_list()]
        chosen = self.game.a.chosen_fighter()
        self.grid_focus = keys.index(chosen) if chosen in keys else 0

    def _fighters(self, a):
        items = self._fighter_list()
        n = len(items)
        i = self.grid_focus
        if a == "left" and i > 0:
            self.grid_focus = i - 1
        elif a == "right" and i + 1 < n:
            self.grid_focus = i + 1
        elif a == "up" and i - GRID_COLS >= 0:
            self.grid_focus = i - GRID_COLS
        elif a == "down":
            if i + GRID_COLS < n:
                self.grid_focus = i + GRID_COLS
            elif i // GRID_COLS < (n - 1) // GRID_COLS:
                self.grid_focus = n - 1
        elif a == "back":
            self.overlay = None
        elif a == "x":
            self._cycle_costume(items[i])
        elif a == "confirm":
            if not self._dry(i18n.message("dry_save", name=items[i]["name"])):
                self.game.a.set_fighter(items[i]["key"])
            self.overlay = None

    def _cycle_costume(self, fighter):
        """X in the grid: the focused fighter's next ranked costume, remembered at once (T5DR 1.2.3)."""
        costumes = self.game.a.costumes(fighter["key"]) if fighter["key"] != "random" else []
        if not costumes:
            return
        buttons = [c["button"] for c in costumes]
        current = self.game.a.chosen_costume(fighter["key"])
        following = buttons[(buttons.index(current) + 1) % len(buttons)] if current in buttons else buttons[0]
        if not self._dry(i18n.message("dry_save", name="@fighter.costume")):
            self.game.a.set_costume(fighter["key"], following)

    def _costume_view(self, fighter):
        costumes = self.game.a.costumes(fighter["key"]) if fighter["key"] != "random" else []
        if not costumes:
            return dict(show=False, caption="", value="")
        current = self.game.a.chosen_costume(fighter["key"])
        n = next((k for k, c in enumerate(costumes) if c["button"] == current), 0)
        return dict(show=True, caption="@fighter.costume",
                    value=i18n.message("fighter.costume_value", n=n + 1, button=costumes[n]["name"]))

    def _view_fighters(self, v):
        items = self._fighter_list()
        chosen = self.game.a.chosen_fighter()
        main = self.game.a.main_fighter()
        v["grid"] = dict(main=main, cells=[dict(index=i, name=f["name"], main=f["name"] == main, image=uri(f["image"]), random=f["key"] == "random", focused=i == self.grid_focus, chosen=f["key"] == chosen)
                                           for i, f in enumerate(items)],
                         mosaic=[uri(f["image"]) for f in items[1:5] if f["image"]])
        v["hint"] = "@fighter_hint"
        v["prompts"] = [self.prompt("confirm", "@choose"), self.prompt("back", "@close")]
        costume = self._costume_view(items[min(self.grid_focus, len(items) - 1)]) if items else dict(show=False)
        v["grid"]["costume"] = costume
        if costume["show"]:
            v["hint"] = "@fighter.costume_hint"
            v["prompts"].insert(1, self.prompt("x", "@fighter.costume_change"))

    def click_cell(self, index):
        self.grid_focus = index
        self.act("confirm")
