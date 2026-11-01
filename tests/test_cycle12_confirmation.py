"""A confirmation being written must not look like a failed launcher."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from openrecomp import updater as u


CHANNEL = u.Channel("example/OpenRecomp", "12345", "audit-channel", ("01" * 32,))


class ConfirmationPollingTests(unittest.TestCase):
    def setUp(self):
        temp = self.enterContext(tempfile.TemporaryDirectory(dir=Path(__file__).parent))
        self.root = Path(temp) / "install"
        self.staged = u._work_root(self.root) / "transaction" / "new"
        self.staged.mkdir(parents=True)
        for root, version in ((self.root, "v1.0.0"), (self.staged, "v1.2.3")):
            for item in u.REQUIRED_ITEMS:
                path = root / item
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("inert audit fixture", encoding="utf-8")
            (root / "release.json").write_text(json.dumps(dict(
                project=u.PROJECT, channel=CHANNEL.name, version=version)), encoding="utf-8")
        self.plan = self.staged.parent / "plan.json"
        self.plan.write_text(json.dumps(dict(root=str(self.root), staged=str(self.staged),
            version="v1.2.3", channel=CHANNEL.name, pid=123, token="a" * 64)), encoding="utf-8")
        self.enterContext(mock.patch.object(u, "configured_channel", return_value=CHANNEL))
        self.enterContext(mock.patch.object(u, "_verify_staged"))
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_HOME=str(Path(temp) / "player-data")))
        self.now = 0
        self.enterContext(mock.patch.object(u.time, "monotonic", side_effect=lambda: self.now))

    def test_partial_confirmation_is_retried_without_stopping_healthy_launcher(self):
        proc = mock.Mock()
        proc.poll.return_value = None
        marker = self.staged.parent / "confirmed.json"
        def restart(root, confirmation=None):
            marker.write_text("", encoding="utf-8")
            return proc
        def sleep(duration):
            self.now += duration
            marker.write_text(json.dumps(dict(token="a" * 64)), encoding="utf-8")
        restart_call = mock.Mock(side_effect=restart)
        self.assertTrue(u.apply_plan(self.plan, wait=1, alive=lambda _pid: False,
                                     processes=lambda _root: [], restart=restart_call, sleep=sleep))
        restart_call.assert_called_once()
        proc.terminate.assert_not_called()
        self.assertEqual(u.local_version(self.root), "v1.2.3")
        self.assertFalse((u._work_root(self.root) / "apply.lock").exists())
        self.assertEqual(u.update_result(self.root)["status"], "updated")

    def test_permanently_malformed_confirmation_rolls_back_at_deadline(self):
        proc = mock.Mock()
        proc.poll.return_value = None
        marker = self.staged.parent / "confirmed.json"
        def restart(root, confirmation=None):
            if confirmation:
                marker.write_text("{", encoding="utf-8")
            return proc
        def sleep(duration):
            self.now += duration
        restart_call = mock.Mock(side_effect=restart)
        with self.assertRaises(u.UpdateError) as error:
            u.apply_plan(self.plan, wait=1, alive=lambda _pid: False,
                         processes=lambda _root: [], restart=restart_call, sleep=sleep)
        self.assertGreaterEqual(self.now, 1)
        self.assertTrue(error.exception.safe_to_unlock)
        proc.terminate.assert_called_once()
        proc.wait.assert_called_once_with(timeout=15)
        self.assertEqual(restart_call.call_count, 2)
        self.assertEqual(restart_call.call_args_list[1], mock.call(self.root))
        self.assertEqual(u.local_version(self.root), "v1.0.0")
        self.assertFalse((u._work_root(self.root) / "apply.lock").exists())
        self.assertEqual(u.update_result(self.root)["status"], "rolled_back")


if __name__ == "__main__":
    unittest.main()
