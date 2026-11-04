"""The Qt side: one window, one QML scene, one Backend object between the scene and Nav."""
import argparse
import ctypes
import copy
import os
import queue
import sys
import threading

from PySide6.QtCore import QObject, QTimer, Property, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QAccessible, QAccessibleAnnouncementEvent, QFont, QFontDatabase, QGuiApplication, QIcon, QWindow
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow  # noqa: F401 -- so the scene's root comes back as a QQuickWindow

from . import adapters, file_dialog, i18n, manifest as mf, stall, ui_sound
from .nav import Game, Nav
from .pad import Pads, PlayStationReader, WinMMPlayStationReader, XInputReader
from .update_service import UpdateService
from . import updater
from .app_game_setup import GameSetupBackend
from .adapters import other_launchers

UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
KEYS = {Qt.Key_Up: "up", Qt.Key_Down: "down", Qt.Key_Left: "left", Qt.Key_Right: "right", Qt.Key_Return: "confirm", Qt.Key_Enter: "confirm",
        Qt.Key_Escape: "back", Qt.Key_Space: "play", Qt.Key_X: "x", Qt.Key_F: "social", Qt.Key_G: "switchGame", Qt.Key_Q: "prev", Qt.Key_E: "next",
        Qt.Key_PageUp: "chapterPrev", Qt.Key_PageDown: "chapterNext", Qt.Key_F8: "offers"}
KEYS = {int(k): v for k, v in KEYS.items()}   # by number: an unknown key (any layout's letter) is no ValueError
TICK_MS = 16
# Windows' CJK fonts first (unchanged order), then the Linux ones Wine/Proton list (make_engine)
CJK_FALLBACKS = ["Yu Gothic UI", "Malgun Gothic", "Noto Sans CJK JP", "Noto Sans CJK KR", "Source Han Sans",
                 "Noto Sans JP", "Noto Sans KR"]
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


def click(nav, action, method, *args):
    """A mouse click on nav: the same menu sound as the pad's press (nav_sound.Sound.sounded)."""
    if isinstance(nav, Nav):
        nav.sounded(action, getattr(nav, method), *args)
    else:
        getattr(nav, method)(*args)


def real_audio():
    """Menu sounds reach the speakers only in a real window: never offscreen (tests) or with OPENRECOMP_UI_SOUND=0."""
    if os.environ.get("OPENRECOMP_UI_SOUND") == "0" or QGuiApplication.instance() is None:
        return False
    try:
        return QGuiApplication.platformName() not in ("offscreen", "minimal")
    except RuntimeError:
        return False


def system_reduced_motion():
    """Read Windows' client-area animation preference; never change it."""
    if os.name != "nt":
        return False
    try:
        enabled = ctypes.c_int(1)
        return bool(ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)
                    and not enabled.value)
    except (AttributeError, OSError):
        return False


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
    from .playtime import shared_store

    manifests, problems = mf.load_all()
    games = [Game(m, adapters.make(m, config)) for m in manifests]
    # A manifest game with "shelf": "found" shows only on a PC that has it (games/tag2.json: no tile for everyone)
    games = [g for g in games if g.m.get("shelf") != "found" or g.a.found()]
    playtime_store = shared_store()
    for game in games:
        game.a.playtime_store = playtime_store
        # T4 Online may offer a T5DR remembered login (one account for both); each adapter decides what it reads.
        game.a.account_peers = tuple(other.a for other in games if other is not game)
    problems += [g.a.problem for g in games if g.a.problem]
    return games, problems


class Backend(QObject, GameSetupBackend):
    viewChanged = Signal()

    def __init__(self, launch_env=None, parent=None, windowed=False):
        super().__init__(parent)
        self.config = mf.load_config()
        self._library = None
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(200)
        self._save_timer.timeout.connect(self._flush_config)
        self._config_pending = False
        self._library_results = queue.Queue()
        self._library_work = None
        self._game_offers = {}
        self._game_updaters = {}
        games, problems = load_games(self.config)
        self._setup_init()
        self.choose_file = file_dialog.choose     # (owner, title, kind, filters, start) -> path; tests put a fake here
        self._native_queued = False
        self._native_open = False
        self.sounds = ui_sound.UiSounds(enabled=self.config.get("ui_sounds", ui_sound.DEFAULT_ON) is not False,
                                        volume=self.config.get("ui_sound_volume", ui_sound.DEFAULT_VOLUME),
                                        output=None if real_audio() else ui_sound.NullOutput())
        self.nav = Nav(games, on_quit=self._quit, install=self._install, launch_env=launch_env,
                       native_picker=native_picker_available(), picker_dirs=picker_dirs(self.config),
                       on_picker_dir=self._save_picker_dir,
                       online_prefs=self.config.get("online_prefs"), on_online_prefs=self._save_online_prefs,
                       language=self.config.get("language"), on_language=self._save_language,
                       last_game=self.config.get("last_game"), on_game=self._save_game,
                       fullscreen=self.config.get("fullscreen", True) and not windowed,
                       reduced_motion=self.config.get("reduced_motion", False), on_preferences=self._save_preferences,
                       text_size=self.config.get("text_size", 100), high_contrast=self.config.get("high_contrast", False),
                       on_accessibility=self._save_accessibility,
                       on_update_check=self._check_updates, on_update_install=self._install_update,
                       on_game_preview=self._preview_game, on_game_accept=self._accept_game,
                       on_game_remove=self._remove_game, on_game_update_check=self._check_game_update,
                       on_game_update_install=self._install_game_update,
                       ui_sounds=self.sounds.enabled, ui_sound_volume=self.sounds.volume, on_ui_sound=self._save_ui_sound,
                       **self._setup_kwargs())
        times = self.config.get("build_times")
        self.nav.build_history = {k: v for k, v in times.items() if isinstance(v, dict)} if isinstance(times, dict) else {}
        self.nav.on_build_history = self._save_build_history      # the Build page's "about N min left" next time
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
        self._system_reduced_motion = system_reduced_motion()
        self._slow = 0.0
        self._model_elapsed = 0.0
        wordmark = os.path.join(UI_DIR, "assets", "logo-wordmark.svg")
        self._wordmark = QUrl.fromLocalFile(wordmark).toString() if os.path.isfile(wordmark) else ""
        self.refresh()
        self.timer = QTimer(self)
        self.timer.setInterval(TICK_MS)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        self._background_timer = QTimer(self)
        self._background_timer.setInterval(250)
        self._background_timer.timeout.connect(self._background_tick)
        self.stall = stall.from_env()      # OPENRECOMP_STALL_LOG: log every time the window stood still
        if self.stall is not None:
            self._heart = QTimer(self)
            self._heart.setInterval(10)
            self._heart.timeout.connect(self.stall.beat)
            self._heart.start()

    @property
    def library(self):
        if self._library is None:
            from .game_library import Library
            self._library = Library(self.config)
        return self._library

    def _update_busy(self):
        if getattr(self, "_library_work", None) is not None:
            return True
        if getattr(self, "_setup_busy", lambda: False)():
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
        if getattr(self, "_save_timer", None) is not None and self._save_timer.isActive():
            self._flush_config()
        stores = {getattr(g.a, "playtime_store", None) for g in getattr(getattr(self, "nav", None), "games", [])}
        for store in stores - {None}:
            store.checkpoint()
        if self.window is not None:
            self.window.setProperty("allowClose", True)
        QGuiApplication.quit()

    def _check_updates(self):
        self.updates.check()

    def _auto_check_updates(self):
        """A few seconds after the start (with the games' check): an offer appears, nothing is said otherwise.
        While something else is busy (the games' own check started at the same moment, a build, an online
        session) it waits and runs once that is over (_poll_updates)."""
        if self.updates.state.get("phase") != "idle":
            self._auto_update_pending = False
        elif self._update_busy():
            self._auto_update_pending = True
        else:
            self._auto_update_pending = False
            self.updates.check(quiet=True)

    def _install_update(self):
        if not self.updates.install():
            self.nav.say("@updates.busy")

    def _poll_updates(self):
        if getattr(self, "_auto_update_pending", False):
            self._auto_check_updates()
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

    def _library_blocked(self):
        """A library job waits for builds, games, installs and searches; a lobby login alone does not (Nav.set_games
        keeps every unchanged game logged in)."""
        if getattr(self, "_setup_busy", lambda: False)():
            return True
        return not self.nav.can_reload_games()

    def _library_job(self, kind, operation, game_id=""):
        if self._library_work is not None or self._library_blocked():
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
        from .game_updates import GameUpdates
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
        timer = getattr(self, "_save_timer", None)
        if timer is not None:
            self._config_pending = True
            timer.start()
        else:
            Backend._flush_config(self)

    def _flush_config(self):
        timer = getattr(self, "_save_timer", None)
        if timer is not None:
            if not self._config_pending:
                return
            self._config_pending = False
            timer.stop()
        try:
            mf.save_config(self.config)
        except (OSError, ValueError):
            self.nav.say("@preferences.save_failed", 8)
            if timer is not None:
                self.refresh()

    def _save_language(self, language):
        self.config["language"] = language
        self._save_config()

    def _save_game(self, game_id):
        self.config["last_game"] = game_id
        self._save_config()

    def _save_build_history(self, game_id, history):
        times = self.config.get("build_times")
        self.config["build_times"] = dict(times if isinstance(times, dict) else {}, **{game_id: history})
        self._save_config()

    def _save_online_prefs(self, prefs):
        self.config["online_prefs"] = prefs
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

    def _save_accessibility(self, text_size, high_contrast):
        self.config.update(text_size=text_size, high_contrast=bool(high_contrast))
        self._save_config()

    def _save_ui_sound(self, on, volume):
        self.config.update(ui_sounds=bool(on), ui_sound_volume=ui_sound.clean_volume(volume))
        self.sounds.configure(on, volume)
        self._save_config()

    def _sound_active(self):
        """Menu sounds only while the player looks at the launcher: its window in front, no game running."""
        if any(g.a.running() for g in self.nav.games):
            return False
        if self.window is None:
            return True
        try:
            return bool(self.window.isActive()) and not self.window.windowState() & Qt.WindowMinimized
        except (AttributeError, RuntimeError):
            return False

    def _play_sound(self):
        name = self.nav.take_sound()
        try:
            active = Backend._sound_active(self)
            game = getattr(self.nav, "game", None)
            self.sounds.set_theme(game.m.get("adapter", "") if game is not None else "")
            self.sounds.play(name, active=active)
        except Exception:  # noqa: BLE001 -- a sound never breaks the screen
            pass

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
        if getattr(self.nav, "pending_url", None):
            self._open_pending()
        if getattr(self.nav, "pending_native", None) is not None:
            self._queue_native()
        if getattr(self, "sounds", None) is not None:
            Backend._play_sound(self)
        previous = getattr(self, "_view", None)
        self.nav.system_reduced_motion = getattr(self, "_system_reduced_motion", False)
        self._view = self.nav.view()
        self._view["gameRunning"] = any(g.a.running() for g in getattr(self.nav, "games", []))
        if getattr(self.nav, "pending_attention", False):
            self.nav.pending_attention = False
            Backend._offer_attention(self)
        if not hasattr(self, "_wordmark"):
            wordmark = os.path.join(UI_DIR, "assets", "logo-wordmark.svg")
            self._wordmark = QUrl.fromLocalFile(wordmark).toString() if os.path.isfile(wordmark) else ""
        self._view["wordmark"] = self._wordmark
        if self._view != previous:
            self.viewChanged.emit()
            Backend._announce_view(self, previous)

    def _offer_attention(self):
        """Flash an inactive launcher; the game keeps OS focus and its own notification panel."""
        window = getattr(self, "window", None)
        if window is None or any(g.a.running() for g in self.nav.games):
            return
        try:
            if not window.isActive():
                window.alert(0)
        except (AttributeError, RuntimeError):
            pass

    def _announce_view(self, previous):
        """One polite announcement for a result or phase; elapsed clocks and selection never speak."""
        window = getattr(self, "window", None)
        if window is None or not QAccessible.isActive():
            return
        before = previous or {}
        current = self._view
        message = current.get("toast") if current.get("toast") != before.get("toast") else ""
        online, old_online = current.get("online") or {}, before.get("online") or {}
        if not message and before and online.get("phase") and online.get("phase") != old_online.get("phase"):
            message = online.get("message") or (online.get("find") or {}).get("message") or online.get("title")
        if not message and online.get("phase") in ("error", "kicked", "result", "result_sent") and online.get("message") != old_online.get("message"):
            message = online.get("message")
        if not message:
            offers = current.get("globalOffers") or []
            old_ids = {row.get("identity") for row in before.get("globalOffers") or []}
            incoming_offer = next((row for row in offers if row.get("identity") not in old_ids), None)
            if incoming_offer:
                message = ". ".join(str(incoming_offer.get(key) or "") for key in ("title", "name", "rank"))
        if not message:
            incoming = (online.get("find") or {}).get("incoming") or {}
            old_incoming = (old_online.get("find") or {}).get("incoming") or {}
            if incoming.get("text") != old_incoming.get("text"):
                message = incoming.get("text")
        if not isinstance(message, str) or not message.strip():
            return
        event = QAccessibleAnnouncementEvent(window, message)
        event.setPoliteness(QAccessible.AnnouncementPoliteness.Polite)
        QAccessible.updateAccessibility(event)

    def _open_pending(self):
        """nav.pending_url (the OpenRecomp-FGC Discord) in the default browser."""
        url = getattr(self.nav, "pending_url", None)
        if not url:
            return
        self.nav.pending_url = None
        self.opened_urls = getattr(self, "opened_urls", []) + [url]      # (tests read it)
        if QGuiApplication.platformName() in ("offscreen", "minimal"):
            return                              # tests: never a real browser
        try:
            from PySide6.QtGui import QDesktopServices
            opened = QDesktopServices.openUrl(QUrl(url))
        except (ImportError, AttributeError, RuntimeError):
            opened = False
        if not opened:
            self.nav.say(i18n.message("community.open_failed", url=i18n.literal(url)), 10)

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
        if self.window is None:
            return True
        if getattr(self, "_input_active", None) is not None:
            return self._input_active
        return (self.window.isVisible() and not self.window.windowState() & Qt.WindowMinimized
                and (self.window.isActive() or os.environ.get("OPENRECOMP_PAD_ALWAYS") == "1"))

    def _sync_timers(self):
        running = any(g.a.running() for g in self.nav.games)
        return_pad = any(g.m.get("adapter") == "t4" and g.a.running() for g in self.nav.games)
        visible = self.window is None or (self.window.isVisible() and not self.window.windowState() & Qt.WindowMinimized)
        self._input_active = visible and (self.window is None or self.window.isActive()
                                         or os.environ.get("OPENRECOMP_PAD_ALWAYS") == "1")
        if (not visible or running or self.window is not None and not self.window.isActive()) and getattr(self, "sounds", None):
            self.sounds.silence()
        foreground = return_pad or visible and not running
        self.timer.start() if foreground else self.timer.stop()
        self._background_timer.stop() if foreground else self._background_timer.start()

    def _background_tick(self):
        self._tick(0.25)
        self._sync_timers()

    def _tick(self, dt=None):
        dt = TICK_MS / 1000.0 if dt is None else dt
        running = any(g.a.running() for g in self.nav.games)
        if any(g.m.get("adapter") == "t4" and g.a.running() for g in self.nav.games):
            if self.pads.return_requested(dt):
                self.nav.act("returnGame", device=self.pads.kind)
        else:
            self.pads.reset_return()
        active = self._in_front() and not running
        if not active:
            self.nav.release("confirm")
        elapsed = getattr(self, "_model_elapsed", 0.1) + dt
        fast = bool(getattr(self.nav, "holding", None) or getattr(self.nav, "toast", ""))
        changed = False
        if elapsed >= 0.1 or fast:
            self._model_elapsed = 0.0
            changed = self.nav.tick(elapsed)
            changed = self._poll_updates() or changed
            if hasattr(self, "_poll_setup"):
                changed = self._poll_setup(elapsed) or changed
            if hasattr(self, "_poll_library"):
                changed = self._poll_library() or changed
        else:
            self._model_elapsed = elapsed
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
        reduced_motion = system_reduced_motion()
        if reduced_motion != getattr(self, "_system_reduced_motion", False):
            self._system_reduced_motion = reduced_motion
            changed = True
        from .living_background import background_view
        game = getattr(self.nav, "game", None)
        if getattr(self.nav, "screen", "") == "start":
            ids = self.nav.tile_ids()
            game = self.nav.game_by_id(ids[min(self.nav.start_focus, len(ids) - 1)])
        scene = background_view(game.a, game.m.get("adapter", ""),
                                reduced_motion=getattr(self.nav, "reduced_motion", False) or reduced_motion) if game else {}
        if scene != getattr(self, "_view", {}).get("livingBackground", {}):
            changed = True
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
            if getattr(g.a, "config_dirty", False):       # a verified ISO, a build to continue after a restart
                g.a.config_dirty = False
                self._save_config()
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
            playtime = getattr(g.a, "playtime", None)
            if playtime is not None:
                cache = self.__dict__.setdefault("_last_playtime", {})
                snapshot = playtime()
                snapshot = {**snapshot, **{key: int(snapshot.get(key, 0) // 60)
                                          for key in ("offline_seconds", "online_seconds")}}
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
        if getattr(nav, "native_edit", ""):
            return                    # QML TextInput owns every physical key while focused, including IME preedit.
        if nav.overlay == "osk":
            if key in (Qt.Key_Return, Qt.Key_Enter):
                if not repeat:
                    nav.act("play", device="kb")
                    self.refresh()
                return
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
    def beginEdit(self, tid):
        self.nav.begin_edit(tid)
        self.refresh()

    @Slot(str, str)
    def editText(self, tid, text):
        self.nav.edit_text(tid, text)
        self.refresh()

    @Slot(str, bool)
    def finishEdit(self, tid, submit):
        self.nav.finish_edit(tid, submit)
        self.refresh()

    @Slot(str)
    def challengePlayer(self, player_id):
        self.nav.finish_edit(getattr(self.nav, "native_edit", ""))
        self.nav.device = "kb"
        self.nav.challenge_player(player_id)
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

    @Slot(str, bool)
    def respondOffer(self, identity, accept):
        from . import nav_feedback
        nav_feedback.click_global(self.nav, identity, accept)
        self.refresh()

    @Slot(int)
    def clickRow(self, i):
        self.nav.finish_edit(getattr(self.nav, "native_edit", ""))
        self.nav.device = "kb"
        click(self.nav, "confirm", "click_row", i)
        self.refresh()

    @Slot(int)
    def clickMainEntry(self, i):
        self.nav.finish_edit(getattr(self.nav, "native_edit", ""))
        self.nav.device = "kb"
        click(self.nav, "confirm", "click_main_entry", i)
        self.refresh()

    @Slot(str)
    def selectSettingsTab(self, tab):
        self.nav.device = "kb"
        self.nav.select_settings_tab(tab)
        self.refresh()

    @Slot(int)
    def focusOnlineRow(self, i):
        self.nav.finish_edit(getattr(self.nav, "native_edit", ""))
        self.nav.device = "kb"
        self.nav.focus_online_row(i)
        self.refresh()

    @Slot(int, int)
    def selectOnlineOption(self, i, option):
        self.nav.device = "kb"
        self.nav.select_online_option(i, option)
        self.refresh()

    @Slot(int)
    def clickTile(self, i):
        self.nav.device = "kb"
        click(self.nav, "confirm", "click_tile", i)
        self.refresh()

    @Slot(str)
    def clickTab(self, s):
        self.nav.finish_edit(getattr(self.nav, "native_edit", ""))
        self.nav.device = "kb"
        click(self.nav, ui_sound.CLICK_TAB, "click_tab", s)
        self.refresh()

    @Slot(str)
    def clickChapter(self, chapter):
        self.nav.finish_edit(getattr(self.nav, "native_edit", ""))
        self.nav.device = "kb"
        click(self.nav, ui_sound.CLICK_TAB, "click_chapter", chapter)
        self.refresh()

    @Slot()
    def clickPrimary(self):
        self.nav.device = "kb"
        click(self.nav, "confirm", "click_primary")
        self.refresh()

    @Slot(int)
    def clickCell(self, i):
        self.nav.device = "kb"
        click(self.nav, "confirm", "click_cell", i)
        self.refresh()

    @Slot(int)
    def clickEntry(self, i):
        self.nav.device = "kb"
        click(self.nav, "confirm", "click_entry", i)
        self.refresh()

    @Slot(int, int)
    def clickKey(self, r, c):
        self.nav.device = "kb"
        click(self.nav, "confirm", "click_key", r, c)
        self.refresh()


def make_engine(backend, full):
    # Windows supplies these CJK fonts; Qt falls back to them when a catalog needs them. Under Wine/Proton (Linux,
    # Steam Deck) there are none of them: Wine lists the Linux fonts instead, where Noto Sans CJK / Source Han Sans
    # carry the glyphs (SteamOS ships Noto). Families a PC does not have are skipped, so Windows is unchanged.
    for family in ("Big Shoulders", "IBM Plex Sans"):
        QFont.insertSubstitutions(family, CJK_FALLBACKS)
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
        backend.window.visibilityChanged.connect(backend._sync_timers)
        backend.window.activeChanged.connect(backend._sync_timers)
        backend._sync_timers()
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
    # Another launcher of the same game (its own launcher, another OpenRecomp window): the Online note (one at a time)
    other_launchers.enable()
    backend = Backend(windowed=args.windowed)
    app.aboutToQuit.connect(backend.nav.close_online)
    app.aboutToQuit.connect(other_launchers.DETECTOR.disable)
    app.aboutToQuit.connect(backend._shutdown_setup)      # an install/update stops or finishes before the exit
    app.aboutToQuit.connect(backend._flush_config)
    app.aboutToQuit.connect(backend.sounds.close)
    engine = make_engine(backend, full=backend.nav.fullscreen)
    # A broken QML scene must never acknowledge an update. The old helper owns rollback.
    QTimer.singleShot(updater.CONFIRM_AFTER_MS, lambda: updater.confirm_startup(backend.updates.root))
    # The launcher's own update check runs with the game checks a few seconds after the start (quiet unless an
    # update is there: app_game_setup._poll_setup -> _auto_check_updates), never here.
    code = app.exec()
    del engine
    return code
