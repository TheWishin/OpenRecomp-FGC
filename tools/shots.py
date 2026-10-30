r"""Drive the real screens without showing a window and save a picture of each state.

    python tools\\shots.py <folder> [start|hub|all]

The pictures can show art from the player's own games: keep them out of the repository.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QEventLoop, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from openrecomp.app import Backend, make_engine  # noqa: E402

SCRIPT = [
    ("01_shelf_t5", []),
    ("02_shelf_t4", ["right"]),
    ("03_shelf_slot", ["right"]),
    ("04_shelf_slot_last", ["right", "right", "right"]),
    ("05_hub_t4_play", ["left", "left", "left", "left", "confirm"]),
    ("06_hub_t4_build", ["next"]),
    ("07_hub_t4_settings", ["next"]),
    ("08_hub_t5_play", ["switchGame"]),
    ("09_t5_online", ["next"]),
    ("10_t5_fighters", ["confirm"]),
    ("11_t5_fighters_moved", ["right", "right", "down"]),
    ("12_t5_build", ["back", "next"]),
    ("13_t5_replays", ["next"]),
    ("14_t5_replay_shown", ["down", "x"]),
    ("15_t5_settings", ["next"]),
    ("16_drawer", ["social"]),
    ("17_picker", ["back", "prev", "prev", "confirm"]),
    ("18_osk", ["back", "prev"]),
    ("19_exit", ["back", "back"]),
]


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def main():
    folder = sys.argv[1]
    os.makedirs(folder, exist_ok=True)
    app = QGuiApplication(sys.argv[:1])
    backend = Backend()
    backend.nav.dry = True           # this tool never starts, opens or writes anything
    engine = make_engine(backend, full=False)
    win = backend.window
    win.setFlag(Qt.WindowDoesNotAcceptFocus)     # a real window must not take the keyboard from a running game
    wait(1500)
    for name, actions in SCRIPT:
        for a in actions:
            backend.press(a)
        wait(450)
        path = os.path.join(folder, name + ".png")
        win.grabWindow().save(path)
        print(name, backend.nav.screen, backend.nav.overlay, backend.nav.section() if backend.nav.screen == "hub" else "")
    del engine
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main())
