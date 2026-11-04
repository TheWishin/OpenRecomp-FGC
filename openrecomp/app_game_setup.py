"""The Backend's side of installing and updating games (Qt-free; app.Backend mixes it in)."""
import os
import subprocess
import sys

from . import manifest as mf
from . import game_releases as gr
from .game_setup import GameSetup, default_parent
from .nav_game_setup import SETUP_GAMES

FIRST_CHECK_SECONDS = 3.0


class GameSetupBackend:
    def _setup_init(self):
        self.setup = GameSetup(self.config)
        self._setup_clock = 0.0
        self._setup_started = os.environ.get(gr.NO_CHECK_ENV) == "1"     # tests: no automatic network check

    def _setup_kwargs(self):
        return dict(on_setup=self._setup_action, game_prereleases=bool(self.config.get("game_prereleases")),
                    on_prereleases=self._save_prereleases)

    def _save_prereleases(self, on):
        self.config["game_prereleases"] = bool(on)
        self._save_config()
        self._setup_check_all(force=True)
        updates = getattr(self, "updates", None)          # the launcher's own test versions follow the switch
        if updates is not None and updates.state.get("phase") in ("idle", "current", "available", "error"):
            self._offered_update = False
            updates.check(quiet=True)

    def _setup_root(self, gid):
        game = self.nav.game_by_id(gid)
        return getattr(game.a, "root", None) if game is not None and game.a.found() else None

    def _setup_check_all(self, force=False):
        for gid in SETUP_GAMES:
            root = self._setup_root(gid)
            if root:
                self.setup.check(gid, root, force=force)
            elif force and self.setup.state.get(gid, {}).get("phase") not in (None, "idle"):
                # A game not installed whose install offer was already looked up (Test versions switched since):
                # its offer follows the new channel now, not after a restart. Never looked up = asked when opened.
                self.setup.check(gid, None, force=True)

    def _setup_busy(self):
        return self.setup.busy()

    def _setup_action(self, action, gid, arg):
        """Nav -> work. Returns what Nav needs right away (a bool or a dict)."""
        if action == "check":
            return self.setup.check(gid, self._setup_root(gid), force=bool(arg))
        if action == "check_all":
            self._setup_check_all(force=True)
            return True
        if action == "default_parent":
            return default_parent()
        if action == "space":
            return self.setup.space(gid, arg)
        if action == "install":
            if self._update_busy() or self._setup_root(gid):
                return False
            return self.setup.install(gid, arg)
        if action == "update":
            root = self._setup_root(gid)
            if not root or self._update_busy():
                return False
            if gid == "t5dr":
                self.nav.close_online(only="t5dr")   # the borrowed lobby client must not run during the exchange
            return self.setup.update(gid, root)
        if action == "cancel":
            self.setup.cancel(gid)
            return True
        if action == "attach":
            return self._setup_attach(gid, arg)
        if action == "reload":
            self.nav.say(self._reload_library())
            self.setup.check(gid, self._setup_root(gid), force=True)
            return True
        if action == "restart":
            return self._setup_restart()
        return False

    def _setup_attach(self, gid, root):
        roots = self.config.setdefault("roots", {})
        roots[gid] = root
        if gid == "t5dr":
            self.config.pop("t5dr_settings_copy", None)
        try:
            mf.save_config(self.config)
        except (OSError, ValueError):
            self.nav.say("@preferences.save_failed", 8)
        message = self._reload_library()
        self.nav.say(message)
        self.nav.setup_installed(gid)
        return True

    def _setup_restart(self):
        """After a T5DR update the borrowed T5DR modules are the old ones: start this launcher again."""
        launcher = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        command = [sys.executable, "-B", "-m", "openrecomp", *sys.argv[1:]]
        flags = 0
        if os.name == "nt":
            flags = 0x00000008 | 0x00000200          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        try:
            subprocess.Popen(command, cwd=launcher, creationflags=flags, close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            self.nav.say("@setup.restart_failed", 12)
            return False
        self._quit()
        return True

    def _poll_setup(self, dt):
        changed = False
        if not self._setup_started:
            self._setup_clock += dt
            if self._setup_clock >= FIRST_CHECK_SECONDS:
                self._setup_started = True
                self._setup_check_all()
                for game in getattr(self.nav, "games", ()):      # manifest games: their release check, once
                    check = getattr(game.a, "check_updates", None)
                    if callable(check):
                        try:
                            check()
                        except Exception:  # noqa: BLE001 -- a manifest game's check never stops the launcher
                            pass
                auto = getattr(self, "_auto_check_updates", None)    # the launcher's own release, same moment
                if callable(auto):
                    auto()
        for gid in SETUP_GAMES:
            game = self.nav.game_by_id(gid)
            seen = getattr(game.a, "lobby_release", None) if game is not None and game.a.found() else None
            if callable(seen):
                try:
                    data = seen()
                except Exception:  # noqa: BLE001 -- the online client is the game's own code
                    data = None
                if data and self.setup.note_lobby(gid, data, self._setup_root(gid)):
                    changed = True
        events = self.setup.poll()
        views = {gid: self.setup.view(gid) for gid in SETUP_GAMES}
        if views != self.nav.setup_state:
            self.nav.setup_state = views
            changed = True
        if events:
            changed = self.nav.poll_setup(events) or True
        elif self.setup.busy():
            changed = self.nav.poll_setup([]) or changed
        return changed
