"""The Qt side: one window, one QML scene, one Backend object between the scene and Nav."""
import argparse
import ctypes
import os
import sys

from PySide6.QtCore import QObject, QTimer, Property, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QFontDatabase, QGuiApplication, QIcon, QWindow
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow  # noqa: F401 -- so the scene's root comes back as a QQuickWindow

from . import adapters, manifest as mf
from .nav import Game, Nav
from .pad import Pads, PlayStationReader, XInputReader

UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
KEYS = {Qt.Key_Up: "up", Qt.Key_Down: "down", Qt.Key_Left: "left", Qt.Key_Right: "right", Qt.Key_Return: "confirm", Qt.Key_Enter: "confirm",
        Qt.Key_Escape: "back", Qt.Key_Space: "play", Qt.Key_X: "x", Qt.Key_F: "social", Qt.Key_G: "switchGame", Qt.Key_Q: "prev", Qt.Key_E: "next"}
TICK_MS = 16


def load_games(config):
    manifests, problems = mf.load_all()
    games = [Game(m, adapters.make(m, config)) for m in manifests]
    problems += [g.a.problem for g in games if g.a.problem]
    return games, problems


class Backend(QObject):
    viewChanged = Signal()

    def __init__(self, launch_env=None, parent=None):
        super().__init__(parent)
        self.config = mf.load_config()
        games, problems = load_games(self.config)
        self.nav = Nav(games, on_quit=QGuiApplication.quit, install=self._install, launch_env=launch_env)
        if problems:
            self.nav.say(problems[0], 8)
        t5 = next((g.a for g in games if g.id == "t5dr" and g.a.found()), None)
        readers = [XInputReader()]
        if t5 is not None:
            readers.append(PlayStationReader(t5.root))
        self.pads = Pads(readers)
        self.window = None
        self._view = {}
        self._was_running = False
        self._was_building = False
        self._last_hero = {}
        self._slow = 0.0
        self.refresh()
        self.timer = QTimer(self)
        self.timer.setInterval(TICK_MS)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    def _install(self, path):
        """path = a player's manifest; None = a game's folder was chosen. Both: load the games again."""
        message = ""
        if path:
            try:
                m = mf.install(path)
                message = f"{m['title']} ist jetzt auf dem Launcher."
            except mf.ManifestError as e:
                return str(e)
        else:
            mf.save_config(self.config)
            message = "Spielordner gespeichert."
        games, problems = load_games(self.config)
        self.nav.set_games(games)
        return problems[0] if problems else message

    @Property("QVariant", notify=viewChanged)
    def view(self):
        return self._view

    def refresh(self):
        self._view = self.nav.view()
        self.viewChanged.emit()

    def _in_front(self):
        return self.window is None or self.window.isActive() or os.environ.get("OPENRECOMP_PAD_ALWAYS") == "1"

    def _tick(self):
        dt = TICK_MS / 1000.0
        changed = self.nav.tick(dt)
        running = any(g.a.running() for g in self.nav.games)
        if self._in_front() and not running:
            for action, edge in self.pads.poll():
                self.nav.pad_kind = self.pads.kind
                changed = True
                if edge == "down":
                    self.nav.act(action, device=self.pads.kind)
                else:
                    self.nav.release(action)
        else:
            self.pads.forget()
        self._slow += dt
        if self._slow >= 0.5:                 # game ended, build moved on, a picture got ready
            self._slow = 0.0
            changed = changed or self._slow_changes(running)
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
        for g in self.nav.games:
            hero = g.a.hero()
            if hero != self._last_hero.get(g.id):
                self._last_hero[g.id] = hero
                changed = True
        return changed

    # ---------------------------------------------------------------- from the scene
    @Slot(int, str, bool)
    def keyDown(self, key, text, repeat):
        action = KEYS.get(Qt.Key(key))
        nav = self.nav
        if nav.overlay == "osk":
            if key == Qt.Key_Backspace:
                nav.act("x", device="kb")
                self.refresh()
                return
            if text and text.isprintable() and key not in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
                nav.type_text(text.upper())
                self.refresh()
                return
        if action is None:
            return
        if repeat and action not in ("up", "down", "left", "right"):
            return
        nav.act(action, device="kb")
        self.refresh()

    @Slot(int, bool)
    def keyUp(self, key, repeat):
        if not repeat and KEYS.get(Qt.Key(key)) == "confirm":
            self.nav.release("confirm")
            self.refresh()

    @Slot(str)
    def press(self, action):
        self.nav.act(action)
        if action == "confirm":
            self.nav.release("confirm")
        self.refresh()

    @Slot(int)
    def clickRow(self, i):
        self.nav.click_row(i)
        self.refresh()

    @Slot(int)
    def clickTile(self, i):
        self.nav.click_tile(i)
        self.refresh()

    @Slot(str)
    def clickTab(self, s):
        self.nav.click_tab(s)
        self.refresh()

    @Slot()
    def clickPrimary(self):
        self.nav.click_primary()
        self.refresh()

    @Slot(int)
    def clickCell(self, i):
        self.nav.click_cell(i)
        self.refresh()

    @Slot(int)
    def clickEntry(self, i):
        self.nav.click_entry(i)
        self.refresh()

    @Slot(int, int)
    def clickKey(self, r, c):
        self.nav.click_key(r, c)
        self.refresh()


def make_engine(backend, full):
    for name in os.listdir(os.path.join(UI_DIR, "fonts")):
        if name.lower().endswith(".ttf"):
            QFontDatabase.addApplicationFont(os.path.join(UI_DIR, "fonts", name))
    engine = QQmlApplicationEngine()
    engine.setInitialProperties({"backend": backend, "wantFull": full})
    engine.load(QUrl.fromLocalFile(os.path.join(UI_DIR, "Main.qml")))
    if not engine.rootObjects():
        raise RuntimeError("Die Oberfläche liess sich nicht laden.")
    backend.window = engine.rootObjects()[0]
    if isinstance(backend.window, QWindow):
        if full:
            backend.window.showFullScreen()
        else:
            backend.window.show()
    return engine


def main(argv=None):
    ap = argparse.ArgumentParser(prog="openrecomp-fgc", description="OpenRecomp-FGC: Launcher for all your Recomps")
    ap.add_argument("--windowed", action="store_true", help="in einem Fenster statt im Vollbild")
    args = ap.parse_args(argv)
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    app = QGuiApplication(sys.argv[:1])
    app.setApplicationName("OpenRecomp-FGC")
    app.setWindowIcon(QIcon(os.path.join(UI_DIR, "assets", "icon.ico")))
    if os.name == "nt":      # the taskbar shows this program's icon, not python's
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TheWishin.OpenRecompFGC")
    backend = Backend()
    engine = make_engine(backend, full=not args.windowed)
    code = app.exec()
    del engine
    return code
