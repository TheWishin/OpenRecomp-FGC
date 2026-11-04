"""Missing VS pictures stay compact while player identities remain prominent."""
import os
import subprocess
import sys
import unittest


class FighterFallback(unittest.TestCase):
    def test_vs_outline_is_bounded_and_real_images_keep_their_aspect_ratio(self):
        script = '''
from pathlib import Path
import sys
sys.path.insert(0, str(Path("tests").resolve()))
from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression, qmlContext
from tools.online_shots import scene, snapshot
from test_ui_loads import FakeBackend, spin, wait_pages
app = QGuiApplication([])
backend = FakeBackend(scene("t5", "matched", "en"))
backend._v = snapshot(backend.nav)
engine = QQmlApplicationEngine()
warnings = []
engine.warnings.connect(lambda messages: warnings.extend(m.toString() for m in messages))
engine.setInitialProperties(dict(backend=backend, wantFull=False))
engine.load(QUrl.fromLocalFile(str(Path("openrecomp/ui/Main.qml").resolve())))
assert engine.rootObjects(), warnings
window = engine.rootObjects()[0]
window.show()
wait_pages(window)
spin(50)
def descendants(item):
    for child in item.childItems():
        yield child
        yield from descendants(child)
def named(name):
    return [item for item in descendants(window.contentItem())
            if item.objectName() == name and item.isVisible()]
portraits = named("versusPortrait")
assert len(portraits) == 2
for portrait in portraits:
    outline = next(item for item in descendants(portrait) if item.objectName() == "fighterFallback")
    assert outline.isVisible()
    assert outline.width() <= min(108, portrait.width() * .34) + .01
    assert outline.height() <= portrait.height() * .58
    assert outline.opacity() <= .5
    assert outline.x() >= 0 and outline.y() >= 0
    assert abs(outline.x() + outline.width() / 2 - portrait.width() / 2) <= .51
assert all(item.property("font").pixelSize() >= 40 for item in named("versusPlayerName")), [(item.property("font").pixelSize()) for item in named("versusPlayerName")]
assert all(item.property("font").pixelSize() >= 30 for item in named("versusPlayerRank")), [(item.property("font").pixelSize()) for item in named("versusPlayerRank")]
# A synthetic rectangle checks showcase scaling and compact native-size limits.
import tempfile
with tempfile.TemporaryDirectory(dir="build") as directory:
    path = Path(directory) / "portrait.png"
    image = QImage(128, 64, QImage.Format_ARGB32)
    image.fill(0xffaabbcc)
    assert image.save(str(path))
    source = QUrl.fromLocalFile(str(path.resolve()))
    for portrait in portraits:
        portrait.setProperty("source", source)
    spin(100)
    for portrait in portraits:
        outline = next(item for item in descendants(portrait) if item.objectName() == "fighterFallback")
        picture = next(item for item in descendants(portrait) if item.objectName() == "fighterPicture")
        assert not outline.isVisible()
        assert picture.isVisible()
        assert QQmlExpression(qmlContext(picture), picture, "fillMode === 2").evaluate()[0]  # PreserveAspectCrop
        assert picture.width() == portrait.width() and picture.height() == portrait.height()
        assert picture.width() > 128
        assert abs(picture.property("paintedWidth") / picture.property("paintedHeight") - 2) < .001
        assert picture.property("paintedWidth") >= picture.width() - .01
        assert picture.property("paintedHeight") >= picture.height() - .01
        portrait.setProperty("showcase", False)
    spin(20)
    for portrait in portraits:
        picture = next(item for item in descendants(portrait) if item.objectName() == "fighterPicture")
        assert picture.width() == 128 and picture.height() == 64
        assert QQmlExpression(qmlContext(picture), picture, "fillMode === 1").evaluate()[0]  # PreserveAspectFit
assert not warnings, warnings
window.setProperty("allowClose", True)
window.close()
'''
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QML_DISABLE_DISK_CACHE="1")
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=30, env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
