"""The Qt side: one window, one QML scene, one Backend object between the scene and Nav."""
import argparse
import ctypes
import copy
import os
import queue
import sys
import threading

from PySide6.QtCore import QObject, QTimer, Property, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication, QIcon, QWindow
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow  # noqa: F401 -- so the scene's root comes back as a QQuickWindow

from . import adapters, file_dialog, i18n, manifest as mf
from .nav import Game, Nav
from .pad import Pads, PlayStationReader, WinMMPlayStationReader, XInputReader
from .update_service import UpdateService
from . import updater
from .game_library import Library
from .game_updates import GameUpdates
from .app_game_setup import GameSetupBackend

UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
KEYS = {Qt.Key_Up: "up", Qt.Key_Down: "down", Qt.Key_Left: "left", Qt.Key_Right: "right", Qt.Key_Return: "confirm", Qt.Key_Enter: "confirm",
        Qt.Key_Escape: "back", Qt.Key_Space: "play", Qt.Key_X: "x", Qt.Key_F: "social", Qt.Key_G: "switchGame", Qt.Key_Q: "prev", Qt.Key_E: "next"}
KEYS = {int(k): v for k, v in KEYS.items()}   # by number: an unknown key (any layout's letter) is no ValueError
TICK_MS = 16
CTRL, SHIFT, ALT = int(Qt.ControlModifier.value), int(Qt.ShiftModifier.value), int(Qt.AltModifier.value)
# Ctrl+letter edits by the letter Qt reports, the control character Windows types (Ctrl+V = \x16 on every layout) or,
# for a non-Latin layout's letter, the key's position (PC scan code): a Russian or Greek layout's Ctrl+V still pastes.
EDIT_LETTERS = {"paste": (int(Qt.Key_V), "\x16", 0x2F), "copy": (int(Qt.Key_C), "\x03", 0x2E),
                "cut": (int(Qt.Key_X), "\x18", 0x2D), "select_all": (int(Qt.Key_A), "\x01", 0x1E)}
EDIT_KEYS = {(int(Qt.Key_Insert), SHIFT): "paste", (int(Qt.Key_Insert), CTRL): "copy", (int(Qt.Key_Delete), SHIFT): "cut"}


def edit_shortcut(key, text, modifiers, scan):
    """-> "paste" / "copy" / "cut" / "select_all" / None for one key press."""
    modifiers = int(modifiers) & (CTRL | SHIFT | ALT)
    if (int(key), modifiers) in EDIT_KEYS:
        return EDIT_KEYS[(int(key), modifiers)]
    if not modifiers & CTRL or modifiers & ALT:   # Ctrl+Alt = AltGr: a typed character (@, {, ...)
        return None
    latin = int(Qt.Key_A) <= int(key) <= int(Qt.Key_Z)
    for edit, (letter, control, position) in EDIT_LETTERS.items():
        if int(key) == letter or text == control or (not latin and (int(scan) & 0xFF) == position):
            return edit
    return None


def native_picker_available():
    """The Explorer dialog needs a real Windows desktop: never offscreen (tests) or with OPENRECOMP_NATIVE_PICKER=0."""
    if os.name != "nt" or os.environ.get("OPENRECOMP_NATIVE_PICKER") == "0":
        return False
    try:
        return QGuiApplication.platformName() == "windows"
    except RuntimeError:
        return False


def picker_dirs(config):
    """The last folder per kind of file (".iso", ".pkg", ...) and for folders; anything else in the config is dropped."""
    dirs = config.get("picker_dirs")
    if not isinstance(dirs, dict):
        return {}
    return {k: v for k, v in dirs.items() if isinstance(k, str) and isinstance(v, str) and len(k) <= 16 and v}


def load_games(config):
    manifests, problems = mf.load_all()
    games = [Game(m, adapters.make(m, config)) for m in manifests]
    for game in games:
        # T4 Online may offer a T5DR remembered login (one account for both); each adapter decides what it reads.
        game.a.account_peers = tuple(other.a for other in games if other is not game)
    problems += [g.a.problem for g in games if g.a.problem]
    return games, problems


class Backend(QObject, GameSetupBackend):
    viewChanged = Signal()

    def __init__(self, launch_env=None, parent=None, windowed=False):
        super().__init__(parent)
        self.config = mf.load_config()
        self.library = Library(self.config)
        self._library_results = queue.Queue()
        self._library_work = None
        self._game_offers = {}
        self._game_updaters = {}
        games, problems = load_games(self.config)
        self._setup_init()
        self.choose_file = file_dialog.choose     # (owner, title, kind, filters, start) -> path; tests put a fake here
        self._native_queued = False
        self._native_open = False
        self.nav = Nav(games, on_quit=self._quit, install=self._install, launch_env=launch_env,
                       native_picker=native_picker_available(), picker_dirs=picker_dirs(self.config),
                       on_picker_dir=self._save_picker_dir,
                       language=self.config.get("language"), on_language=self._save_language,
                       last_game=self.config.get("last_game"), on_game=self._save_game,
                       fullscreen=self.config.get("fullscreen", True) and not windowed,
                       reduced_motion=self.config.get("reduced_motion", False), on_preferences=self._save_preferences,
                       on_update_check=self._check_updates, on_update_install=self._install_update,
                       on_game_preview=self._preview_game, on_game_accept=self._accept_game,
                       on_game_remove=self._remove_game, on_game_update_check=self._check_game_update,
                       on_game_update_install=self._install_game_update, **self._setup_kwargs())
        self.updates = UpdateService(busy=self._update_busy, quit=self._quit,
                                     prereleases=lambda: bool(self.config.get("game_prereleases")))
        self._offered_update = False
        self._update_phase = "idle"
        if problems:
            self.nav.say(problems[0], 8)
        try:
            result = updater.update_result(self.updates.root)
            updater.clean_finished(self.updates.root)
        except (OSError, ValueError, TypeError):
            result = None
        if result and result.get("status") == "updated" and result.get("version") == updater.local_version(self.updates.root):
            self.nav.say(i18n.message("updates.updated", version=i18n.literal(result["version"])), 8)
        elif result and result.get("status") == "rolled_back":
            self.nav.say("@updates.rolled_back", 12)
        elif result and result.get("status") == "recovery_required":
            self.nav.say("@updates.recovery", 20)
        elif result and result.get("status") == "unchanged":
            self.nav.say("@updates.failed", 12)
        self.pads = None
        self._pad_root = None
        self._load_pads(games)
        self.window = None
        self._view = {}
        self._was_running = False
        self._was_building = False
        self._was_sourcing = False
        self._last_hero = {}
        self._last_status = {}
        self._last_build = {}
        self._last_prerequisites = {}
        self._slow = 0.0
        self.refresh()
        self.timer = QTimer(self)
        self.timer.setInterval(TICK_MS)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    def _update_busy(self):
        if getattr(self, "_library_work", None) is not None:
            return True
        if getattr(self, "setup", None) is not None and self._setup_busy():
            return True
        if self.nav.binding_active():
            return True
        for game in self.nav.games:
            adapter = game.a
            if (adapter.running() or adapter.build_state().get("running")
                    or adapter.source_state().get("running")
                    or adapter.support_state().get("running")):
                return True
            online = adapter.online_state()
            if online.get("busy") or online.get("phase", "offline") not in ("offline", "error", "kicked"):
                return True
        return False

    def _quit(self):
        if self.window is not None:
            self.window.setProperty("allowClose", True)
        QGuiApplication.quit()

    def _check_updates(self):
        self.updates.check()

    def _auto_check_updates(self):
        """A few seconds after the start (with the games' check): an offer appears, nothing is said otherwise."""
        if self.updates.state.get("phase") == "idle" and not self._update_busy():
            self.updates.check(quiet=True)

    def _install_update(self):
        if not self.updates.install():
            self.nav.say("@updates.busy")

    def _poll_updates(self):
        changed = self.updates.poll()
        self.nav.update_state = dict(self.updates.state)
        phase = self.updates.state["phase"]
        if phase != self._update_phase:
            changed = True
            self._update_phase = phase
            if phase in ("current", "unconfigured", "error") and not self.updates.quiet:
                key = "failed" if phase == "error" else phase
                self.nav.say("@updates." + key, 8)
        if phase == "available" and not self._offered_update and not self._update_busy():
            self._offered_update = self.nav.offer_update()
            changed = changed or self._offered_update
        return changed

    def _library_job(self, kind, operation, game_id=""):
        if self._library_work is not None or self._update_busy():
            return "@library.busy"
        request = self.nav.library_request
        self._library_work = (kind, request, game_id)
        self.nav.library_busy = True

        def work():
            try:
                result, failed = operation(), False
            except Exception:  # noqa: BLE001 -- never expose local paths or network response text
                result, failed = None, True
            self._library_results.put((kind, request, game_id, result, failed))

        try:
            threading.Thread(target=work, daemon=True).start()
        except Exception:  # noqa: BLE001 -- a missing worker must leave navigation usable
            self._library_work = None
            self.nav.library_busy = False
            return "@library.failed"
        return "@library.loading"

    def _preview_game(self, source):
        return self._library_job("preview", lambda: self.library.preview(source))

    def _reload_library(self):
        games, problems = load_games(self.config)
        if not self.nav.set_games(games):
            return "@library.busy"
        self._load_pads(games)
        return problems[0] if problems else "@library.saved"

    def _accept_game(self, preview):
        if not self.nav.can_reload_games():
            return "@library.busy"
        try:
            self.library.accept(preview)
            self._game_offers.clear()
            self._game_updaters.clear()
            return self._reload_library()
        except Exception:  # noqa: BLE001 -- registration errors use the selected language
            return "@library.failed"

    def _remove_game(self, game_id):
        if not self.nav.can_reload_games():
            return "@library.busy"
        try:
            self.library.remove(game_id)
            self._game_offers.pop(game_id, None)
            self._game_updaters.pop(game_id, None)
            return self._reload_library()
        except Exception:  # noqa: BLE001 -- game folders and their data are never removed
            return "@library.failed"

    def _check_game_update(self, game_id):
        if self._library_work is not None:
            return "@library.busy"
        game = self.nav.game_by_id(game_id)
        if game is None or game.m.get("adapter") != "generic":
            return "@library.failed"
        manifest = copy.deepcopy(game.m)
        service = GameUpdates(copy.deepcopy(self.config))
        self._game_updaters[game_id] = service
        return self._library_job("check", lambda: service.check(manifest), game_id)

    def _install_game_update(self, game_id):
        if self._library_work is not None:
            return "@library.busy"
        game = self.nav.game_by_id(game_id)
        offer = self._game_offers.get(game_id)
        if game is None or offer is None or game.m.get("adapter") != "generic":
            return "@library.failed"
        manifest = copy.deepcopy(game.m)
        service = self._game_updaters.get(game_id)
        if service is None:
            return "@library.failed"
        service.config = copy.deepcopy(self.config)

        def install():
            root = service.install(manifest, offer)
            return dict(root=root, version=offer["version"])

        return self._library_job("install", install, game_id)

    def _poll_library(self):
        try:
            kind, request, game_id, result, failed = self._library_results.get_nowait()
        except queue.Empty:
            return False
        self._library_work = None
        self.nav.library_busy = False
        if failed:
            self.nav.fail_game_request(request=request)
        elif kind == "preview":
            self.nav.complete_game_preview(result, request=request)
        elif kind == "check":
            if request == self.nav.library_request:
                self._game_offers[game_id] = result
                self.nav.complete_game_update(result, request=request)
        elif kind == "install":
            # Extraction is already complete in a separate version directory. Publish
            # the new root only on this thread, preserving unrelated live preferences.
            previous = copy.deepcopy(self.config)
            self.config.setdefault("roots", {})[game_id] = result["root"]
            self.config.setdefault("game_versions", {})[game_id] = result["version"]
            try:
                mf.save_config(self.config)
            except Exception:  # noqa: BLE001 -- keep the previous registration on save failure
                self.config.clear()
                self.config.update(previous)
                self.nav.say("@library.failed")
                return True
            try:
                self._game_offers.pop(game_id, None)
                self._game_updaters.pop(game_id, None)
                self.nav.say(self._reload_library())
            except Exception:  # noqa: BLE001 -- the saved registration must stay in sync with disk
                self.nav.say("@library.failed")
        return True

    def _save_config(self):
        try:
            mf.save_config(self.config)
        except (OSError, ValueError):
            self.nav.say("@preferences.save_failed", 8)

    def _save_language(self, language):
        self.config["language"] = language
        self._save_config()

    def _save_game(self, game_id):
        self.config["last_game"] = game_id
        self._save_config()

    def _save_picker_dir(self, key, folder):
        dirs = picker_dirs(self.config)
        dirs[key] = folder
        self.config["picker_dirs"] = dirs
        self._save_config()

    def _queue_native(self):
        """A mouse or keyboard press asked for a file: the Explorer dialog opens once this press is handled."""
        if self.nav.pending_native is None or self._native_queued or self._native_open:
            return
        self._native_queued = True
        QTimer.singleShot(0, self._run_native)

    def _run_native(self):
        self._native_queued = False
        request = self.nav.native_request()
        if request is None or self._native_open:
            return
        owner = 0
        try:
            owner = int(self.window.winId()) if self.window is not None else 0
        except (AttributeError, RuntimeError, TypeError, ValueError):
            owner = 0
        self.nav.release("confirm")
        self._native_open = True
        try:
            path = self.choose_file(owner, request["title"], request["kind"], request["filters"], request["start"])
        except Exception:  # noqa: BLE001 -- no dialog on this PC: the launcher's own list does the same job
            path = None
        finally:
            self._native_open = False
        if self.pads is not None:
            self.pads.suppress()          # a button held while the dialog was open is not a launcher press
        if path is None:
            self.nav.native_failed(request)
        else:
            self.nav._guard(self.nav.native_result, request, path)
        self.refresh()

    def _save_preferences(self, fullscreen, reduced_motion):
        self.config.update(fullscreen=fullscreen, reduced_motion=reduced_motion)
        self._save_config()
        if self.window is not None:
            changed = self.window.property("wantFull") != fullscreen
            self.window.setProperty("wantFull", fullscreen)
            if changed and not self.window.windowState() & Qt.WindowMinimized:
                self.window.showFullScreen() if fullscreen else self.window.showNormal()

    def _load_pads(self, games):
        t5 = next((g.a for g in games if g.id == "t5dr" and g.a.found()), None)
        root = os.path.normcase(os.path.realpath(t5.root)) if t5 is not None else ""
        if self.pads is not None:
            if root == self._pad_root:
                self.pads.suppress()
                return
            self.pads.forget()
        readers = [XInputReader(), WinMMPlayStationReader()]
        if t5 is not None:
            readers.append(PlayStationReader(t5.root))
        self.pads = Pads(readers)
        self._pad_root = root
        self.pads.suppress()

    def _install(self, path):
        """path = a player's manifest; None = a game's folder was chosen. Both: load the games again."""
        if not self.nav.can_reload_games():
            return "@library.busy"
        message = ""
        if path:
            try:
                m = mf.install(path)
                message = i18n.message("manifest_installed", name=m["title"])
            except mf.ManifestError as e:
                return str(e)
        else:
            mf.save_config(self.config)
            message = "@folder_saved"
        games, problems = load_games(self.config)
        if not self.nav.set_games(games):
            return "@library.busy"
        self._load_pads(games)
        return problems[0] if problems else message

    @Property("QVariant", notify=viewChanged)
    def view(self):
        return self._view

    def refresh(self):
        self._copy_pending()
        if getattr(self.nav, "pending_native", None) is not None:
            self._queue_native()
        self._view = self.nav.view()
        wordmark = os.path.join(UI_DIR, "assets", "logo-wordmark.svg")
        self._view["wordmark"] = QUrl.fromLocalFile(wordmark).toString() if os.path.isfile(wordmark) else ""
        self.viewChanged.emit()

    def _copy_pending(self):
        text = getattr(self.nav, "pending_clipboard", None)
        if text is None:
            return
        self.nav.pending_clipboard = None
        try:
            QGuiApplication.clipboard().setText(text)
        except (AttributeError, RuntimeError):
            self.nav.say("@t4.tools.copy_failed")

    def _in_front(self):
        return self.window is None or self.window.isActive() or os.environ.get("OPENRECOMP_PAD_ALWAYS") == "1"

    def _tick(self):
        dt = TICK_MS / 1000.0
        running = any(g.a.running() for g in self.nav.games)
        if any(g.m.get("adapter") == "t4" and g.a.running() for g in self.nav.games):
            if self.pads.return_requested(dt):
                self.nav.act("returnGame", device=self.pads.kind)
        else:
            self.pads.reset_return()
        active = self._in_front() and not running
        if not active:
            self.nav.release("confirm")
        changed = self.nav.tick(dt)
        changed = self._poll_updates() or changed
        if hasattr(self, "setup"):
            changed = self._poll_setup(dt) or changed
        if hasattr(self, "_poll_library"):
            changed = self._poll_library() or changed
        running = any(g.a.running() for g in self.nav.games)
        active = active and not running
        capturing = self.nav.binding_active()
        if capturing:
            self.pads.suppress()
        changed = self.nav.poll_tools(active=active) or changed
        if active and not capturing:
            for action, edge in self.pads.poll():
                self.nav.pad_kind = self.pads.kind
                changed = True
                if edge == "down":
                    self.nav.act(action, device=self.pads.kind)
                    if self.nav.binding_active():
                        self.pads.suppress()
                        break
                else:
                    self.nav.release(action)
        elif not active:
            self.pads.forget()
        self._slow += dt
        if self._slow >= 0.5:                 # game ended, build moved on, a picture got ready
            self._slow = 0.0
            changed = self._slow_changes(running) or changed
        if changed:
            self.refresh()

    def _slow_changes(self, running):
        changed = False
        if running != self._was_running:
            self._was_running = running
            changed = True
            if self.window is not None:
                if running:
                    self.window.showMinimized()
                else:
                    self.window.showFullScreen() if self.window.property("wantFull") else self.window.showNormal()
                    self.window.requestActivate()
        building = any(g.a.build_state()["running"] for g in self.nav.games if g.a.found())
        if building or building != self._was_building:
            self._was_building = building
            changed = True
        sourcing = any(g.a.source_state().get("running") for g in self.nav.games)
        if sourcing or sourcing != getattr(self, "_was_sourcing", False):
            self._was_sourcing = sourcing
            changed = True
        for g in self.nav.games:
            # A short run, final build result or tool check can finish between polls.
            for method, cache_name in (("status", "_last_status"), ("build_state", "_last_build"),
                                       ("prerequisites", "_last_prerequisites"),
                                       ("prerequisite_install_state", "_last_tool_install")):
                cache = getattr(self, cache_name, None)
                if cache is None:
                    cache = {}
                    setattr(self, cache_name, cache)
                snapshot = getattr(g.a, method)()
                if snapshot != cache.get(g.id):
                    cache[g.id] = snapshot
                    changed = True
            hero = g.a.hero()
            if hero != self._last_hero.get(g.id):
                self._last_hero[g.id] = hero
                changed = True
        return changed

    # ---------------------------------------------------------------- from the scene
    @Slot()
    def requestQuit(self):
        self.nav.request_quit()
        self.refresh()

    @Slot(int, str, bool)
    def keyDown(self, key, text, repeat):
        Backend.keyPress(self, key, text, repeat, 0, 0)

    @Slot(int, str, bool, int, int)
    def keyPress(self, key, text, repeat, modifiers, scan):
        """A key of a real keyboard. modifiers/scan (the key's position) find Ctrl+V & co. on any layout."""
        action = KEYS.get(key)
        nav = self.nav
        if nav.overlay == "osk":
            edit = edit_shortcut(key, text, modifiers, scan)
            if edit:
                if not repeat or edit == "paste":
                    Backend.oskEdit(self, edit)
                return
            if modifiers & CTRL and not modifiers & ALT:
                return                    # Ctrl+F, Ctrl+X ...: never a typed letter or a launcher action here
            if key == Qt.Key_Backspace:
                nav.act("x", device="kb")
                self.refresh()
                return
            if text and text.isprintable() and key not in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
                nav.type_text(text)
                self.refresh()
                return
        if action is None:
            return
        if repeat and action not in ("up", "down", "left", "right"):
            return
        nav.act(action, device="kb")
        self.refresh()

    @Slot(str)
    def oskEdit(self, what):
        """paste / copy / cut / select_all in the on-screen keyboard's text (keys or its right-click menu)."""
        nav = self.nav
        if nav.overlay != "osk":
            return
        nav.device = "kb"
        if what == "paste":
            try:
                text = QGuiApplication.clipboard().text()
            except (AttributeError, RuntimeError):
                text = ""
            nav.paste_text(text)
        elif what in ("copy", "cut"):
            nav.osk_copy(cut=what == "cut")
        elif what == "select_all":
            nav.osk_select_all()
        self.refresh()

    @Slot(int, bool)
    def keyUp(self, key, repeat):
        if not repeat and KEYS.get(key) == "confirm":
            self.nav.release("confirm")
            self.refresh()

    @Slot(str)
    def press(self, action):
        self.nav.act(action, device="kb")
        if action == "confirm":
            self.nav.release("confirm")
        self.refresh()

    @Slot(int)
    def clickRow(self, i):
        self.nav.device = "kb"
        self.nav.click_row(i)
        self.refresh()

    @Slot(int)
    def clickTile(self, i):
        self.nav.device = "kb"
        self.nav.click_tile(i)
        self.refresh()

    @Slot(str)
    def clickTab(self, s):
        self.nav.device = "kb"
        self.nav.click_tab(s)
        self.refresh()

    @Slot()
    def clickPrimary(self):
        self.nav.device = "kb"
        self.nav.click_primary()
        self.refresh()

    @Slot(int)
    def clickCell(self, i):
        self.nav.device = "kb"
        self.nav.click_cell(i)
        self.refresh()

    @Slot(int)
    def clickEntry(self, i):
        self.nav.device = "kb"
        self.nav.click_entry(i)
        self.refresh()

    @Slot(int, int)
    def clickKey(self, r, c):
        self.nav.device = "kb"
        self.nav.click_key(r, c)
        self.refresh()


def make_engine(backend, full):
    # Windows supplies these CJK fonts; Qt falls back to them when a catalog needs them.
    for family in ("Big Shoulders", "IBM Plex Sans"):
        QFont.insertSubstitutions(family, ["Yu Gothic UI", "Malgun Gothic"])
    for name in os.listdir(os.path.join(UI_DIR, "fonts")):
        if name.lower().endswith(".ttf"):
            QFontDatabase.addApplicationFont(os.path.join(UI_DIR, "fonts", name))
    engine = QQmlApplicationEngine()
    engine.setInitialProperties({"backend": backend, "wantFull": full})
    engine.load(QUrl.fromLocalFile(os.path.join(UI_DIR, "Main.qml")))
    if not engine.rootObjects():
        raise RuntimeError("The interface could not be loaded.")
    backend.window = engine.rootObjects()[0]
    if isinstance(backend.window, QWindow):
        if full:
            backend.window.showFullScreen()
        else:
            backend.window.show()
    return engine


def main(argv=None):
    ap = argparse.ArgumentParser(prog="openrecomp-fgc", description="OpenRecomp-FGC: Launcher for all your Recomps")
    ap.add_argument("--windowed", action="store_true", help="in a window instead of fullscreen")
    args = ap.parse_args(argv)
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    app = QGuiApplication(sys.argv[:1])
    app.setApplicationName("OpenRecomp-FGC")
    icon = os.path.join(UI_DIR, "assets", "icon.ico")
    if os.path.isfile(icon):
        app.setWindowIcon(QIcon(icon))
    if os.name == "nt":      # the taskbar shows this program's icon, not python's
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TheWishin.OpenRecompFGC")
    backend = Backend(windowed=args.windowed)
    app.aboutToQuit.connect(backend.nav.close_online)
    engine = make_engine(backend, full=backend.nav.fullscreen)
    # A broken QML scene must never acknowledge an update. The old helper owns rollback.
    QTimer.singleShot(updater.CONFIRM_AFTER_MS, lambda: updater.confirm_startup(backend.updates.root))
    QTimer.singleShot(2000, backend._check_updates)
    code = app.exec()
    del engine
    return code
