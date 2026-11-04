"""A disabled action remains in the accessible tree with a discoverable reason."""
import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlProperty, qmlContext
from openrecomp.app import UI_DIR


class DisabledAccessibility(unittest.TestCase):
    def test_disabled_button_is_named_explained_and_enabled_state_blocks_activation(self):
        app = QGuiApplication.instance() or QGuiApplication([])
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
        engine.loadData(b'''import QtQuick
Item {
    width: 200; height: 80
    property bool blocked: true
    property var b: ({hint: "An account is required"})
    Interaction { disabled: parent.blocked; name: "Ranked" }
}''', QUrl.fromLocalFile(str(Path(UI_DIR) / "DisabledTest.qml")))
        self.assertTrue(engine.rootObjects(), warnings)
        root = engine.rootObjects()[0]
        target = root.findChild(QObject, "accessibleTarget")
        context = qmlContext(target)
        self.assertEqual(QQmlProperty(target, "Accessible.name", context).read(), "Ranked")
        self.assertEqual(QQmlProperty(target, "Accessible.description", context).read(), "An account is required")
        self.assertFalse(QQmlProperty(target, "Accessible.ignored", context).read())
        self.assertFalse(target.property("enabled"))
        root.setProperty("blocked", False)
        self.assertTrue(target.property("enabled"))
        self.assertEqual(QQmlProperty(target, "Accessible.description", context).read(), "")
        self.assertEqual(warnings, [])
