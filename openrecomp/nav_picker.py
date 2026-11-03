"""Controller file and folder picker actions and view."""
import os
import string

from . import i18n
from .nav_common import PICKER_VISIBLE, window


class Picker:
    """Mouse and keyboard get the Windows Explorer dialog (when the app has one: native_picker); a controller gets
    the launcher's own list. Both end in _picked(), so a path is checked the same way whichever chose it."""

    def _open_picker(self, target, title, exts, dirs, kind, filter_name=""):
        """filter_name: what the files are ("@t4.iso_filter"), the Explorer dialog's first filter."""
        exts = [e.lower() for e in exts]
        if self.device == "kb" and self.native_picker:
            self._request_native(target, title, exts, kind, self._picker_start(dirs, kind, exts, downloads=True), filter_name)
            return
        self._open_list_picker(target, title, exts, kind, self._picker_start(dirs, kind, exts))

    def _open_list_picker(self, target, title, exts, kind, start, filter_name=""):
        self.picker = dict(target=target, title=title, exts=exts, kind=kind, dir=start, focus=0, filter_name=filter_name)
        self.overlay = "picker"
        self._picker_first_file()

    @staticmethod
    def _dir_key(kind, exts):
        """Folders are remembered per type: the last ISO folder is not the last game folder."""
        return exts[0] if kind == "file" and exts else "folder"

    def _picker_start(self, dirs, kind, exts=(), downloads=False):
        """A folder setting opens at its own value; a file opens where the player last chose one of its type."""
        dirs = [d for d in dirs if d]
        last = self.picker_dirs.get(self._dir_key(kind, list(exts)), "")
        order = dirs + [last] if kind != "file" else [last] + dirs
        if downloads:
            order.append(os.path.join(os.path.expanduser("~"), "Downloads"))
        return next((d for d in order if d and os.path.isdir(d)), "")

    def _remember_dir(self, path, exts):
        if os.path.isdir(path):
            key, folder = "folder", path
        else:
            ext = os.path.splitext(path)[1].lower()
            key, folder = ext if ext in exts else "folder", os.path.dirname(path)
        if folder and self.picker_dirs.get(key) != folder:
            self.picker_dirs[key] = folder
            if not self.dry:
                self.on_picker_dir(key, folder)

    # ---------------------------------------------------------------- the Windows Explorer dialog
    def _request_native(self, target, title, exts, kind, start, filter_name=""):
        """The app opens the dialog after this action (native_request) and hands back native_result()."""
        self.overlay = None
        self.pending_native = dict(target=target, title=title, exts=exts, kind=kind, dir=start, filter_name=filter_name)

    def native_request(self):
        """-> dict(title, kind, filters, start) for the dialog, localized; None when nothing waits. Taken once.

        A "zip or folder" source (the T4 game) opens the FOLDER dialog: the zip has its own row."""
        r, self.pending_native = self.pending_native, None
        if r is None:
            return None
        kind = "file" if r["kind"] == "file" else "folder"
        filters = []
        if kind == "file" and r["exts"]:
            patterns = ";".join("*" + e for e in r["exts"])
            shown = i18n.literal(patterns.replace(";", "; "))
            name = (i18n.message("picker.filter_named", name=r["filter_name"], patterns=shown) if r.get("filter_name")
                    else i18n.message("picker.filter_matching", patterns=shown))
            filters = [(i18n.localize(name, self.language), patterns),
                       (i18n.localize("@picker.filter_all", self.language), "*.*")]
        return dict(request=r, title=i18n.localize(r["title"], self.language), kind=kind, filters=filters, start=r["dir"])

    def native_result(self, request, path):
        """The dialog closed: path = the player's choice, "" = cancelled (nothing happens)."""
        r = request["request"]
        if not path:
            return
        if request["kind"] == "folder" and not os.path.isdir(path):
            self.say("@picker_not_folder")
            return
        if request["kind"] == "file" and r["exts"] and os.path.splitext(path)[1].lower() not in r["exts"]:
            self.say(i18n.message("picker_wrong_type", types=i18n.literal(", ".join(r["exts"]))), 8)
            return
        self._remember_dir(path, r["exts"])
        self._picked(r["target"], path)

    def native_failed(self, request):
        """No Explorer dialog on this PC (or Windows refused one): the launcher's own list instead."""
        r = request["request"]
        self._open_list_picker(r["target"], r["title"], r["exts"], r["kind"], r["dir"], r.get("filter_name", ""))

    def _picker_first_file(self):
        """The focus starts on the first file: usually the one the player came for."""
        entries = self._picker_entries()
        self.picker["focus"] = next((i for i, e in enumerate(entries) if e["kind"] == "file"), 0)

    def _picker_entries(self):
        p = self.picker
        p["error"] = False
        out = []
        if not p["dir"]:
            for letter in string.ascii_uppercase:
                root = f"{letter}:\\"
                if os.path.exists(root):
                    out.append(dict(name=root, path=root, kind="dir"))
            return out
        if p["kind"] in ("folder", "file_or_folder"):
            out.append(dict(name="@picker.choose_folder", path=p["dir"], kind="pick"))
        parent = os.path.dirname(p["dir"].rstrip("\\/"))
        out.append(dict(name="..", path="" if parent == p["dir"].rstrip("\\/") or len(p["dir"]) <= 3 else parent, kind="dir"))
        folders, files = [], []
        try:
            with os.scandir(p["dir"]) as it:
                for e in it:
                    try:
                        if e.is_dir():
                            folders.append(dict(name=e.name, path=e.path, kind="dir"))
                        elif p["kind"] in ("file", "file_or_folder") and (not p["exts"] or os.path.splitext(e.name)[1].lower() in p["exts"]):
                            files.append(dict(name=e.name, path=e.path, kind="file"))
                    except OSError:
                        pass
        except OSError:
            p["error"] = True
            out = [e for e in out if e["kind"] != "pick"]
        key = lambda d: d["name"].casefold()  # noqa: E731
        return out + sorted(files, key=key) + sorted(folders, key=key)

    def _picker(self, a):
        p = self.picker
        entries = self._picker_entries()
        p["focus"] = max(0, min(p["focus"], len(entries) - 1))
        if a == "up":
            p["focus"] = max(0, p["focus"] - 1)
        elif a == "down":
            p["focus"] = max(0, min(len(entries) - 1, p["focus"] + 1))
        elif a == "back":
            self.overlay = None
        elif a == "x" and self.native_picker:
            self._request_native(p["target"], p["title"], p["exts"], p["kind"], p["dir"], p.get("filter_name", ""))
        elif a == "confirm" and entries:
            e = entries[p["focus"]]
            if e["kind"] == "dir":
                p["dir"] = e["path"]
                self._picker_first_file()
            else:
                self.overlay = None
                self._remember_dir(e["path"], p["exts"])
                self._picked(p["target"], e["path"])

    def _picked(self, target, path):
        if self._dry(i18n.message("dry_use", path=path)):
            return
        if (target == "manifest" or target.startswith("source:")) and not self.can_reload_games():
            self.say("@library.busy")
            return
        if target == "library_folder":
            self._preview_game(path)
        elif target == "setup_folder":
            self.setup_folder_picked(path)
        elif target == "manifest":
            self.say(self.install(path) if self.install else "")
        elif target.startswith("setting:"):
            self.game.a.set_setting(target[8:], path)
        elif target.startswith("source:"):
            game = self.game
            message = self.game.a.set_source(target[7:], path)
            if message == "reload" and self.install:
                self._reload_source(game)
            elif message:
                self.say(message)
            state = game.a.source_state()
            if state.get("id") == target[7:] and (state.get("running") or state.get("result")):
                self.source_checks[game.id] = game
                self.poll_sources()

    def poll_sources(self):
        changed = False
        for gid, game in list(self.source_checks.items()):
            state = game.a.source_state()
            if state.get("running"):
                continue
            if state.get("result") == "reload" and self.install:
                if not self.can_reload_games() or not self._reload_source(game):
                    continue
                del self.source_checks[gid]
                changed = True
                continue
            del self.source_checks[gid]
            changed = True
            if state.get("result"):
                self.say(state["result"], 12)
            if state.get("ok") and self.game is game and self.screen == "hub" and self.section() == "build" and not self.overlay:
                items = self._items_build(game)
                self.focus[gid + ":build"] = next((i for i, item in enumerate(items) if item.get("id") == "build"), 0)
        return changed

    def _reload_source(self, game):
        try:
            message = self.install(None)
        except Exception:  # noqa: BLE001 -- a registration failure must not break the timer
            self.say("@t4.install_failed", 12)
            return True
        self.say(message)
        if message == "@library.busy":
            return False
        if message == "@folder_saved" and self.game and self.game.id == game.id and self.game.m.get("adapter") == "t4" and self.game.a.found():
            self.screen = "hub"
            self.sec[self.game.id] = "build"
            self.focus[self.game.id + ":build"] = 0
            self.say("@t4.install_next", 12)
        return True

    def _view_picker(self, v):
        p = self.picker
        entries = self._picker_entries()
        p["focus"] = max(0, min(p["focus"], len(entries) - 1))
        start = window(len(entries), p["focus"], PICKER_VISIBLE)
        rows = [dict(index=i, name=e["name"], kind=e["kind"], focused=i == p["focus"]) for i, e in enumerate(entries[start:start + PICKER_VISIBLE], start)]
        message = ""
        if p.get("error"):
            message = "@picker_unreadable"
        elif not entries:
            message = "@picker_empty"
        elif p["kind"] == "file" and not any(e["kind"] == "file" for e in entries):
            message = "@picker_no_matches"
        v["picker"] = dict(rows=rows, title=p["title"], path=p["dir"] or "@picker.this_pc", up=start > 0, down=start + PICKER_VISIBLE < len(entries), message=message)
        v["hint"] = message or ("@picker_files_hint" if p["kind"] == "file" else "@picker_folder_hint")
        v["prompts"] = []
        if entries:
            v["prompts"].append(self.prompt("confirm", "@open" if entries[p["focus"]]["kind"] == "dir" else "@choose"))
        if self.native_picker:
            v["prompts"].append(self.prompt("x", "@picker.explorer"))
        v["prompts"].append(self.prompt("back", "@cancel"))
