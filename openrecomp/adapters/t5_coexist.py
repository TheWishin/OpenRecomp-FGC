"""Read installed T5DR preferences; save explicit changes only in this launcher's home."""
from contextlib import contextmanager
import hashlib
import json
import os
import sys
import tempfile
import threading

from ..manifest import user_dir

_IMPORT_LOCK = threading.RLock()


@contextmanager
def readonly_imports():
    with _IMPORT_LOCK:
        previous = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            yield
        finally:
            sys.dont_write_bytecode = previous


def read_object(path):
    with open(path, encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("@not_ready")
    return value


def _resolved(path):
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def _overlap(first, second):
    first, second = _resolved(first), _resolved(second)
    try:
        return os.path.commonpath((first, second)) in (first, second)
    except ValueError:
        return False


def local_path(root, name):
    if not name or os.path.basename(name) != name or name in (".", ".."):
        raise ValueError("@not_ready")
    home = user_dir()
    if _overlap(home, root):
        raise ValueError("@not_ready")
    identity = hashlib.sha256(_resolved(root).encode("utf-8")).hexdigest()[:24]
    path = os.path.join(home, "t5dr", identity, name)
    if _overlap(path, root) or not _resolved(path).startswith(_resolved(home) + os.sep):
        raise ValueError("@not_ready")
    return path


class _CoexistSettings:
    coexistence = True

    def __init__(self, root, settings_source=None):
        self._coexist_loading = True
        self._coexist_pending = {}
        self._coexist_root = os.path.abspath(root)
        self._coexist_home = user_dir()
        self._coexist_protected = [self._coexist_root]
        # Refuse an overlapping home before the installed constructor can run.
        local_path(root, "settings.json")
        super().__init__()
        self._coexist_source_path = os.fspath(getattr(self, "path", None) or os.path.join(root, "launcher.json"))
        self._coexist_protected.append(os.path.dirname(os.path.abspath(self._coexist_source_path)))
        self._coexist_copy = None
        if settings_source:
            source = os.fspath(settings_source)
            self._coexist_copy = os.path.abspath(source if os.path.isdir(source) else os.path.dirname(source))
            source = os.path.join(source, "launcher.json") if os.path.isdir(source) else source
            values = read_object(source)
            clear = getattr(super(), "clear", None)
            if callable(clear):
                clear()
            for key, value in self._coexist_defaults.items():
                super().__setitem__(key, value)
            for key, value in values.items():
                super().__setitem__(key, value)
            self._coexist_source_path = os.path.abspath(source)
            self._coexist_protected.append(self._coexist_copy)
        out_dir = getattr(self, "out_dir", None)
        if out_dir:
            self._coexist_protected.append(os.path.abspath(out_dir))
        path = self.private_path("settings.json")
        try:
            overrides = read_object(path)
        except FileNotFoundError:
            overrides = {}
        for key, value in overrides.items():
            super().__setitem__(key, value)
        if ("screen_side" in self._coexist_defaults and "always_left" in overrides
                and "screen_side" not in overrides):
            # An edit saved before the install had the three-way side (1.1.9) keeps its meaning on 1.2.0.
            super().__setitem__("screen_side", "left" if overrides["always_left"] is True else "dealt")
        self._coexist_loading = False

    @property
    def source_path(self):
        return self._coexist_source_path

    @property
    def coexist_dir(self):
        return os.path.dirname(self.private_path("settings.json"))

    def private_path(self, name):
        # The checks resolve every folder on disk (realpath): seconds of a frozen window when the launcher asked
        # on every redraw. The answer only changes with the folders it was made from.
        key = (name, user_dir(), self._coexist_root, tuple(self._coexist_protected))
        known = self.__dict__.setdefault("_coexist_checked", {})
        if key in known:
            return known[key]
        path = local_path(self._coexist_root, name)
        if any(_overlap(self._coexist_home, source) or _overlap(path, source)
               for source in self._coexist_protected):
            raise ValueError("@not_ready")
        known[key] = path
        return path

    @property
    def controls_write_path(self):
        return self.private_path("controls.json")

    @property
    def online_config_path(self):
        return self.private_path("online.json")

    @property
    def legacy_online_paths(self):
        if self._coexist_copy:
            return (os.path.join(self._coexist_copy, "online.json"),)
        base = os.environ.get("T5_ONLINE_DIR")
        if not base:
            base = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "T5DROnline")
        return (os.path.join(base, "online.json"), os.path.join(os.path.dirname(self.source_path), "online.json"))

    @property
    def legacy_controls_paths(self):
        """Where OpenRecomp (before 0.1.6.1) kept controls of its own: the private copy, then a chosen settings copy's.
        Controls are one file now -- the one T5DR's own launcher edits (t5_controls migrates these once)."""
        paths = [self.controls_write_path]
        if self._coexist_copy:
            paths.append(os.path.join(self._coexist_copy, "controls.json"))
        return tuple(paths)

    def env_overrides(self):
        # No PS3_CONTROLS of our own: the game and both launchers read the same controls.ini (a PS3_CONTROLS the
        # player set in the settings stays, via super()).
        return dict(super().env_overrides())

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if not self._coexist_loading:
            self._coexist_pending[key] = value

    def save(self):
        # Some installed Settings constructors save defaults. Attachment must not.
        if self._coexist_loading or not self._coexist_pending:
            return
        path = self.private_path("settings.json")
        try:
            values = read_object(path)
        except FileNotFoundError:
            values = {}
        values.update(self._coexist_pending)
        folder = os.path.dirname(path)
        os.makedirs(folder, exist_ok=True)
        path = self.private_path("settings.json")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder,
                                             prefix=".settings-", suffix=".tmp", delete=False) as stream:
                temporary = stream.name
                json.dump(values, stream, indent=1)
            os.replace(temporary, path)
            self._coexist_pending.clear()
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)


def load_settings(core, root, settings_source=None):
    """Retain native properties and environment policy, replacing only persistence."""
    native = core.Settings
    if not isinstance(native, type):
        raise ValueError("@not_ready")
    settings_type = type("_OpenRecompSettings", (_CoexistSettings, native),
                         {"_coexist_defaults": dict(getattr(core, "DEFAULTS", {}))})
    with readonly_imports():
        return settings_type(root, settings_source)
