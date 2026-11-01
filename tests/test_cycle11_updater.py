"""Release inventory and completed recovery remain compatible with updates."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

from openrecomp import updater as u
from tools import package_release as package


CHANNEL = u.Channel("example/OpenRecomp", "12345", "audit-channel", ("01" * 32,))


class PackageInventoryTests(unittest.TestCase):
    def test_updater_accepts_every_packaged_source_file(self):
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as archive:
            for name in sorted(package.SOURCE_FILES):
                archive.writestr("OpenRecomp-v1.2.3/" + name, b"inert audit fixture")
        raw.seek(0)
        with zipfile.ZipFile(raw) as archive:
            members = u._archive_members(archive, "v1.2.3")
        self.assertEqual({"/".join(parts) for _info, parts in members}, package.SOURCE_FILES)


class RestartFailureTests(unittest.TestCase):
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

    def assert_recovery(self, status):
        self.assertEqual(u.local_version(self.root), "v1.0.0")
        for item in u.REQUIRED_ITEMS:
            self.assertTrue((self.root / item).is_file())
        self.assertFalse((u._work_root(self.root) / "apply.lock").exists())
        self.assertEqual(u.update_result(self.root)["status"], status)

    def test_preflight_restart_failure_releases_unchanged_installation(self):
        restart = mock.Mock(side_effect=OSError("inert restart denial"))
        move = mock.Mock()
        with self.assertRaises(u.UpdateError) as error:
            u.apply_plan(self.plan, wait=0, alive=lambda _pid: False,
                         processes=mock.Mock(side_effect=OSError("inert inspection failure")),
                         restart=restart, move=move)
        self.assertTrue(error.exception.safe_to_unlock)
        restart.assert_called_once_with(self.root)
        move.assert_not_called()
        self.assert_recovery("unchanged")

    def test_restart_failure_after_complete_rollback_releases_installation(self):
        restart = mock.Mock(side_effect=OSError("inert restart denial"))
        with self.assertRaises(u.UpdateError) as error:
            u.apply_plan(self.plan, wait=0, alive=lambda _pid: False,
                         processes=lambda _root: [], restart=restart)
        self.assertTrue(error.exception.safe_to_unlock)
        self.assertEqual(restart.call_count, 2)
        self.assertIn("path", restart.call_args_list[0].args[1])
        self.assertEqual(restart.call_args_list[1], mock.call(self.root))
        self.assert_recovery("rolled_back")


if __name__ == "__main__":
    unittest.main()
