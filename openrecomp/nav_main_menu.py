"""Per-game main menu. Entries route to existing pages without starting a search."""
from . import i18n

MAIN_LABELS = dict(ranked="@main_menu.ranked", quick="@main_menu.quick", lobby="@main_menu.lobby",
                   rooms="@main_menu.rooms", friend="@main_menu.friend", practice="@main_menu.practice",
                   offline="@main_menu.offline", replays="@main_menu.replays", leaderboard="@main_menu.leaderboard",
                   build="@main_menu.build", settings="@main_menu.settings", controls="@main_menu.controls",
                   support="@main_menu.support", games="@main_menu.games")


class MainMenu:
    def has_main_menu(self, g=None):
        return (g or self.game).m.get("adapter") in ("t4", "t5dr")

    def open_main_menu(self, g=None):
        g = g or self.game
        self.screen = "hub"
        self.main_menu_game = g.id
        self.ranked_page = ""
        self.__dict__.setdefault("main_menu_visited", set()).add(g.id)

    def _main_entries(self, g):
        state = g.a.online_state()
        caps = state.get("capabilities") or {}
        entries = []
        def add(key, section, chapter="", item=""):
            if section in self.sections(g) or section == "games":
                entries.append(dict(id=key, label=MAIN_LABELS[key],
                                    section=section, chapter=chapter, item=item))
        online = "online" in self.sections(g)
        if online:
            if caps.get("ranked", g.m.get("adapter") == "t5dr"):
                add("ranked", "online")
            add("quick", "online", item="search_casual")
            add("lobby", "online", "lobby")
            add("rooms", "online", "rooms")
            if caps.get("friends", g.m.get("adapter") == "t5dr"):
                add("friend", "online", "friends")
        if any(it.get("id") == "practice" for it in g.a.settings()):
            add("practice", "settings", item="practice")
        add("offline", "play")
        add("replays", "replays")
        if online and caps.get("leaderboard", g.m.get("adapter") == "t5dr"):
            add("leaderboard", "online", "leaderboard")
        add("build", "build")
        add("settings", "settings")
        add("controls", "controls")
        add("support", "support")
        add("games", "games")
        return entries

    def _open_main_entry(self, entry):
        g = self.game
        self.main_menu_game = ""
        self.ranked_page = ""
        if entry["section"] == "games":
            self.screen = "start"
            return
        if entry["id"] == "ranked":
            self.open_ranked(g)
            return
        self.sec[g.id] = entry["section"]
        if entry["section"] == "online":
            if entry["chapter"]:
                self.click_chapter(entry["chapter"])
            elif entry["item"]:
                items = self.items()
                self.focus[self.key()] = next((n for n, it in enumerate(items)
                                               if it.get("id") == entry["item"]), 0)
        elif entry["item"] == "practice":
            # Practice tools are an existing game setting, separate from launching offline.
            items = self.items()
            self.focus[self.key()] = next((n for n, it in enumerate(items)
                                           if it.get("id") == "practice"), 0)

    def _main_menu(self, action):
        entries = self._main_entries(self.game)
        index = min(getattr(self, "main_menu_focus", 0), len(entries) - 1)
        if action in ("up", "prev", "down", "next"):
            self.main_menu_focus = max(0, min(len(entries) - 1,
                index + (-1 if action in ("up", "prev") else 1)))
        elif action == "confirm":
            self._open_main_entry(entries[index])
        elif action == "back":
            self.main_menu_game = ""
            self.screen = "start"
        elif action == "switchGame":
            self._select_game(self.games[(self.games.index(self.game) + 1) % len(self.games)])
            self.open_main_menu()

    def click_main_entry(self, index):
        if self.overlay or getattr(self, "main_menu_game", "") != self.game.id:
            return
        entries = self._main_entries(self.game)
        if 0 <= index < len(entries):
            self.main_menu_focus = index
            self._guard(self._open_main_entry, entries[index])

    def _view_main_menu(self, v, g):
        state = g.a.online_state()
        me = state.get("me") or {}
        entries = self._main_entries(g)
        selected = min(getattr(self, "main_menu_focus", 0), len(entries) - 1)
        for index, entry in enumerate(entries):
            entry.update(index=index, focused=index == selected)
        connected = state.get("phase") not in (None, "", "offline", "error", "kicked")
        friends = sum(friend.get("status") == "online" for friend in state.get("friends") or [])
        notifications = len(state.get("friend_incoming") or []) + len(state.get("open_challenges") or [])
        v["mainMenu"] = dict(show=True, title=i18n.literal(g.m["title"]),
            kicker="@main_menu.title", entries=entries, selected=selected,
            status="@main_menu.online" if connected else "@main_menu.connection_offline",
            player=i18n.literal(me.get("name") or state.get("username") or ""),
            activity=i18n.message("main_menu.activity", players=len(state.get("players") or []),
                                  friends=friends, notifications=notifications),
            hint="@main_menu.hint")
        v["hint"] = "@main_menu.hint"
        v["prompts"] = [self.prompt("confirm", "@open"), self.prompt("back", "@games"),
                        self.prompt("social", "@quick_access"), self.prompt("switchGame", "@switch_game")]
