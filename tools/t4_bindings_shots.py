r"""Pictures of the Tekken 4 Pad bindings page (real T4 adapter, fake pads, a temporary controls.ini):

    python tools	4_bindings_shots.py <folder> [language]

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
from test_nav import manifest  # noqa: E402
from test_t4_controls import T4Editable  # noqa: E402
from test_ui_loads import FakeBackend, spin  # noqa: E402


def main():
    folder = sys.argv[1]
    language = sys.argv[2] if len(sys.argv) > 2 else "en"
    os.makedirs(folder, exist_ok=True)
    app = QGuiApplication(sys.argv[:1])
    for font in (Path(UI_DIR) / "fonts").glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(font))
    tmp = tempfile.mkdtemp(prefix="t4shots-")
    adapter = T4Editable(tmp)
    nav = Nav([Game(manifest(), adapter)], language=language)
    nav.screen = "hub"
    nav.game.accent = "#E5493A"
    nav.sec[nav.game.id] = "controls"
    backend = FakeBackend(nav)
    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
    engine.setInitialProperties({"backend": backend, "wantFull": False})
    engine.load(QUrl.fromLocalFile(str(Path(UI_DIR) / "Main.qml")))
    win = engine.rootObjects()[0]
    win.setVisible(True)

    def shot(name):
        backend._v = nav.view()
        backend.viewChanged.emit()
        spin(80)
        for w, h in ((1920, 1080), (1280, 720)):
            win.resize(w, h)
            spin(120)
            win.grabWindow().save(os.path.join(folder, f"{name}_{language}_{h}p.png"))
        print(name)

    def focus(**match):
        nav.focus[nav.key()] = next(i for i, it in enumerate(nav.items())
                                    if all(it.get(k) == v for k, v in match.items()))

    nav._ctl_select(nav.game, "t4:xinput:0")
    focus(slot="1")
    shot("01_pad_xbox")
    adapter.reader.pads[0] = {"X", "A", "DDOWN", "DRIGHT"}
    shot("02_pad_live_input")
    adapter.reader.pads[0] = {}
    adapter.apply_preset("t4:xinput:0", "t4_combos")
    focus(slot="1+2")
    shot("03_pad_combos_preset")
    adapter.reader.pads[0] = {"RB"}
    shot("04_combo_live")
    adapter.reader.pads[0] = {}
    nav.prompt_style = "ps"
    focus(slot="3")
    shot("05_pad_playstation_prompts")
    nav.prompt_style = "auto"
    nav._ctl_select(nav.game, "t4:keyboard")
    adapter.apply_preset("t4:keyboard", "t4_combos")
    focus(slot="3+4")
    shot("06_keyboard_keycaps")
    nav._ctl_select(nav.game, "t4:player:2")
    focus(slot="1")
    shot("07_player2_tab")
    print("warnings:", warnings)
    del engine
    del app
    return 1 if warnings else 0


if __name__ == "__main__":
    sys.exit(main())
