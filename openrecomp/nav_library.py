"""Controller registration and author-owned game updates. No network or Qt here."""
from . import i18n


class Library:
    def _cancel_library(self):
        self.library_request += 1
        self.library_pending = ""
        self.library_preview = None
        self.library_offer = None
        self.overlay = None

    def _preview_game(self, source):
        if self._dry("@library.add"):
            return
        if not self.can_reload_games():
            self.say("@library.busy")
            return
        if not self.on_game_preview:
            self.say("@library.unavailable")
            return
        self.library_request += 1
        self.library_pending = "preview"
        self._ask("library_loading")
        try:
            result = self.on_game_preview(source)
        except Exception:  # noqa: BLE001 -- untrusted source errors stay in the library flow
            self.fail_game_request()
            return
        if isinstance(result, dict):
            self.complete_game_preview(result)
        elif result and result != "@library.loading":
            self.fail_game_request()

    def complete_game_preview(self, preview, request=None):
        if (request is not None and request != self.library_request) or self.library_pending != "preview":
            return False
        if not isinstance(preview, dict) or not isinstance(preview.get("manifest"), dict):
            self.fail_game_request(request)
            return False
        self.library_preview = preview
        self.library_pending = ""
        self.library_page = 0
        self._ask("library_preview")
        return True

    def complete_game_update(self, offer, request=None):
        if (request is not None and request != self.library_request) or self.library_pending != "update":
            return False
        self.library_pending = ""
        self.library_offer = offer
        if offer and offer.get("phase", "available") == "available":
            self._ask("library_update")
        else:
            self.overlay = None
            self.say("@library.no_update")
        return True

    def fail_game_request(self, request=None):
        if request is not None and request != self.library_request:
            return False
        self.library_pending = ""
        self.overlay = None
        self.say("@library.failed", 12)
        return True

    def _library_pages(self):
        p = self.library_preview
        m = p["manifest"]
        messages = [i18n.message("library.preview_summary", name=i18n.literal(m["title"]),
                                author=i18n.literal(m.get("author", "")), source=i18n.literal(p.get("source", "")),
                                warning="@library.third_party")]
        for requirement in m.get("requirements", []):
            messages.append(i18n.message("library.requirement_summary", label=i18n.literal(requirement["label"]),
                                         kind="@game_iso" if requirement["kind"] == "iso" else "@file",
                                         version=i18n.literal(requirement["version"]), sha256=i18n.literal(requirement["sha256"])))
        pages = []
        for message in messages:
            text = i18n.localize(message, self.language)
            pages.extend(i18n.literal(text[start:start + 340]) for start in range(0, len(text), 340))
        return pages

    def _library_check(self):
        if self._dry("@library.check"):
            return
        if not self.can_reload_games():
            self.say("@library.busy")
            return
        if not self.on_game_update_check:
            self.say("@library.unavailable")
            return
        self.library_request += 1
        self.library_pending = "update"
        self._ask("library_loading")
        try:
            result = self.on_game_update_check(self.library_game)
        except Exception:  # noqa: BLE001 -- a failed release lookup must not break navigation
            self.fail_game_request()
            return
        if isinstance(result, dict) or result is None:
            self.complete_game_update(result)
        elif result != "@library.loading":
            self.fail_game_request()

    def _library_dialog(self, action):
        if action in ("left", "right", "up", "down"):
            self.exit_focus = 1 - self.exit_focus
            return
        if action == "back":
            self._cancel_library()
            return
        if action != "confirm":
            return
        kind = self.confirm_kind
        yes = self.exit_focus == 1
        if kind == "library_loading":
            self._cancel_library()
        elif kind == "library_source":
            if yes:
                self._open_picker("library_folder", "@library.local", [], [], "folder")
            else:
                self._open_osk("library_repository")
        elif kind == "library_manage":
            if yes:
                self._ask("library_remove")
            else:
                self._library_check()
        elif kind == "library_preview":
            if not yes:
                self._cancel_library()
            elif self.library_page + 1 < len(self._library_pages()):
                self.library_page += 1
                self.exit_focus = 0
            elif self.can_reload_games() and self.on_game_accept and not self._dry("@library.accept"):
                preview = self.library_preview
                self.overlay = None
                self.library_preview = None
                self.say(self.on_game_accept(preview) or "")
        elif kind == "library_remove":
            self.overlay = None
            if yes and self.can_reload_games() and self.on_game_remove and not self._dry("@library.remove"):
                self.say(self.on_game_remove(self.library_game) or "")
        elif kind == "library_update":
            self.overlay = None
            if yes and self.can_reload_games() and self.on_game_update_install and not self._dry("@library.update"):
                self.say(self.on_game_update_install(self.library_game) or "")

    def _view_library_dialog(self, view):
        kind = self.confirm_kind
        title, text = "@library.add", "@library.choose_source"
        labels = ["@library.github", "@library.local"]
        if kind == "library_loading":
            text = "@library.loading"
            labels = ["@cancel", "@cancel"]
        elif kind == "library_manage":
            title, text = "@library.manage", "@library.third_party"
            labels = ["@library.check", "@library.remove"]
        elif kind == "library_preview":
            title = "@library.preview"
            pages = self._library_pages()
            text = pages[self.library_page]
            labels = ["@cancel", "@library.next" if self.library_page + 1 < len(pages) else "@library.accept"]
        elif kind == "library_remove":
            title = "@library.remove"
            game = self.game_by_id(self.library_game)
            text = i18n.message("library.remove_confirm", name=i18n.literal(game.short if game else self.library_game))
            labels = ["@no", "@yes"]
        elif kind == "library_update":
            title = "@library.update"
            offer = self.library_offer or {}
            text = i18n.message("library.update_confirm", version=i18n.literal(offer.get("version", "")),
                                repository=i18n.literal(offer.get("repository", "")), channel=i18n.literal(offer.get("channel", "")))
            labels = ["@no", "@updates.install"]
        view["dialog"] = dict(title=title, text=text, options=[dict(label=label, index=index, focused=self.exit_focus == index)
                                                             for index, label in enumerate(labels)])
        view["hint"] = "@dialog_hint"
        view["prompts"] = [self.prompt("confirm", "@confirm"), self.prompt("right", "@switch"), self.prompt("back", "@cancel")]
