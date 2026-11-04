"""Render T4's shared online screens with synthetic data only, without install discovery.

    python tools/t4_flow_shots.py [build/shots/t4flow] [--languages en de ...]

No game adapter, player art, saved login, physical input, updater or network is loaded.
The output stays in this repository's ignored build folder by default.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QUICK_BACKEND"] = "software"
os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"
os.environ["QML_DISABLE_DISK_CACHE"] = "1"
os.environ["OPENRECOMP_UI_SOUND"] = "0"
os.environ["OPENRECOMP_HOME"] = str(ROOT / "build" / "tmp-home" / "t4flow-shots")
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QObject, Property, QEventLoop, QTimer, Signal, Slot  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from openrecomp import i18n  # noqa: E402
from openrecomp.adapters.base import Adapter  # noqa: E402
from openrecomp.app import make_engine  # noqa: E402
from openrecomp.nav import Game, Nav  # noqa: E402


class SyntheticT4(Adapter):
    def __init__(self):
        manifest = json.loads((ROOT / "games" / "t4.json").read_text(encoding="utf-8"))
        super().__init__(manifest)
        self.state = {}

    def found(self):
        return True

    def ready(self):
        return True

    def status(self):
        return dict(status="@ready", version="Synthetic fixture", players="@section.online", last="@never",
                    detail="@t4.ready_detail")

    def online_supported(self):
        return True

    def online_state(self):
        return copy.deepcopy(self.state)

    def text_value(self, tid):
        return {"online_name": "Player A", "online_server": ""}.get(tid, "")

    def online_action(self, action):
        raise AssertionError("Screenshot fixtures never request online actions")


class ShotBackend(QObject):
    viewChanged = Signal()

    def __init__(self, nav):
        super().__init__()
        self.nav = nav
        self.window = None
        self._view = nav.view()

    @Property("QVariant", notify=viewChanged)
    def view(self):
        return self._view

    def refresh(self):
        self._view = self.nav.view()
        self.viewChanged.emit()

    def _sync_timers(self, *_args):
        pass

    @Slot(int, str, bool, int, int)
    def keyPress(self, *_args):
        pass

    @Slot(int, bool)
    def keyUp(self, *_args):
        pass

    @Slot(str)
    def press(self, *_args):
        pass

    @Slot(str)
    def oskEdit(self, *_args):
        pass

    @Slot(int)
    def clickRow(self, *_args):
        pass

    @Slot(int)
    def clickTile(self, *_args):
        pass

    @Slot(str)
    def clickTab(self, *_args):
        pass

    @Slot()
    def clickPrimary(self):
        pass

    @Slot(int)
    def clickCell(self, *_args):
        pass

    @Slot(int)
    def clickEntry(self, *_args):
        pass

    @Slot(int, int)
    def clickKey(self, *_args):
        pass

    @Slot()
    def requestQuit(self):
        pass


def spin(milliseconds=100):
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def lobby_state():
    return dict(phase="logged_in", message="@online.logged_in", name="Player A", account=True,
                secure=True, server_ping=28, rank="1st dan", match={},
                capabilities=dict(t4_lobby=True, lobby=True, ranked=True, rooms=True,
                                  match_flow=True, rematch=True),
                me=dict(name="Player A", rank="1st dan", tier=0, rating=1500, record=[12, 8, 0]),
                players=[dict(id="b", name="Player B", rank="2nd dan", rating=1600, record=[16, 10, 0],
                              status="idle", ping=34, ping_measured=True, ping_path="direct"),
                         dict(id="c", name="Player C", guest=True, status="idle", ping=55,
                              ping_measured=True, ping_path="relay")],
                rooms=[dict(id="practice", name="Practice room", host="Player C", players=1)],
                chat=[dict(name="Player B", text="Ready for a set?"),
                      dict(name="Player A", text="Yes, send a challenge.")])


def render(folder, languages):
    folder = folder.resolve()
    if not folder.is_relative_to(ROOT / "build"):
        raise ValueError("Synthetic screenshots must stay under this repository's ignored build folder")
    folder.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    adapter = SyntheticT4()
    adapter.state = lobby_state()
    nav = Nav([Game(adapter.m, adapter)], language="en", fullscreen=False, reduced_motion=True)
    nav.screen = "hub"
    nav.sec["t4"] = "online"
    backend = ShotBackend(nav)
    engine = make_engine(backend, full=False)
    warnings = []
    engine.warnings.connect(lambda messages: warnings.extend(message.toString() for message in messages))
    captures = []
    try:
        for language in languages:
            nav.language = language
            for screen in ("login", "lobby", "challenge", "match_found", "result"):
                adapter.state = lobby_state()
                nav.overlay = None
                nav.online_challenge = None
                nav.online_challenge_seen = {}
                nav.focus["t4:online"] = 0
                if screen == "login":
                    adapter.state.update(phase="offline", message="@t4.online_setup_hint", account=False)
                elif screen == "challenge":
                    adapter.state["challenge"] = dict(id="synthetic-challenge", name="Player B", ping=34,
                                                      ping_measured=True, ping_path="direct")
                    nav.tick(0)
                    if nav.overlay != "dialog" or nav.confirm_kind != "online_challenge":
                        raise AssertionError("The shared challenge popup did not open")
                elif screen in ("match_found", "result"):
                    adapter.state.update(phase="matched" if screen == "match_found" else "result_sent",
                                         message="@online.t4_matched" if screen == "match_found"
                                         else "@online.result_confirmed",
                                         match=dict(opponent="Player B", ping=34, ping_measured=True,
                                                    ping_path="direct", sides=[
                                                        dict(name="Player A", rank="1st dan", you=True),
                                                        dict(name="Player B", rank="2nd dan", you=False)]))
                    if screen == "result":
                        adapter.state["result"] = dict(winner=0, score=[2, 1], slot=0, source="game")
                backend.refresh()
                spin(180)
                image = backend.window.grabWindow()
                name = language + "_" + screen + ".png"
                if image.isNull() or not image.save(str(folder / name)):
                    raise AssertionError("The synthetic screenshot could not be saved: " + name)
                captures.append(name)
        if warnings:
            raise AssertionError("QML warnings: " + "\n".join(warnings))
        return captures
    finally:
        backend.window.setProperty("allowClose", True)
        backend.window.close()
        engine.deleteLater()
        spin(10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", nargs="?", type=Path, default=ROOT / "build" / "shots" / "t4flow")
    parser.add_argument("--languages", nargs="+", choices=tuple(i18n.LANGUAGES), default=list(i18n.LANGUAGES))
    args = parser.parse_args()
    captures = render(args.folder, args.languages)
    print(json.dumps(dict(synthetic=True, captures=captures)))


if __name__ == "__main__":
    main()
