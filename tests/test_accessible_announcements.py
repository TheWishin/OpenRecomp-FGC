"""Qt announcements follow stable phases/results and ignore countdown or focus ticks."""
import copy
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QAccessible, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlProperty, qmlContext
from openrecomp import app


class AccessibleAnnouncements(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gui = QGuiApplication.instance() or QGuiApplication([])

    def test_real_refresh_announces_result_phase_and_incoming_once(self):
        view = dict(toast="", online=dict(phase="logged_in", find=dict(message="Connected")))
        backend = SimpleNamespace(nav=SimpleNamespace(view=lambda: copy.deepcopy(view)),
                                  window=QObject(), _view=copy.deepcopy(view), _wordmark="",
                                  _copy_pending=lambda: None, viewChanged=mock.Mock())
        messages = []
        def record(event):
            self.assertEqual(event.type(), QAccessible.Event.Announcement)
            self.assertEqual(event.politeness(), QAccessible.AnnouncementPoliteness.Polite)
            self.assertIs(event.object(), backend.window)
            messages.append(event.message())
        with mock.patch.object(app.QAccessible, "isActive", return_value=True), \
                mock.patch.object(app.QAccessible, "updateAccessibility", side_effect=record):
            app.Backend.refresh(backend)
            self.assertEqual(messages, [])
            view["toast"] = "Challenge sent to Rival"
            app.Backend.refresh(backend)
            app.Backend.refresh(backend)
            self.assertEqual(messages, ["Challenge sent to Rival"])
            view["toast"] = ""
            for seconds in (29, 28, 27):
                view["online"]["find"]["outgoing"] = dict(text="Waiting for Rival", status=f"Waiting {seconds}s")
                view["focus"] = seconds
                app.Backend.refresh(backend)
            self.assertEqual(messages, ["Challenge sent to Rival"])
            view["online"].update(phase="matched", message="Match found")
            app.Backend.refresh(backend)
            app.Backend.refresh(backend)
            view["online"]["find"]["incoming"] = dict(text="Incoming challenge from Peer", seconds=20)
            app.Backend.refresh(backend)
            view["online"]["find"]["incoming"]["seconds"] = 19
            app.Backend.refresh(backend)
            self.assertEqual(messages, ["Challenge sent to Rival", "Match found", "Incoming challenge from Peer"])
            view["online"].update(phase="error", message="Connection lost")
            app.Backend.refresh(backend)
            view["online"]["message"] = "Retry failed"
            app.Backend.refresh(backend)
            app.Backend.refresh(backend)
            self.assertEqual(messages[-2:], ["Connection lost", "Retry failed"])

    def test_no_announcement_without_an_active_reader_or_target_window(self):
        backend = SimpleNamespace(window=None, _view=dict(toast="Result"))
        with mock.patch.object(app.QAccessible, "updateAccessibility") as update:
            app.Backend._announce_view(backend, {})
            update.assert_not_called()
            backend.window = QObject()
            with mock.patch.object(app.QAccessible, "isActive", return_value=False):
                app.Backend._announce_view(backend, {})
                update.assert_not_called()

    def test_shared_titles_expose_real_heading_roles_and_names(self):
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
        engine.loadData(b'''import QtQuick
Item {
    OnlineStyle.PageTitle { objectName: "pageHeading"; text: "Community" }
    OnlineStyle.SectionHeader { objectName: "sectionHeading"; text: "Players" }
}''', QUrl.fromLocalFile(str(Path(app.UI_DIR) / "HeadingTest.qml")))
        self.assertTrue(engine.rootObjects(), warnings)
        root = engine.rootObjects()[0]
        for name, text in (("pageHeading", "Community"), ("sectionHeading", "Players")):
            heading = root.findChild(QObject, name)
            self.assertEqual(QQmlProperty(heading, "Accessible.role", qmlContext(heading)).read(), QAccessible.Role.Heading)
            self.assertEqual(QQmlProperty(heading, "Accessible.name", qmlContext(heading)).read(), text)
        self.assertEqual(warnings, [])
