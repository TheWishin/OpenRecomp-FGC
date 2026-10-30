"""Game shelf input, layout, and selection."""
import os

from . import manifest as mf
from . import i18n
from .nav_common import GAP, SCREEN_W, SECTION_TITLES, SPINE_GAME, SPINE_SLOT, WIDE, badge, uri


class Shelf:
    def tile_ids(self):
        ids = [g.id for g in self.games]
        free = max(1, mf.TOTAL_SLOTS - len(ids))
        return ids + [f"slot{i}" for i in range(free)]

    def game_by_id(self, gid):
        return next((g for g in self.games if g.id == gid), None)

    def _folder_source(self, g):
        if not g.a.found():
            return next((s for s in g.a.sources() if s.get("kind") in ("folder", "file_or_folder")), None)
        return None

    def can_reload_games(self):
        return not self.binding_game and not self._update_busy()

    def set_games(self, games):
        if not self.can_reload_games():
            self.say("@library.busy")
            return False
        if not self.dry:
            try:
                for g in self.games:
                    if getattr(g.a, "online_supported", lambda: False)():
                        g.a.online_close()
            except Exception:  # noqa: BLE001 -- keep a client tracked if its cleanup failed
                self.say("@library.busy")
                return False
        if self.controls_game:
            self.controls_game.a.controls_close()
            self.controls_game = None
        keep = self.game.id if self.game else None
        self._cancel_hold()
        self.overlay = None
        self.picker = self.osk = None
        self.support_game = self.support_snapshot = None
        self.games = games
        self.game = self.game_by_id(keep) or (games[0] if games else None)
        self.online_rows.clear()
        self.start_focus = min(self.start_focus, len(self.tile_ids()) - 1)
        if self.game is None:
            self.screen = "start"
        return True

    def _start(self, a):
        ids = self.tile_ids()
        if a == "left":
            self.start_focus = max(0, self.start_focus - 1)
        elif a == "right":
            self.start_focus = min(len(ids) - 1, self.start_focus + 1)
        elif a == "switchGame":
            if self.games:
                self._select_game(self.games[(self.start_focus + 1) % len(self.games)])
        elif a == "back":
            self._ask("exit")
        else:
            g = self.game_by_id(ids[self.start_focus])
            if g is None:
                if a == "confirm":
                    self._open_picker("manifest", "@choose_manifest", [".json"], [mf.BUILTIN_DIR, os.path.expanduser("~\\Downloads")], "file")
            elif a == "confirm":
                self._select_game(g)
                source = self._folder_source(g)
                if source:
                    self._open_picker("source:" + source["id"], "@onboarding.choose_folder", source["exts"], source["dirs"], source["kind"])
                else:
                    self.screen = "hub"
            elif a == "play":
                self._select_game(g)
                self.start_game(g)

    def _view_start(self, v):
        ids = self.tile_ids()
        widths = [SPINE_GAME if self.game_by_id(i) else SPINE_SLOT for i in ids]
        focus = min(self.start_focus, len(ids) - 1)
        others = sum(w + GAP for j, w in enumerate(widths) if j != focus)
        wide = max(WIDE, SCREEN_W - others)
        total = wide + others
        before = sum(widths[j] + GAP for j in range(focus))
        x = -max(0, min(total - SCREEN_W, before - (SCREEN_W - wide) // 2))
        tiles = []
        for j, tid in enumerate(ids):
            g = self.game_by_id(tid)
            foc = j == focus
            t = dict(id=tid, focused=foc, w=wide if foc else widths[j], free=g is None)
            if g:
                st = g.a.status()
                ready = g.a.ready()
                missing = not g.a.found()
                t.update(badge=badge(g), num=i18n.literal(g.m["numeral"]), name=i18n.literal(g.m["title"]), subtitle=i18n.literal(g.m["subtitle"]) if foc else st["status"], accent=g.accent, hero=uri(g.a.hero()),
                         rows=[dict(k="@status", v=st["status"]), dict(k="@version", v=st["version"]), dict(k="@section.online", v=st["players"]), dict(k="@last_played", v=st["last"])],
                         results=self._cells(g.a.recent_results()), empty="@no_sets", sections=["@" + SECTION_TITLES[s] for s in g.m["sections"]],
                         bar="@onboarding.choose_folder" if self._folder_source(g) else ("@open" if ready else "@go_build"))
                if missing and self._folder_source(g) and not any(game.a.found() for game in self.games):
                    t["subtitle"] = "@onboarding.title" if foc else st["status"]
                    t["empty"] = "@onboarding.source"
            else:
                t.update(badge="", num="+", name="@free_slot" if not foc else "@add_recomp", subtitle="@another_game" if foc else "", accent="#ECE9E1", hero="",
                         rows=[dict(k="@name_colour", v="@manifest"), dict(k="@sections", v="@manifest"), dict(k="@build_exe", v="@manifest")],
                         results=[], empty="@manifest_screens", sections=[], bar="@choose_manifest")
            tiles.append(t)
        v["shelf"] = dict(tiles=tiles, x=x, w=total)
        g = self.game_by_id(ids[focus])
        if g:
            ready = g.a.ready()
            missing = not g.a.found()
            v["hint"] = "@onboarding.hint" if missing and self._folder_source(g) and not any(game.a.found() for game in self.games) else g.a.status()["detail"]
            v["prompts"] = [self.prompt("confirm", "@onboarding.choose_folder" if self._folder_source(g) else ("@open" if ready else "@go_build")), self.prompt("right", "@choose_game")]
            if ready:
                v["prompts"].append(self.prompt("play", "@play"))
            v["prompts"] += [self.prompt("switchGame", "@switch_game"), self.prompt("social", "@quick_access"), self.prompt("back", "@quit")]
        else:
            v["hint"] = "@onboarding.empty" if not self.games else "@manifest_hint"
            v["prompts"] = [self.prompt("confirm", "@choose_manifest"), self.prompt("right", "@choose_game"), self.prompt("social", "@quick_access"), self.prompt("back", "@quit")]

    def click_tile(self, index):
        self._cancel_hold()
        if self.start_focus == index:
            self.act("confirm")
        else:
            self.start_focus = index
