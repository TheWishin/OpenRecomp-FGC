r"""Pictures of the Pad bindings page with fake controllers (no game, no device, nothing written):

    python tools\pad_bindings_shots.py <folder>

Every picture is drawn at 1920x1080 and 1280x720. Only the launcher's own screens are shown, so they may be
shared, but keep them out of the repository anyway.
"""
import os
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QUICK_BACKEND", "software")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "tests")]
_home = tempfile.mkdtemp(prefix="padshots-")      # never the player's own settings
for _name in ("OPENRECOMP_HOME", "APPDATA", "LOCALAPPDATA"):
    os.environ[_name] = _home

from pathlib import Path  # noqa: E402

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QFontDatabase, QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402

from openrecomp.app import UI_DIR  # noqa: E402
from openrecomp.nav import Game, Nav  # noqa: E402
from pad_fakes import PadsFake  # noqa: E402
from test_ui_loads import FakeBackend, spin  # noqa: E402


def main():
    folder = sys.argv[1]
    language = sys.argv[2] if len(sys.argv) > 2 else "en"
    os.makedirs(folder, exist_ok=True)
    app = QGuiApplication(sys.argv[:1])
    for font in (Path(UI_DIR) / "fonts").glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(font))
    adapter = PadsFake()
    nav = Nav([Game(adapter.m, adapter)], language=language)
    nav.screen = "hub"
    nav.game.accent = "#E5493A"          # the fake game's own accent is nearly black
    nav.sec[nav.game.id] = "controls"
    backend = FakeBackend(nav)
    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
    engine.setInitialProperties({"backend": backend, "wantFull": False})
    engine.load(QUrl.fromLocalFile(str(Path(UI_DIR) / "Main.qml")))
    win = engine.rootObjects()[0]
    win.setVisible(True)                 # offscreen: nothing appears on the screen

    def show():
        backend._v = nav.view()
        backend.viewChanged.emit()
        spin(80)

    def shot(name):
        show()
        for w, h in ((1920, 1080), (1280, 720)):
            win.resize(w, h)
            spin(120)
            win.grabWindow().save(os.path.join(folder, f"{name}_{h}p.png"))
        print(name)

    def press(*actions):
        for a in actions:
            nav.act(a, device="xbox")

    items = nav.items()
    first_slot = next(i for i, it in enumerate(items) if it.get("ctl") == "slot")
    nav.focus[nav.key()] = first_slot
    shot("01_xbox_actions")
    adapter.held["xinput:0"] = {"A", "B", "DDOWN", "DRIGHT"}
    shot("02_xbox_live_input")
    adapter.held = {}
    press("confirm")
    adapter.result = dict(state="waiting", left=3.4)
    nav.poll_tools()
    shot("03_capture_countdown")
    adapter.result = dict(state="conflict", source="Y", conflicts=["@controls.slot.2"],
                          swap=dict(slot="@controls.slot.2", sources=["X"]))
    nav.poll_tools()
    press("right")
    shot("04_conflict_swap")
    press("back")
    adapter.result = dict(state="waiting", left=5.0)
    press("chapterNext")
    nav.focus[nav.key()] = next(i for i, it in enumerate(nav.items()) if it.get("slot") == "1+2")
    adapter.binds["dinput:054C:0CE6"]["1+2"] = ["B8"]
    shot("05_dualsense_combos")
    nav.focus[nav.key()] = next(i for i, it in enumerate(nav.items()) if it.get("id") == "ctl:preset")
    press("confirm", "down", "down", "down")
    shot("06_presets")
    press("back")
    nav.focus[nav.key()] = next(i for i, it in enumerate(nav.items()) if it.get("id") == "ctl:socd")
    shot("07_socd")
    nav.focus[nav.key()] = next(i for i, it in enumerate(nav.items()) if it.get("id") == "ctl:test")
    press("confirm")
    adapter.result = dict(state="test")
    adapter.held["dinput:054C:0CE6"] = {"B1", "B4", "HAT_DOWN"}
    nav.poll_tools()
    shot("08_input_test")
    nav.act("back", device="kb")
    adapter.held = {}
    press("chapterNext")
    nav.focus[nav.key()] = next(i for i, it in enumerate(nav.items()) if it.get("slot") == "UP")
    shot("09_keyboard_directions")
    print("warnings:", warnings)
    del engine
    del app
    return 1 if warnings else 0


if __name__ == "__main__":
    sys.exit(main())
