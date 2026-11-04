"""The Online section's lobby page: a profile card, the find-opponent card, chapters and the chat panel. No Qt.

The online rows stay one list (every action keeps its id and its run); this module only puts them in page order and
says where each one is drawn:

    find      profile card + find-opponent card (always on top)
    chapters  Lobby, Rooms, Friends, Leaderboard, Statistics, Profile, Tournaments, Spectating, Account
    chat      the chat panel at the right, on every chapter (lobby chat and private conversations as tabs)

Up/down walks the list (crossing into the next chapter shows it), rows of one group (a player's buttons, a button bar)
are one line: left/right moves inside it. LT/RT jump between chapters, X goes to the chat panel and back.
"""
import collections

from . import i18n
from .nav_netext import where
from .nav_common import uri

CHAPTERS = ("lobby", "rooms", "friends", "leaderboard", "stats", "profile", "tournaments", "spectating", "account")
CHAPTER_LABELS = {"lobby": "@online_ui.chapter.lobby", "rooms": "@online_ui.chapter.rooms",
                  "friends": "@online_ui.chapter.friends", "leaderboard": "@online_ui.chapter.leaderboard",
                  "stats": "@online_ui.chapter.stats", "profile": "@online_ui.chapter.profile",
                  "tournaments": "@online_ui.chapter.tournaments", "spectating": "@online_ui.chapter.spectating",
                  "account": "@online_ui.chapter.account"}
REGIONS = ("find",) + CHAPTERS + ("chat",)
FIND_IDS = {"online_status", "online_fighter", "search_casual", "search_ranked", "ranked_strict", "logout",
            "profile_self", "accept_challenge", "decline_challenge", "native", "leave_set", "game_setup",
            "game_update", "rules_life", "screen_side", "always_left", "other_here", "other_keep", "netext_options"}
# (id or id prefix, region): the first match wins
PREFIXES = (
    (("chat:", "no_chat", "online_chat", "send_chat", "chat_toggle", "chat_lobby", "private_send", "private_close",
      "online_private_chat", "private_message:", "private_select:", "private_empty", "online_private_report_reason",
      "private_report"), "chat"),
    (("challenge_",), "find"),
    (("refresh_players", "challenge:", "no_players", "profile_player:", "mention:", "cancel_challenge:",
      "private_open:"), "lobby"),
    (("leaderboard_", "profile_board:"), "leaderboard"),
    (("stats_", "community_totals", "community_fighter:", "no_statistics"), "stats"),
    (("refresh_rooms", "create_room", "create_password_room", "create_code_room", "join_room_code", "online_room_",
      "room_invite_code", "leave_room", "join_room:", "no_rooms", "community_"), "rooms"),
    (("refresh_friends", "online_friend_name", "add_friend", "remove_friend:", "invite_friend:", "invite_room:",
      "accept_friend:", "decline_friend:", "cancel_friend:", "accept_invite:", "decline_invite:", "cancel_invite",
      "no_friends"), "friends"),
    (("tour_", "online_tour_", "spec_watch_tour"), "tournaments"),
    (("spec_",), "spectating"),
    (("profile_", "online_profile", "no_ranked_chars"), "profile"),
)
# ids of one line, by family: consecutive rows of a family are one group (left/right inside it)
BARS = {"other_here": "other", "other_keep": "other", "profile_self": "card", "logout": "card", "search_ranked": "search", "search_casual": "search",
        "accept_challenge": "incoming", "decline_challenge": "incoming", "refresh_rooms": "room_bar",
        "create_room": "room_bar", "create_password_room": "room_bar", "create_code_room": "room_bar",
        "join_room_code": "room_bar", "leave_room": "room_bar", "refresh_friends": "friend_bar", "add_friend": "friend_bar",
        "leaderboard_previous": "lb_page", "leaderboard_next": "lb_page", "profile_history_previous": "hist_page",
        "profile_history_next": "hist_page", "online_chat": "compose", "send_chat": "compose",
        "online_private_chat": "pcompose", "private_send": "pcompose", "chat_toggle": "tabs", "chat_lobby": "tabs",
        "online_private_report_reason": "preport", "private_report": "preport"}
BAR_PREFIXES = {"leaderboard_sort:": "lb_sort", "stats_mode:": "stats_mode", "stats_sort:": "stats_sort"}
# table families: id prefix -> the group of a row's extra buttons
TABLES = ("challenge:", "join_room:", "profile_board:", "community_fighter:", "profile_history:", "profile_stats:",
          "profile_char:", "profile_ranked_char:", "tour_entrant:", "tour_standing:", "community_member:")
# rows that open a chapter's page: the chapter is shown after them
AFTER = {"profile_self": "profile", "profile_load": "profile", "profile_player:": "profile", "profile_board:": "profile",
         "leaderboard_refresh": "leaderboard", "stats_refresh": "stats"}
LOADERS = {"profile": "profile_self", "leaderboard": "leaderboard_refresh", "stats": "stats_refresh"}
CHAT_LINES = 13
LOBBY_HEADINGS = ("@online.players", "@online.open_challenges")
CARD_LINES = 13
BODY_LINES = 13
BAR_WIDTH = 5
SIGNAL = ((60, 4), (100, 3), (160, 2))


def region_of(iid, threads=()):
    if iid in FIND_IDS:
        return "find"
    if iid.startswith("private_open:"):
        return "chat" if iid.partition(":")[2] in threads else "lobby"
    for prefixes, region in PREFIXES:
        if iid.startswith(prefixes):
            return region
    return "account"


def bars(ping):
    if not isinstance(ping, (int, float)):
        return 0
    return next((n for limit, n in SIGNAL if ping < limit), 1)


def connection(info):
    ping = info.get("ping")
    text = "@online_ui.ping_unknown"
    if ping is not None and info.get("ping_measured"):
        text = i18n.message("online_ui.ping_ms", ping=ping)
    elif ping is not None:
        text = i18n.message("online_ui.ping_est", ping=ping)
    path = {"direct": "@online_ui.path_direct", "relay": "@online_ui.path_relay", "lan": "@online_ui.path_lan"}
    return dict(text=text, bars=bars(ping), path=path.get(info.get("ping_path"), ""))


def _family(iid):
    return next((p for p in TABLES if iid.startswith(p)), "")


class OnlineLayout:
    """Mixin of Nav: the lobby page's order, groups, chapter memory and its view."""

    def _online_layout_on(self, state):
        caps = state.get("capabilities") or {}
        return (state.get("phase") == "logged_in" and caps.get("lobby", False)
                and not state.get("recovery_codes"))

    def _online_layout_items(self, g, state, out):
        """Page order + region/group tags for the lobby page; other phases keep their plain list."""
        if not self._online_layout_on(state):
            return out
        threads = {str(t.get("id")) for t in ((state.get("private_chat") or {}).get("threads") or [])}
        selected = str((state.get("private_chat") or {}).get("selected") or "")
        open_chat = self.__dict__.setdefault("chat_open", {}).get(g.id, True)
        extra = []
        for sid in ("screen_side", "always_left"):
            setting = next((s for s in self._settings_safe(g) if s["id"] == sid), None)
            if setting:
                item = self._cycler_item(g, setting)
                item["label"] = "@online_ui.side"
                extra.append(item)
        if (state.get("capabilities") or {}).get("strict"):
            extra.append(dict(kind="action", id="ranked_strict", label="@online_ui.strict",
                              value="@on" if state.get("strict") else "@off", verb="@change",
                              hint="@online_ui.strict_hint",
                              detail=dict(kicker="@section.online", title="@online_ui.strict",
                                          lead="@online_ui.strict_hint", rows=[]),
                              run=lambda: self._online_action(g, "ranked_strict")))
        if not state.get("account"):
            # Ranked needs an account: a guest sees the button greyed with the reason, never a refusal after it
            for item in out:
                if item.get("id") == "search_ranked":
                    item.update(disabled=True, run=None, verb="", hint="@online_ui.ranked_account",
                                value="@online_ui.ranked_account")
        toggle = dict(kind="action", id="chat_toggle", label="@online_ui.chat_hide" if open_chat else "@online_ui.chat_show",
                      verb="@change", hint="@online_ui.chat_toggle_hint",
                      detail=dict(kicker="@online.chat", title="@online.chat", lead="@online_ui.chat_toggle_hint", rows=[]),
                      run=lambda: self._chat_set_open(g, not open_chat))
        tabs = [toggle]
        if threads:
            tab = dict(kind="action", id="chat_lobby", label="@online_ui.lobby_chat", verb="@open",
                       hint="@online.chat_hint", detail=dict(kicker="@online.chat", title="@online_ui.lobby_chat",
                                                            lead="@online.chat_hint", rows=[]),
                       run=(lambda: self._online_action(g, "private_close")) if selected else None)
            tabs.append(tab)
        by_region = collections.OrderedDict((r, []) for r in REGIONS)
        pending = []
        for item in out + extra:
            if item.get("kind") == "heading":
                pending.append(item)
                continue
            if item.get("id") == "close_profile":
                continue                          # the chapters are the pages: no Back row
            chapter = AFTER.get(item.get("id")) or next((c for p, c in AFTER.items() if p.endswith(":")
                                                         and (item.get("id") or "").startswith(p)), None)
            if chapter and item.get("run"):
                item["run"] = self._then_chapter(item["run"], chapter)
            region = region_of(item.get("id") or "", threads)
            if region == "chat" and not open_chat and item.get("id") != "chat_toggle":
                continue                          # a closed panel: its rows are hidden, X opens it
            if region == "chat" and selected and (item.get("id") or "").startswith(("chat:", "no_chat", "online_chat", "send_chat")):
                continue                          # a private conversation is open in the panel
            for heading in pending:
                # a heading names its own rows: one whose rows live elsewhere (spectating, private chat) is dropped
                if region == "lobby" and heading.get("label") not in LOBBY_HEADINGS:
                    continue
                if region != "chat" or selected:
                    by_region[region].append(heading)
            pending = []
            by_region[region].append(item)
        by_region["chat"] = tabs + [it for it in by_region["chat"] if it.get("id") != "chat_toggle"]
        by_region["lobby"] = self._lobby_order(state, by_region["lobby"])
        by_region["find"] = self._find_order(by_region["find"])
        page = []
        for region, items in by_region.items():
            for item in items:
                item["region"] = region
                page.append(item)
        self._group(page)
        return page

    def _then_chapter(self, run, chapter):
        def go():
            result = run()
            self._show_chapter(self.items(), chapter)
            return result
        return go

    def _settings_safe(self, g):
        try:
            return g.a.settings()
        except Exception:  # noqa: BLE001 -- a game without settings: no side choice in the card
            return []

    @staticmethod
    def _find_order(items):
        order = {iid: n for n, iid in enumerate((
            "online_status", "other_here", "other_keep", "profile_self", "logout", "search_ranked", "search_casual", "accept_challenge",
            "decline_challenge", "online_fighter", "rules_life", "ranked_strict", "screen_side", "always_left", "netext_options"))}
        return sorted(items, key=lambda it: (order.get(it.get("id"), 50), 0))

    @staticmethod
    def _lobby_order(state, items):
        """A player's buttons (challenge, profile, message, mention) next to each other: one table row."""
        players = [str(p.get("id")) for p in state.get("players") or []]
        rank = {pid: n for n, pid in enumerate(players)}
        head, rows, tail = [], collections.defaultdict(list), []
        for item in items:
            iid = item.get("id") or ""
            prefix, _, pid = iid.partition(":")
            if prefix in ("challenge", "profile_player", "private_open", "mention") and pid in rank:
                rows[pid].append(item)
            elif rows or iid == "no_players":
                tail.append(item)
            else:
                head.append(item)
        kinds = ("challenge", "profile_player", "private_open", "mention")
        out = list(head)
        for pid in sorted(rows, key=rank.get):
            out += sorted(rows[pid], key=lambda it: kinds.index((it.get("id") or "").partition(":")[0]))
        return out + tail

    @staticmethod
    def _group(page):
        for n, item in enumerate(page):
            iid = item.get("id") or ""
            if item.get("kind") == "heading":
                continue
            group = BARS.get(iid) or next((g for p, g in BAR_PREFIXES.items() if iid.startswith(p)), "")
            prefix, _, rest = iid.partition(":")
            if prefix in ("challenge", "profile_player", "private_open", "mention") and item.get("region") == "lobby":
                group = "p:" + rest
            elif prefix in ("invite_friend", "invite_room", "remove_friend", "accept_friend", "decline_friend",
                            "cancel_friend"):
                group = "f:" + rest
            elif prefix in ("accept_invite", "decline_invite"):
                group = "i:" + rest
            elif prefix in ("profile_history", "profile_history_replay"):
                group = "h:" + rest
            elif prefix == "private_open" and item.get("region") == "chat":
                group = "tabs"
            item["group"] = group
        # one line = one unbroken run of a group (two button bars of one kind are two lines)
        run, previous = 0, None
        for item in page:
            base = item.get("group") or ""
            if item.get("kind") == "heading" or not base:
                previous = None
                continue
            if base != previous:
                run += 1
            previous = base
            item["group"] = base + "#" + str(run)

    # ---------------------------------------------------------------- moving
    def _online_page(self):
        g = self.game
        return self.section() == "online" and self._online_layout_on(g.a.online_state())

    def _line_start(self, items, i):
        group = items[i].get("group")
        while group and i > 0 and items[i - 1].get("group") == group:
            i -= 1
        return i

    def _online_move(self, items, i, step):
        """Up/down on the lobby page: to the next line (a group is one line), the same column where it can."""
        if not items:
            return i
        start = self._line_start(items, i)
        column = i - start
        j = i
        group = items[i].get("group")
        while 0 <= j < len(items) and ((group and items[j].get("group") == group) or j == i):
            j += step
        while 0 <= j < len(items) and items[j].get("kind") == "heading":
            j += step
        if not 0 <= j < len(items):
            return i
        start = self._line_start(items, j)
        group = items[j].get("group")
        end = start
        while group and end + 1 < len(items) and items[end + 1].get("group") == group:
            end += 1
        return min(start + column, end)

    def _online_side(self, items, i, step):
        """Left/right inside a line; a lone cycler row changes its value instead (the caller does that)."""
        group = items[i].get("group")
        j = i + step
        if group and 0 <= j < len(items) and items[j].get("group") == group:
            return j
        return None

    def _chapter_of_focus(self, items, i):
        g = self.game
        memory = self.__dict__.setdefault("online_chapter", {})
        region = items[i].get("region") if items else None
        if region in CHAPTERS:
            memory[g.id] = region
        chapter = memory.get(g.id, "lobby")
        present = {it.get("region") for it in items}
        if chapter not in present:
            chapter = next((c for c in CHAPTERS if c in present), "lobby")
        return chapter

    def _online_chapter(self, items, i, step):
        present = [c for c in CHAPTERS if any(it.get("region") == c for it in items)]
        if not present:
            return
        self._remember_chapter_focus(items, i)
        chapter = self._chapter_of_focus(items, i)
        pos = present.index(chapter) if chapter in present else 0
        self._go_chapter(items, present[(pos + step) % len(present)])

    def _go_chapter(self, items, target):
        g = self.game
        self._show_chapter(items, target)
        pages = getattr(self, "_t5_profile_pages", None) or {}
        loader = LOADERS.get(target)
        if loader and pages.get(g.id) != target and not self.dry:
            # Opening the Leaderboard, Statistics or Profile chapter asks the server for it (one request).
            item = next((it for it in items if it.get("id") == loader), None)
            if item and item.get("run"):
                self._guard(item["run"])

    def _show_chapter(self, items, chapter):
        g = self.game
        self.__dict__.setdefault("online_chapter", {})[g.id] = chapter
        remembered = self.__dict__.setdefault("chapter_focus", {}).get((g.id, chapter))
        first = next((n for n, it in enumerate(items) if it.get("region") == chapter and it.get("kind") != "heading"), None)
        target = next((n for n, it in enumerate(items) if it.get("id") == remembered and it.get("region") == chapter), first)
        if target is not None:
            self.focus[self.key()] = target

    def click_chapter(self, chapter):
        """A mouse click on a chapter tab: the same as LT/RT reaching it."""
        if self.overlay or not self._online_page():
            return
        items = self.items()
        if any(it.get("region") == chapter for it in items):
            self._go_chapter(items, chapter)

    def _remember_chapter_focus(self, items, i):
        if items and items[i].get("region") in CHAPTERS:
            self.__dict__.setdefault("chapter_focus", {})[(self.game.id, items[i]["region"])] = items[i].get("id")

    def _chat_jump(self, items, i):
        """X: into the chat panel (its text field), and back to where the focus was."""
        g = self.game
        back = self.__dict__.setdefault("chat_back", {})
        if items[i].get("region") == "chat" and back.get(g.id):
            target = next((n for n, it in enumerate(items) if it.get("id") == back[g.id]), None)
            back.pop(g.id, None)
            if target is not None:
                self.focus[self.key()] = target
            return
        back[g.id] = items[i].get("id")
        if not self.__dict__.setdefault("chat_open", {}).get(g.id, True):
            self._chat_set_open(g, True)
            items = self.items()
        field = next((n for n, it in enumerate(items) if it.get("id") in ("online_private_chat", "online_chat")), None)
        if field is None:
            field = next((n for n, it in enumerate(items) if it.get("region") == "chat"), None)
        if field is not None:
            self.focus[self.key()] = field

    def _chat_set_open(self, g, on):
        state = g.a.online_state()
        self.__dict__.setdefault("chat_open", {})[g.id] = bool(on)
        seen = self.__dict__.setdefault("chat_seen", {})
        seen[g.id] = None if on else collections.Counter(self._chat_keys(state))
        items = self.items()
        target = next((n for n, it in enumerate(items) if it.get("id") == "chat_toggle"), None)
        if target is not None:
            self.focus[self.key()] = target

    @staticmethod
    def _chat_keys(state):
        return [(str(m.get("name") or ""), str(m.get("text") or "")) for m in state.get("chat") or []]

    def _chat_unread(self, g, state):
        seen = self.__dict__.setdefault("chat_seen", {}).get(g.id)
        threads = (state.get("private_chat") or {}).get("threads") or []
        private = sum(int(t.get("unread") or 0) for t in threads if isinstance(t.get("unread"), int))
        if seen is None:
            return private
        now = collections.Counter(self._chat_keys(state))
        return private + sum((now - seen).values())

    # ---------------------------------------------------------------- view
    def _btn(self, items, n, fi, short=False):
        it = items[n]
        value = it.get("value") or ""
        return dict(index=n, label=it.get("label", ""), value=value, focused=n == fi, disabled=bool(it.get("disabled")),
                    cycler=it.get("kind") == "cycler", verb=it.get("verb", "") if n == fi else "")

    def _view_online_card(self, v, g, items, fi):
        """Login, search, match and result: one card (title, the status message, the rows) + the focused row's details."""
        lines, focus_line = [], 0
        for n, it in enumerate(items):
            if it.get("kind") == "heading":
                lines.append(dict(kind="heading", label=it.get("label", "")))
                continue
            if it.get("id") == "online_status":
                continue                          # the status is the card's title and message
            if n == fi:
                focus_line = len(lines)
            row = self._btn(items, n, fi)
            iid = it.get("id") or ""
            row["kind"] = "field" if iid.startswith("online_") and it.get("verb") == "@change" else "row"
            row["verb"] = it.get("verb", "") if n == fi else ""
            lines.append(row)
        start = 0
        if len(lines) > CARD_LINES:
            start = max(0, min(len(lines) - CARD_LINES, focus_line - CARD_LINES // 2))
        si = next((n for n, it in enumerate(items) if it.get("id") == "online_status"), -1)
        status = items[si] if si >= 0 else {}
        sd = status.get("detail") or {}
        it = items[fi] if items else {}
        d = it.get("detail") or {}
        rows = [dict(k=r["k"], v=r["v"], accent=bool(r.get("accent")),
                     **({"plate": r["plate"]} if r.get("plate") else {})) for r in (sd.get("rows") or []) + (
            (d.get("rows") or []) if it is not status else [])][:12]
        try:
            state = g.a.online_state()
            phase = state.get("phase", "")
        except Exception:  # noqa: BLE001 -- the card without its error colour
            state, phase = {}, ""
        v["online"] = dict(layout="card", title=sd.get("title") or status.get("label", ""), message=sd.get("lead", ""),
                           connection=connection(state.get("match") or {}) if phase in ("matched", "starting", "playing", "result", "result_sent") else None,
                           error=phase in ("error", "kicked"),
                           statusFocused=fi == si and si >= 0, statusIndex=si,
                           lines=lines[start:start + CARD_LINES], up=start > 0, down=start + CARD_LINES < len(lines),
                           detail=dict(title=d.get("title") or it.get("label", ""), lead=d.get("lead") or it.get("hint", ""),
                                       rows=rows))

    def _view_online_page(self, v, g, state, items, fi):
        chapter = self._chapter_of_focus(items, fi)
        self._remember_chapter_focus(items, fi)
        open_chat = self.__dict__.setdefault("chat_open", {}).get(g.id, True)
        by_id = {it.get("id"): n for n, it in enumerate(items)}
        page = dict(layout="lobby", chapter=chapter, chatOpen=open_chat, findTitle="@online_ui.find_title",
                    prevG=self.glyph("chapterPrev"), nextG=self.glyph("chapterNext"), chatG=self.glyph("x"))
        page["profile"] = self._view_profile(g, state, items, fi, by_id)
        page["find"] = self._view_find(g, state, items, fi, by_id)
        page["chapters"] = self._view_chapters(state, items, chapter)
        page["body"] = self._view_body(g, state, items, fi, chapter)
        page["chat"] = self._view_chat(g, state, items, fi)
        page["focusRegion"] = items[fi].get("region") if items else ""
        v["online"] = page

    def _view_profile(self, g, state, items, fi, by_id):
        me = state.get("me") or {}
        rank = self._rank_label(me) if me else ("@online.guest_kind" if not state.get("account") else "")
        record = me.get("record")
        main = me.get("main") or ""
        face = uri(g.a.fighter_image(main)) if main else ""
        rows = []
        if me.get("rating") is not None and not me.get("guest"):
            rows.append(i18n.message("online_ui.rating_line", rating=me["rating"]))
        if record:
            rows.append(self._record(record))
        ping = state.get("server_ping")
        conn = [i18n.message("online_ui.server_ping", ping=ping) if ping is not None else "@online_ui.server_ping_unknown",
                "@online_ui.secure" if state.get("secure") else "@online_ui.not_secure"]
        n = by_id.get("online_status", 0)
        progress, progress_text = -1, ""
        rating = me.get("rating")
        if state.get("account") and not me.get("guest") and not me.get("placement"):
            bar = g.a.rank_progress(rating)
            if bar:
                low, high, following = bar
                progress = max(0.0, min(1.0, (rating - low) / max(1.0, high - low)))
                progress_text = i18n.message("online_ui.to_next", points=int(round(max(0, high - rating))),
                                             rank=i18n.literal(following))
        elif me.get("placement"):
            done, total = me["placement"]
            progress = max(0.0, min(1.0, done / max(1, total)))
            progress_text = i18n.message("online_ui.placement_left", left=max(0, total - done))
        try:
            recent = self._cells(g.a.recent_results() or [])[:8]
        except Exception:  # noqa: BLE001 -- the card shows no results then
            recent = []
        build = []
        if state.get("build_id"):
            build.append(i18n.message("online_ui.build_line", build=i18n.literal(state["build_id"])))
        if state.get("game_folder"):
            build.append(i18n.literal(state["game_folder"]))
        return dict(name=i18n.literal(state.get("name") or ""), rank=rank, build=build, plate=uri(g.a.rank_plate(me.get("tier"))) if me else "",
                    face=face, main=i18n.literal(g.a.fighter_label(main)) if main else "", rows=rows, conn=conn,
                    index=n, focused=n == fi, guest=not state.get("account"),
                    progress=progress, progressText=progress_text, recent=recent, recentLabel="@recent_sets",
                    buttons=[self._btn(items, by_id[i], fi) for i in ("profile_self", "logout") if i in by_id])

    def _view_find(self, g, state, items, fi, by_id):
        from .nav_challenges import _details

        def button(iid):
            if iid not in by_id:
                return dict(index=-1, label="", focused=False, disabled=True, present=False)
            out = self._btn(items, by_id[iid], fi)
            out["present"] = True
            return out
        options = [self._btn(items, n, fi) for n, it in enumerate(items)
                   if it.get("region") == "find" and (it.get("kind") == "cycler" or it.get("id") in ("online_fighter", "ranked_strict", "netext_options"))]
        extra = [self._btn(items, n, fi) for n, it in enumerate(items)
                 if it.get("region") == "find" and it.get("id") in ("native", "leave_set", "game_setup", "game_update")]
        challenge = state.get("challenge") or {}
        terms = (state.get("challenge_preferences") or {}).get("incoming") or {}
        incoming = dict(text=i18n.message("online_ui.incoming", name=i18n.literal(challenge.get("name") or "")),
                        connection=connection(challenge),
                        details=_details(terms) if terms.get("id") == challenge.get("id") else [],
                        buttons=[self._btn(items, by_id[i], fi) for i in ("accept_challenge", "decline_challenge") if i in by_id]) \
            if challenge and "accept_challenge" in by_id else None
        outgoing = None
        for offer in state.get("open_challenges") or []:
            iid = "cancel_challenge:" + offer["id"]
            if iid in by_id:
                outgoing = dict(text=i18n.message("online_ui.waiting_for", name=i18n.literal(offer.get("name") or "")),
                                connection=connection(offer), details=_details(offer),
                                buttons=[dict(self._btn(items, by_id[iid], fi), label="@online.cancel_challenge")])
                break
        if not outgoing and state.get("outgoing_challenge"):
            offer = state["outgoing_challenge"]
            outgoing = dict(text=i18n.message("online_ui.waiting_for", name=i18n.literal(offer.get("name") or "")),
                            connection=connection(offer), details=[], buttons=[])
        # another launcher of this game is open: the note sits over the options until the player chose
        note = self._other_launcher_text(state)
        notice = dict(text=note, buttons=[self._btn(items, by_id[i], fi) for i in ("other_here", "other_keep")
                                          if i in by_id]) if note and "other_here" in by_id else None
        return dict(ranked=button("search_ranked"), quick=button("search_casual"), notice=notice,
                    rankedNote="@online_ui.ranked_note", quickNote="@online_ui.quick_note",
                    options=options, extra=extra, incoming=incoming, outgoing=outgoing, message=state.get("message") or "")

    def _view_chapters(self, state, items, chapter):
        present = [c for c in CHAPTERS if any(it.get("region") == c for it in items)]
        out = []
        for c in present:
            badge = ""
            if c == "lobby":
                badge = str(len(state.get("players") or []))
            elif c == "friends":
                count = len(state.get("friend_incoming") or []) + len(state.get("invites") or [])
                badge = str(count) if count else ""
            elif c == "rooms":
                badge = str(len(state.get("rooms") or [])) if state.get("rooms") else ""
            out.append(dict(id=c, label=CHAPTER_LABELS[c], active=c == chapter, badge=badge))
        return out

    @staticmethod
    def _record(record):
        if len(record) > 2 and record[2]:
            return i18n.message("online_ui.record_draws", wins=record[0], losses=record[1], draws=record[2])
        return i18n.message("online_ui.record", wins=record[0], losses=record[1])

    @staticmethod
    def _rank_label(p):
        rank = i18n.literal(p.get("rank") or "") if p.get("rank") else ""
        if p.get("guest"):
            return "@online_ui.guest"
        if p.get("placement"):
            done, total = p["placement"]
            return i18n.message("online_ui.placement", done=done, total=total)
        if p.get("provisional"):
            return "@online_ui.provisional"
        return rank

    def _view_body(self, g, state, items, fi, chapter):
        lines = []
        players = {str(p.get("id")): p for p in state.get("players") or []}
        rooms = {str(r.get("id")): r for r in state.get("rooms") or []}
        idx = [n for n, it in enumerate(items) if it.get("region") == chapter]
        n = 0
        focus_line = 0
        while n < len(idx):
            i = idx[n]
            it = items[i]
            iid = it.get("id") or ""
            if it.get("kind") == "heading":
                lines.append(dict(kind="heading", label=it.get("label", "")))
                n += 1
                continue
            group = it.get("group") or ""
            family = _family(iid)
            if family:
                # one table: consecutive rows of this family (with their groups' buttons)
                block = []
                while n < len(idx) and (_family(items[idx[n]].get("id") or "") == family
                                        or (items[idx[n]].get("group") and block and items[idx[n]].get("group") == items[block[-1][0]].get("group"))):
                    j = idx[n]
                    if block and items[j].get("group") and items[j].get("group") == items[block[-1][0]].get("group"):
                        block[-1][1].append(j)
                    else:
                        block.append((j, []))
                    n += 1
                table = self._table(g, family, block, items, fi, players, rooms)
                for line in table:
                    if line.get("focused") or any(b["focused"] for b in line.get("buttons") or []):
                        focus_line = len(lines)
                    lines.append(line)
                continue
            if group:
                members = []
                while n < len(idx) and items[idx[n]].get("group") == group:
                    members.append(idx[n])
                    n += 1
                for start_at in range(0, len(members), BAR_WIDTH):     # a long bar (sort keys) wraps into lines
                    part = members[start_at:start_at + BAR_WIDTH]
                    if fi in part:
                        focus_line = len(lines)
                    lines.append(dict(kind="bar", buttons=[self._btn(items, j, fi) for j in part]))
                continue
            if i == fi:
                focus_line = len(lines)
            row = self._btn(items, i, fi)
            row["kind"] = "row"
            row["verb"] = it.get("verb", "") if i == fi else ""
            lines.append(row)
            n += 1
        start = 0
        if len(lines) > BODY_LINES:
            start = max(0, min(len(lines) - BODY_LINES, focus_line - BODY_LINES // 2))
        shown = lines[start:start + BODY_LINES]
        if start > 0 and shown and shown[0]["kind"] == "trow":           # keep the table's heading on screen
            head = next((line for line in reversed(lines[:start]) if line["kind"] == "thead"), None)
            if head:
                shown = [head] + shown[:-1]
        it = items[fi] if items else {}
        detail = None
        if chapter not in ("lobby", "rooms") and it.get("region") == chapter:
            d = it.get("detail") or {}
            rows = [dict(k=r["k"], v=r["v"]) for r in d.get("rows") or []]
            if rows or d.get("lead"):
                detail = dict(title=d.get("title") or it.get("label", ""), lead=d.get("lead", ""), rows=rows[:12])
        empty = not lines
        return dict(lines=shown, up=start > 0, down=start + BODY_LINES < len(lines), detail=detail,
                    empty="@online_ui.empty" if empty else "", title=CHAPTER_LABELS.get(chapter, ""))

    def _table(self, g, family, block, items, fi, players, rooms):
        lines = []
        if family == "challenge:":
            cols = [("", 0.10), ("@online_ui.col.player", 0.20), ("@online.rank", 0.15), ("@rating", 0.08),
                    ("@online_ui.col.record", 0.11), ("@online_ui.col.main", 0.13), ("@online_ui.col.status", 0.12),
                    ("@online.ping", 0.11)]
            lines.append(dict(kind="thead", cols=[dict(label=c, w=w) for c, w in cols]))
            available, busy = [], []
            for main, extra in block:
                pid = (items[main].get("id") or "").partition(":")[2]
                p = players.get(pid, {})
                (busy if p.get("status") in ("match", "playing") else available).append((main, extra, p))
            for group, dim in ((available, False), (busy, True)):
                if dim and group:
                    lines.append(dict(kind="note", label="@online_ui.not_available"))
                for main, extra, p in group:
                    record = p.get("record")
                    status = {"idle": "@online_ui.status.idle", "room": "@online_ui.status.room",
                              "queue": "@online_ui.status.queue", "match": "@online_ui.status.match",
                              "playing": "@online_ui.status.playing"}.get(p.get("status"), "")
                    ping = p.get("ping")
                    measured = bool(p.get("ping_measured"))
                    shown = ""
                    if ping is not None and measured:
                        shown = i18n.message("online_ui.ping_ms", ping=ping)
                    elif ping is not None:
                        shown = i18n.message("online_ui.ping_est", ping=ping)
                    cells = [dict(text="", plate=uri(g.a.rank_plate(p.get("tier"))) if "tier" in p else "", bars=bars(ping)),
                             dict(text=i18n.literal(p.get("name") or ""), bold=True, tags=i18n.literal(where(p))),
                             dict(text=self._rank_label(p)),
                             dict(text=str(p["rating"]) if p.get("rating") is not None and not p.get("guest") else ""),
                             dict(text=self._record(record) if record else ""),
                             dict(text=i18n.literal(g.a.fighter_label(p["main"])) if p.get("main") else "",
                                  face=uri(g.a.fighter_image(p["main"])) if p.get("main") else ""),
                             dict(text=status),
                             dict(text=shown)]
                    lines.append(self._trow(items, fi, main, extra, cells, dim))
            return lines
        if family == "join_room:":
            cols = [("@online_ui.col.room", 0.34), ("@online_ui.col.host", 0.26), ("@online_ui.col.state", 0.2),
                    ("@online_ui.col.lock", 0.2)]
            lines.append(dict(kind="thead", cols=[dict(label=c, w=w) for c, w in cols]))
            for main, extra in block:
                r = rooms.get((items[main].get("id") or "").partition(":")[2], {})
                lock = {"password": "@online_ui.lock.password", "code": "@online_ui.lock.code"}.get(r.get("lock"), "")
                cells = [dict(text=items[main].get("label", ""), bold=True, tags=i18n.literal(where(r))), dict(text=i18n.literal(r.get("host") or "")),
                         dict(text=i18n.literal(r.get("status") or "")), dict(text=lock)]
                lines.append(self._trow(items, fi, main, extra, cells, False))
            return lines
        # generic: the label, then the rows' detail values as columns
        keys = []
        for main, _extra in block:
            for r in (items[main].get("detail") or {}).get("rows") or []:
                if r["k"] not in keys and len(keys) < 6:
                    keys.append(r["k"])
        first = 0.3 if keys else 1.0
        width = (1.0 - first) / max(1, len(keys))
        lines.append(dict(kind="thead", cols=[dict(label="", w=first)] + [dict(label=k, w=width) for k in keys]))
        for main, extra in block:
            values = {r["k"]: r["v"] for r in (items[main].get("detail") or {}).get("rows") or []}
            label = items[main].get("label", "")
            cells = [dict(text=label, bold=True)] + [dict(text=values.get(k, "")) for k in keys]
            lines.append(self._trow(items, fi, main, extra, cells, False))
        return lines

    def _trow(self, items, fi, main, extra, cells, dim):
        it = items[main]
        focused_row = fi == main or fi in extra
        buttons = []
        if focused_row:
            first = self._btn(items, main, fi)
            first["label"] = it.get("verb") or "@open"
            buttons = [first] + [self._btn(items, j, fi) for j in extra]
            for b, j in zip(buttons[1:], extra):
                if items[j].get("verb") and (items[j].get("id") or "").startswith(("profile_player:", "private_open:", "profile_history_replay:")):
                    b["label"] = items[j]["verb"]
        return dict(kind="trow", index=main, focused=focused_row, dim=dim, cells=cells, buttons=buttons)

    def _view_chat(self, g, state, items, fi):
        open_chat = self.__dict__.setdefault("chat_open", {}).get(g.id, True)
        data = state.get("private_chat") or {}
        selected = str(data.get("selected") or "")
        tabs = []
        lines = []
        compose, send, other = None, None, []
        me = str(state.get("name") or "")
        for n, it in enumerate(items):
            if it.get("region") != "chat":
                continue
            iid = it.get("id") or ""
            if iid == "chat_toggle":
                continue
            if iid == "chat_lobby" or iid.startswith("private_open:"):
                b = self._btn(items, n, fi)
                b["active"] = (iid == "chat_lobby" and not selected) or iid.partition(":")[2] == selected
                tabs.append(b)
            elif iid.startswith(("chat:", "private_message:", "private_select:")) or iid in ("no_chat", "private_empty"):
                name = it.get("label") if iid not in ("no_chat", "private_empty") else ""
                text = it.get("value") or (it.get("label") if iid in ("no_chat", "private_empty") else "")
                raw = name.get("_literal") if isinstance(name, dict) else ""
                lines.append(dict(index=n, name=name, text=text, focused=n == fi, own=bool(me) and raw == me,
                                  system=iid in ("no_chat", "private_empty")))
            elif iid in ("online_chat", "online_private_chat"):
                compose = self._btn(items, n, fi)
            elif iid in ("send_chat", "private_send"):
                send = self._btn(items, n, fi)
            elif it.get("kind") != "heading":
                other.append(self._btn(items, n, fi))
        focus = next((k for k, line in enumerate(lines) if line["focused"]), None)
        start = max(0, len(lines) - CHAT_LINES) if focus is None else max(0, min(len(lines) - CHAT_LINES, focus - CHAT_LINES // 2))
        toggle = next(({**self._btn(items, n, fi)} for n, it in enumerate(items) if it.get("id") == "chat_toggle"), None)
        return dict(open=open_chat, unread=self._chat_unread(g, state), tabs=tabs, lines=lines[start:start + CHAT_LINES],
                    up=start > 0, compose=compose, send=send, other=other, toggle=toggle,
                    title="@online.chat" if not selected else "@online_chat.private_title")
