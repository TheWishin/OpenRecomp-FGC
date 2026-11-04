"""The installed report API is replaced by fakes: no game files or reports are read or written."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp.adapters.base import Adapter
from openrecomp.adapters.support import T5Support


class FakeSettings(dict):
    out_dir = "fake-output"


class FakeAdapter(T5Support, Adapter):
    def __init__(self):
        super().__init__(dict(id="test", short="Test"))
        self.root = "fake-install"
        self.s = FakeSettings(display="window")
        self.dest = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "player-desktop"))
        self.core = SimpleNamespace(desktop_dir=mock.Mock(return_value=self.dest))
        self.check = SimpleNamespace(check=mock.Mock(return_value=[]))
        self.report = SimpleNamespace(
            Context=mock.Mock(side_effect=lambda *args, **kwargs: SimpleNamespace(out_dir=args[0], **kwargs)),
            settings_lines=mock.Mock(return_value=["fake settings"]),
            build_info_for=mock.Mock(return_value=dict(build_id="fake")),
            discover=mock.Mock(return_value=[object()]),
            build=mock.Mock(return_value=SimpleNamespace(path=os.path.join(self.dest, "report.zip"))))
        self._support_modules = (self.check, self.report)

    def release(self):
        return dict(version="fake-version")

    def online_cfg_path(self):
        return os.path.join("fake-online", "online.json")


class Support(unittest.TestCase):
    def setUp(self):
        self.adapter = FakeAdapter()
        self.thread = self.enterContext(mock.patch("openrecomp.adapters.support.threading.Thread"))

    def finish(self):
        call = self.thread.call_args
        call.kwargs["target"](*call.kwargs["args"])

    def test_checks_run_only_when_requested_and_findings_are_catalog_messages(self):
        a = self.adapter
        self.assertTrue(a.support_available())
        self.assertEqual(a.support_state()["findings"], [])
        a.check.check.assert_not_called()
        a.report.build.assert_not_called()
        a.check.check.return_value = [SimpleNamespace(key="unpack_memory", kind="problem")]
        self.assertTrue(a.support_start("check"))
        self.assertTrue(a.support_state()["running"])
        a.check.check.assert_not_called()
        self.finish()
        a.check.check.assert_called_once_with(a.s.out_dir)
        state = a.support_state()
        self.assertFalse(state["running"])
        self.assertTrue(state["checked"])
        self.assertEqual(state["findings"][0]["label"], "@support.finding.unpack_memory.title")
        self.assertEqual(state["findings"][0]["fix"], "@support.finding.unpack_memory.fix")
        a.report.build.assert_not_called()

    def test_unknown_findings_have_localized_recovery_instructions(self):
        a = self.adapter
        a.check.check.return_value = [SimpleNamespace(key="future_case", kind="hint")]
        a.support_start("check")
        self.finish()
        self.assertEqual(a.support_state()["findings"][0]["fix"], "@support.finding.unknown.fix")

    def test_report_uses_native_context_scrubbing_and_writer_without_sending(self):
        a = self.adapter
        a.support_start("report")
        self.finish()
        a.core.desktop_dir.assert_called_once_with()
        context = a.report.discover.call_args.args[0]
        self.assertEqual(context.out_dir, a.s.out_dir)
        self.assertEqual(context.root, a.root)
        self.assertEqual(context.online_dir, "fake-online")
        self.assertEqual(context.settings_lines, ["fake settings"])
        self.assertEqual(context.build_info(), dict(build_id="fake"))
        a.report.build.assert_called_once_with(context, a.dest, groups=a.report.discover.return_value)
        a.check.check.assert_not_called()
        state = a.support_state()
        self.assertEqual(state["report"], os.path.join(a.dest, "report.zip"))
        self.assertFalse(state["running"])
        self.assertFalse(state["error"])

    def test_busy_request_does_not_start_another_worker(self):
        self.assertTrue(self.adapter.support_start("check"))
        self.assertFalse(self.adapter.support_start("report"))
        self.assertEqual(self.thread.call_count, 1)
        self.assertTrue(self.thread.call_args.kwargs["daemon"])

    def test_worker_start_failure_allows_retry(self):
        self.thread.return_value.start.side_effect = RuntimeError("fake worker failure")
        self.assertFalse(self.adapter.support_start("check"))
        self.assertFalse(self.adapter.support_state()["running"])
        self.assertTrue(self.adapter.support_state()["error"])
        self.thread.return_value.start.side_effect = None
        self.assertTrue(self.adapter.support_start("check"))

    def test_failure_keeps_findings_and_can_be_retried(self):
        a = self.adapter
        a.check.check.return_value = [SimpleNamespace(key="wine", kind="hint")]
        a.support_start("check")
        self.finish()
        a.report.build.side_effect = OSError("fake report failure")
        a.support_start("report")
        self.finish()
        state = a.support_state()
        self.assertFalse(state["running"])
        self.assertEqual(state["findings"][0]["id"], "wine")
        self.assertEqual(state["error"], Adapter.message("support.failed", error="fake report failure"))
        a.report.build.side_effect = None
        self.assertTrue(a.support_start("report"))
        self.finish()
        self.assertFalse(a.support_state()["error"])

    def test_returned_findings_cannot_change_worker_state(self):
        a = self.adapter
        a.check.check.return_value = [SimpleNamespace(key="wine", kind="hint")]
        a.support_start("check")
        self.finish()
        a.support_state()["findings"][0]["id"] = "changed"
        self.assertEqual(a.support_state()["findings"][0]["id"], "wine")

    def test_missing_native_functions_hide_support(self):
        self.adapter.report.build = None
        self.assertFalse(self.adapter.support_available())
        with self.assertRaises(RuntimeError):
            self.adapter.support_start("report")
        self.thread.assert_not_called()

    def test_invalid_operation_does_not_start_work(self):
        with self.assertRaises(RuntimeError):
            self.adapter.support_start("upload")
        self.thread.assert_not_called()

    def test_report_destination_never_defaults_to_checkout(self):
        a = self.adapter
        for dest in ("", ".", os.path.abspath(os.path.join(os.path.dirname(__file__), "reports"))):
            with self.subTest(dest=dest):
                a.core.desktop_dir.return_value = dest
                a.support_start("report")
                self.finish()
                self.assertTrue(a.support_state()["error"])
                a.report.build.assert_not_called()

    def test_missing_modules_and_wrong_install_cache_hide_support(self):
        a = self.adapter
        del a._support_modules
        with mock.patch.dict(sys.modules, {"replays": SimpleNamespace(__file__="other-install/replays.py")}):
            self.assertFalse(a.support_available())
        with mock.patch.dict(sys.modules, {"replays": None}), mock.patch("os.path.isfile", return_value=False):
            self.assertFalse(a.support_available())

    def test_module_cache_must_match_this_install(self):
        a = self.adapter
        with mock.patch("os.path.isfile", return_value=True):
            module = SimpleNamespace(__file__=os.path.join(a.root, "launcher", "problem_report.py"))
            with mock.patch.dict(sys.modules, {"problem_report": module}):
                self.assertIs(a._support_import("problem_report"), module)
            with mock.patch.dict(sys.modules, {"problem_report": SimpleNamespace(__file__="other-install/problem_report.py")}):
                with self.assertRaises(ImportError):
                    a._support_import("problem_report")


if __name__ == "__main__":
    unittest.main()
