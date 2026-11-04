"""The Online login page: one centred card. No Qt. T5DR and T4 share it.

    Name (one field for both ways in)
    Account: password (show/hide), Remember me, [Log in], Register · Forgot password?
    Play as guest: [Play as guest]
    footer: Server ... · change, certificate, direct play, the game's own launcher

The rows stay the adapter's own (same ids, same runs); this module orders them, adds Show password, Remember me and
Forgot password? / Back, and builds the view. "Forgot password?" opens the account recovery rows as their own page.
Up/down walks the card; left/right jumps between Log in and Play as guest. Remember me off: the adapter keeps no login, and the remembered
one does not log in by itself when Online is shown (the adapter's online_shown is not asked).
"""
from . import i18n
from .nav_common import uri

LOGIN_PHASES = ("offline", "error", "kicked")
ACCOUNT_IDS = ("online_password", "login_show_password", "login_remember", "login_account", "login_register",
               "login_forgot")
RECOVER_IDS = ("online_recovery_code", "online_new_password", "online_repeat_password", "recover_account")
FOOTER_IDS = ("online_server", "online_fingerprint", "mode_direct", "native")
# which field a message is about: the red line goes under it
FIELD_ERRORS = {
    "online_name": ("@online.bad_name", "@online.name_taken"),
    "online_password": ("@online.password_required", "@online.auth_failed", "@online.account_required"),
    "online_server": ("@online.unavailable", "@online.unreachable", "@online.refused", "@online.server_invalid",
                      "@online.insecure", "@online.version_mismatch", "@online.server_full", "@online.busy_server",
                      "@online.client_missing"),
}


class OnlineLogin:
    def _login_page_on(self, g, state):
        return (state.get("phase", "offline") in LOGIN_PHASES and not state.get("recovery_codes")
                and not self._direct_online(g))

    def _login_items(self, g, state, out):
        """The offline rows in card order (+ Show password, Remember me, Forgot password? / Back)."""
        if not self._login_page_on(g, state):
            return out
        by_id = {item.get("id"): item for item in out if item.get("id")}
        recover = self.__dict__.setdefault("login_page", {}).get(g.id) == "recover" and "recover_account" in by_id
        if self.login_page.get(g.id) == "recover" and not recover:
            self.login_page[g.id] = ""

        def extra(iid, label, hint, run, verb="@change", value=""):
            return dict(kind="action", id=iid, label=label, verb=verb, hint=hint, value=value, run=run,
                        detail=dict(kicker="@section.online", title=label, lead=hint, rows=[]))

        # the status row stays first (the card's message; a vanished row's focus lands on it, as everywhere)
        page = [by_id["online_status"]] if "online_status" in by_id else []
        if recover:
            page += [by_id[i] for i in ("online_name",) + RECOVER_IDS if i in by_id]
            page.append(extra("login_back", "@online_ui.login_back", "@online120.account_hint",
                              lambda: self._login_page(g, ""), verb="@back"))
        else:
            shown = self.__dict__.setdefault("login_show", {}).get(g.id, False)
            page += [by_id[i] for i in ("login_saved", "online_name", "online_password") if i in by_id]
            if "online_password" in by_id:
                page.append(extra("login_show_password", "@online_ui.show_password", "@online_ui.show_password_hint",
                                  lambda: self._login_toggle_show(g), value="@on" if shown else "@off"))
                page.append(extra("login_remember", "@online_ui.remember", "@online_ui.remember_hint",
                                  lambda: self._login_remember(g), value="@on" if self._login_auto(g) else "@off"))
            for iid in ("login_account", "login_register"):
                if iid in by_id:
                    item = by_id[iid]
                    if item.get("run"):
                        item["run"] = self._login_with_choice(g, item["run"])
                    page.append(item)
            if "recover_account" in by_id:
                page.append(extra("login_forgot", "@online_ui.forgot", "@online120.account_hint",
                                  lambda: self._login_page(g, "recover"), verb="@open"))
            page += [by_id[i] for i in ("login_guest",) if i in by_id]
            known = set(("online_status", "login_saved", "online_name", "login_guest") + ACCOUNT_IDS + RECOVER_IDS
                        + FOOTER_IDS)
            # rows this card does not place itself (a game's own extra) go above the footer
            page += [item for item in out if item.get("kind") != "heading" and item.get("id") not in known]
            page += [by_id[i] for i in FOOTER_IDS if i in by_id]
        for item in page:
            item["region"] = "login"
            item["group"] = ""
        return page

    def _login_page(self, g, page):
        self.__dict__.setdefault("login_page", {})[g.id] = page
        self.__dict__.setdefault("login_focused", set()).discard(g.id)
        self.focus[g.id + ":online"] = 0

    def _login_toggle_show(self, g):
        shown = self.__dict__.setdefault("login_show", {})
        shown[g.id] = not shown.get(g.id, False)

    def _login_auto(self, g):
        return bool(((self.__dict__.get("online_prefs") or {}).get(g.id) or {}).get("auto_login", True))

    def _login_with_choice(self, g, run):
        """Log in / Register: the adapter keeps the login only when Remember me is on."""
        def go():
            if not self.dry and bool(g.a.online_state().get("remember", True)) != self._login_auto(g):
                self._online_action(g, "login_remember")
            return run()
        return go

    def _login_remember(self, g):
        if self._dry("@online_ui.remember"):
            return
        on = not self._login_auto(g)
        prefs = self.__dict__.setdefault("online_prefs", {})
        prefs[g.id] = dict(prefs.get(g.id) or {}, auto_login=on)
        callback = getattr(self, "on_online_prefs", None)
        if callback:
            callback(dict(prefs))
        items = self.items()
        self.focus[self.key()] = next((n for n, it in enumerate(items) if it.get("id") == "login_remember"), 0)

    def _login_start_focus(self, g, items):
        """The pad starts on the name field when it is empty, else on Log in (or the remembered login)."""
        seen = self.__dict__.setdefault("login_focused", set())
        if g.id in seen or not items:
            return
        seen.add(g.id)
        if g.a.online_state().get("phase") != "offline":
            return                                # kicked / error: the focus stays on the message (row 0)
        if self.__dict__.setdefault("login_page", {}).get(g.id) == "recover":
            want = next((it.get("id") for it in items if it.get("id") == "online_recovery_code"), None)
            self.focus[g.id + ":online"] = next((n for n, it in enumerate(items) if it.get("id") == want), 0)
            return
        name = g.a.text_value("online_name").strip() if hasattr(g.a, "text_value") else ""
        want = "online_name" if not name else ("login_saved" if any(it.get("id") == "login_saved" for it in items)
                                               else "login_account")
        self.focus[g.id + ":online"] = next((n for n, it in enumerate(items) if it.get("id") == want), 0)

    def _login_side(self, items, i, step):
        """Left/right: between Log in (and its area) and Play as guest."""
        ids = [it.get("id") for it in items]
        if "login_guest" not in ids or "login_account" not in ids:
            return None
        if step > 0 and items[i].get("id") in ACCOUNT_IDS + ("online_name", "login_saved"):
            return ids.index("login_guest")
        if step < 0 and items[i].get("id") == "login_guest":
            return ids.index("login_account")
        return None

    # ---------------------------------------------------------------- view
    def _view_online_login(self, v, g, state, items, fi):
        by_id = {it.get("id"): n for n, it in enumerate(items)}
        message = state.get("message") or ""
        error = state.get("phase") in ("error", "kicked") or any(message in keys for keys in FIELD_ERRORS.values())
        field_of = next((field for field, keys in FIELD_ERRORS.items() if message in keys), "") if error else ""
        shown = self.__dict__.setdefault("login_show", {}).get(g.id, False)

        def one(iid, **more):
            if iid not in by_id:
                return None
            n = by_id[iid]
            it = items[n]
            out = dict(index=n, label=it.get("label", ""), value=it.get("value") or "", focused=n == fi,
                       verb=it.get("verb", "") if n == fi else "", disabled=bool(it.get("disabled")),
                       error=message if field_of == iid else "")
            out.update(more)
            return out

        password = one("online_password")
        if password and shown:
            password["value"] = i18n.literal(g.a.text_value("online_password"))
        footer = [one(i) for i in FOOTER_IDS if i in by_id]
        known = set(("online_status", "login_saved", "online_name", "login_guest", "login_back") + ACCOUNT_IDS
                    + RECOVER_IDS + FOOTER_IDS)
        extra = [one(it.get("id")) for it in items if it.get("id") not in known and it.get("kind") != "heading"]
        recover = self.__dict__.setdefault("login_page", {}).get(g.id) == "recover"
        if recover and not error:
            message = "@online120.account_hint"
        v["online"] = dict(
            layout="login", page="recover" if recover else "main", statusIndex=by_id.get("online_status", -1),
            statusFocused=by_id.get("online_status", -1) == fi,
            title="@online_ui.recover_title" if recover else "@online_ui.login_title",
            game=i18n.literal(g.short), art=uri(g.a.hero()) if hasattr(g.a, "hero") else "",
            message=message, error=bool(error) and not field_of, errorText=message if error and not field_of else "",
            saved=one("login_saved"), name=one("online_name"), password=password,
            show=one("login_show_password", on=shown), remember=one("login_remember", on=self._login_auto(g)),
            login=one("login_account"), register=one("login_register"), forgot=one("login_forgot"),
            guest=one("login_guest"), accountTitle="@online_ui.account_area", guestTitle="@online_ui.guest_area",
            guestNote="@online_ui.guest_note", footer=[f for f in footer if f], extra=[e for e in extra if e],
            serverLabel="@online_ui.server_line", orText="@online_ui.or",
            recover=[one(i) for i in RECOVER_IDS if i in by_id], back=one("login_back"))
