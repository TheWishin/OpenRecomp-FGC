"""Local check/report actions and findings, driven entirely by semantic actions."""
import os
import unittest

from openrecomp.nav import Game, Nav
from test_nav import Fake, manifest


class SupportFake(Fake):
    def __init__(self):
        super().__init__(manifest())
        self.state = dict(running=False, operation="", checked=False, findings=[], report="", error="")

    def support_available(self):
        return True

    def support_start(self, kind="check"):
        self.calls.append(("support", kind))
        self.state = dict(self.state, running=True, operation=kind)
        return True

    def support_state(self):
        return dict(self.state)


class SupportNavigation(unittest.TestCase):
    def setUp(self):
        self.a = SupportFake()
        self.nav = Nav([Game(self.a.m, self.a)], language="en")
        self.nav.screen = "hub"
        self.nav.sec[self.nav.game.id] = "support"

    def test_section_hidden_without_runtime_feature(self):
        self.assertIn("support", self.nav.sections())
        other = Fake(manifest())
        self.assertNotIn("support", Nav([Game(other.m, other)]).sections())

    def test_check_starts_once_and_polled_findings_explain_next_step(self):
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.a.calls, [("support", "check")])
        self.nav.act("confirm", device="xbox")
        self.assertEqual(len(self.a.calls), 1)
        self.a.state = dict(self.a.state, running=False, checked=True,
                            findings=[dict(id="example", label="Something needs attention", seen="A check failed", fix="Open settings")])
        self.assertTrue(self.nav.poll_tools())
        self.nav.act("down", device="xbox")
        self.nav.act("down", device="xbox")
        detail = self.nav.view()["detail"]
        self.assertEqual(detail["title"], "Something needs attention")
        self.assertEqual(detail["lead"], "Open settings")
        self.assertIsNone(self.nav.support_game)

    def test_report_requires_explicit_confirmation_with_no_as_default(self):
        self.nav.act("down", device="xbox")
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.nav.overlay, "dialog")
        self.assertEqual(self.a.calls, [])
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.a.calls, [])
        self.nav.act("confirm", device="xbox")
        self.nav.act("right", device="xbox")
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.a.calls, [("support", "report")])

    def test_completed_local_report_is_visible_without_send_action(self):
        self.a.state = dict(self.a.state, checked=True, report="report.zip")
        self.nav.act("down", device="xbox")
        self.nav.act("down", device="xbox")
        detail = self.nav.view()["detail"]
        self.assertEqual(detail["rows"][0]["v"], "report.zip")
        self.assertFalse(any("send" in item["id"] for item in self.nav.items()))

    def test_dry_report_confirm_does_not_create_archive(self):
        self.nav.dry = True
        self.nav.act("down")
        self.nav.act("confirm")
        self.nav.act("right")
        self.nav.act("confirm")
        self.assertEqual(self.a.calls, [])


class ToolScenes(unittest.TestCase):
    def test_optional_sections_and_binding_dialogs_load_in_every_catalog(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
        from openrecomp import i18n
        from openrecomp.app import UI_DIR
        from test_controls_nav import ControlsFake
        from test_ui_loads import FakeBackend, spin

        app = QGuiApplication.instance() or QGuiApplication([])
        adapter = ControlsFake()
        support = SupportFake()
        adapter.support_available = support.support_available
        adapter.support_state = support.support_state
        adapter.support_start = support.support_start
        nav = Nav([Game(adapter.m, adapter)], language="en")
        nav.screen = "hub"
        nav.sec[nav.game.id] = "controls"
        backend = FakeBackend(nav)
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda messages: warnings.extend(message.toString() for message in messages))
        engine.setInitialProperties({"backend": backend, "wantFull": False})
        engine.load(QUrl.fromLocalFile(os.path.join(UI_DIR, "Main.qml")))
        self.assertTrue(engine.rootObjects(), warnings)

        def publish():
            backend._v = nav.view()
            backend.viewChanged.emit()
            spin()

        for language in i18n.LANGUAGES:
            with self.subTest(language=language):
                nav.language = language
                nav.sec[nav.game.id] = "controls"
                publish()
                self.assertEqual(len(backend._v["tabs"]), 7)
                nav.act("confirm", device="xbox")
                publish()
                self.assertEqual(backend._v["overlay"], "dialog")
                adapter.result = dict(state="conflict", source="B", conflicts=["@controls.slot.SELECT"])
                nav.poll_tools()
                publish()
                self.assertEqual(len(backend._v["dialog"]["options"]), 2)
                nav.act("back", device="xbox")
                adapter.result = dict(state="waiting")
                nav.sec[nav.game.id] = "support"
                support.state = dict(support.state, checked=True, report="report.zip",
                                     findings=[dict(id="gpu", label="@support.finding.gpu_tier1.title", seen="",
                                                    fix="@support.finding.gpu_tier1.fix")])
                nav.focus[nav.key()] = 2
                publish()
                nav.focus[nav.key()] = 1
                nav.act("confirm", device="xbox")
                publish()
                nav.act("back", device="xbox")
        self.assertEqual(warnings, [])
        del engine
        del app


if __name__ == "__main__":
    unittest.main()
