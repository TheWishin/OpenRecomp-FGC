"""Source bundle bridge checks with mocks and an invisible, image-free QML scene."""
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from openrecomp import app
from openrecomp.adapters.base import Adapter
from openrecomp.nav import Game, Nav
from test_nav import Fake, manifest
from test_ui_loads import FakeBackend, spin


class BundleBridge(unittest.TestCase):
    def test_copy_request_reaches_clipboard_exactly_once(self):
        command = 'winget install --id Microsoft.VisualStudio.2022.BuildTools --exact --override "--wait --passive"'
        backend = SimpleNamespace(nav=SimpleNamespace(pending_clipboard=command, say=mock.Mock()))
        clipboard = mock.Mock()
        with mock.patch.object(app.QGuiApplication, "clipboard", return_value=clipboard):
            app.Backend._copy_pending(backend)
            app.Backend._copy_pending(backend)
        clipboard.setText.assert_called_once_with(command)
        self.assertIsNone(backend.nav.pending_clipboard)
        backend.nav.say.assert_not_called()

    def test_unavailable_clipboard_leaves_navigation_usable(self):
        backend = SimpleNamespace(nav=SimpleNamespace(pending_clipboard="winget install", say=mock.Mock()))
        with mock.patch.object(app.QGuiApplication, "clipboard", side_effect=RuntimeError("unavailable")):
            app.Backend._copy_pending(backend)
        backend.nav.say.assert_called_once_with("@t4.tools.copy_failed")
        self.assertIsNone(backend.nav.pending_clipboard)

    def test_refresh_supplies_empty_wordmark_when_bundle_has_no_images(self):
        backend = SimpleNamespace(nav=SimpleNamespace(view=lambda: {}), _copy_pending=mock.Mock(),
                                  viewChanged=mock.Mock())
        with mock.patch.object(app.os.path, "isfile", return_value=False):
            app.Backend.refresh(backend)
        self.assertEqual(backend._view["wordmark"], "")
        backend._copy_pending.assert_called_once_with()

    def test_finished_tool_check_refreshes_without_game_or_build_changes(self):
        adapter = Adapter(dict(id="t4", short="T4", accent="#ffffff"))
        rows = [dict(id="python", label="Python", value="@t4.tools.checking", ok=False, command="")]
        adapter.prerequisites = lambda: [dict(row) for row in rows]
        game = Game(adapter.m, adapter)
        backend = SimpleNamespace(nav=SimpleNamespace(games=[game]), window=None,
                                  _was_running=False, _was_building=False, _was_sourcing=False,
                                  _last_hero={game.id: ""})
        app.Backend._slow_changes(backend, False)
        self.assertFalse(app.Backend._slow_changes(backend, False))
        rows[0].update(value="3.12", ok=True)
        self.assertTrue(app.Backend._slow_changes(backend, False))
        self.assertFalse(app.Backend._slow_changes(backend, False))

    def test_image_free_scene_has_text_brand_and_no_warnings(self):
        gui = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        self.assertEqual(gui.platformName(), "offscreen")
        adapter = Fake(manifest("t4"))
        backend = FakeBackend(Nav([Game(adapter.m, adapter)]))
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda items: warnings.extend(item.toString() for item in items))
        engine.setInitialProperties({"backend": backend, "wantFull": False})
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            for source in Path(app.UI_DIR).glob("*.qml"):
                shutil.copyfile(source, Path(folder) / source.name)
            engine.load(QUrl.fromLocalFile(str(Path(folder) / "Main.qml")))
            spin()
            self.assertTrue(engine.rootObjects(), warnings)
            window = engine.rootObjects()[0]
            self.assertFalse(window.isVisible())
            brand = window.findChild(app.QObject, "brandFallback")
            self.assertIsNotNone(brand)
            self.assertEqual(brand.property("text"), "OpenRecomp-FGC")
            self.assertEqual(warnings, [])
            del window
            del engine


if __name__ == "__main__":
    unittest.main()
