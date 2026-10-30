"""Controller file and folder picker actions and view."""
import os
import string

from . import i18n
from .nav_common import PICKER_VISIBLE, window


class Picker:
    def _open_picker(self, target, title, exts, dirs, kind):
        start = next((d for d in dirs if d and os.path.isdir(d)), "")
        self.picker = dict(target=target, title=title, exts=[e.lower() for e in exts], kind=kind, dir=start, focus=0)
        self.overlay = "picker"
        self._picker_first_file()

    def _picker_first_file(self):
        """The focus starts on the first file: usually the one the player came for."""
        entries = self._picker_entries()
        self.picker["focus"] = next((i for i, e in enumerate(entries) if e["kind"] == "file"), 0)

    def _picker_entries(self):
        p = self.picker
        out = []
        if not p["dir"]:
            for letter in string.ascii_uppercase:
                root = f"{letter}:\\"
                if os.path.exists(root):
                    out.append(dict(name=root, path=root, kind="dir"))
            return out
        if p["kind"] == "folder":
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
                        elif p["kind"] == "file" and os.path.splitext(e.name)[1].lower() in p["exts"]:
                            files.append(dict(name=e.name, path=e.path, kind="file"))
                    except OSError:
                        pass
        except OSError:
            pass
        key = lambda d: d["name"].casefold()  # noqa: E731
        return out + sorted(files, key=key) + sorted(folders, key=key)

    def _picker(self, a):
        p = self.picker
        entries = self._picker_entries()
        if a == "up":
            p["focus"] = max(0, p["focus"] - 1)
        elif a == "down":
            p["focus"] = min(len(entries) - 1, p["focus"] + 1)
        elif a == "back":
            self.overlay = None
        elif a == "confirm" and entries:
            e = entries[p["focus"]]
            if e["kind"] == "dir":
                p["dir"] = e["path"]
                self._picker_first_file()
            else:
                self.overlay = None
                self._picked(p["target"], e["path"])

    def _picked(self, target, path):
        if self._dry(i18n.message("dry_use", path=path)):
            return
        if target == "manifest":
            self.say(self.install(path) if self.install else "")
        elif target.startswith("source:"):
            message = self.game.a.set_source(target[7:], path)
            if message == "reload" and self.install:
                self.say(self.install(None))
            elif message:
                self.say(message)

    def _view_picker(self, v):
        p = self.picker
        entries = self._picker_entries()
        start = window(len(entries), p["focus"], PICKER_VISIBLE)
        rows = [dict(index=i, name=e["name"], kind=e["kind"], focused=i == p["focus"]) for i, e in enumerate(entries[start:start + PICKER_VISIBLE], start)]
        v["picker"] = dict(rows=rows, title=p["title"], path=p["dir"] or "@picker.this_pc", up=start > 0, down=start + PICKER_VISIBLE < len(entries))
        v["hint"] = "@picker_files_hint" if p["kind"] == "file" else "@picker_folder_hint"
        v["prompts"] = [self.prompt("confirm", "@open"), self.prompt("back", "@cancel")]
