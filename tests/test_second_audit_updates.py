"""Update workspace safety with inert local fixtures and no network or processes."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from openrecomp import updater as u


CHANNEL = u.Channel("example/OpenRecomp", "12345", "audit-channel", ("01" * 32,))


class UpdateWorkspaceSafety(unittest.TestCase):
    def setUp(self):
        temp = self.enterContext(tempfile.TemporaryDirectory(dir=Path(__file__).parent))
        self.root = Path(temp) / "install"
        self.root.mkdir()
        self.work = u._work_root(self.root)
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_HOME=str(Path(temp) / "player-data")))

    def linked(self, path, method):
        original = getattr(Path, method)
        return mock.patch.object(Path, method, autospec=True,
                                 side_effect=lambda item: item == path or original(item))

    def test_linked_workspace_refuses_before_download_or_directory_creation(self):
        for method in ("is_symlink", "is_junction"):
            with self.subTest(method=method), self.linked(self.work, method), \
                    mock.patch.object(u, "_download") as download:
                with self.assertRaises(u.UpdateError):
                    u.stage_update(self.root, dict(version="v1.2.3"), CHANNEL)
                download.assert_not_called()
                self.assertFalse(self.work.exists())

    def test_player_home_cannot_overlap_the_update_workspace(self):
        for home in (self.work, self.work / "private-data", self.work.parent):
            with self.subTest(home=home), mock.patch.dict(os.environ, OPENRECOMP_HOME=str(home)), \
                    mock.patch.object(u, "_download") as download:
                with self.assertRaises(u.UpdateError):
                    u.stage_update(self.root, dict(version="v1.2.3"), CHANNEL)
                download.assert_not_called()
                self.assertFalse(self.work.exists())

    def result(self):
        result = self.work / "transaction" / "result.json"
        result.parent.mkdir(parents=True)
        result.write_text(json.dumps(dict(status="rolled_back", version="v1.2.3")), encoding="utf-8")
        return result

    def test_startup_ignores_a_linked_workspace_without_reading_results(self):
        result = self.result()
        for method in ("is_symlink", "is_junction"):
            with self.subTest(method=method), self.linked(self.work, method), \
                    mock.patch.object(u, "_json") as read:
                self.assertIsNone(u.update_result(self.root))
                read.assert_not_called()
                self.assertTrue(result.is_file())

    def test_unreadable_workspace_is_nonfatal_and_preserves_results(self):
        result = self.result()
        for method in ("is_symlink", "is_junction", "is_dir", "iterdir"):
            original = getattr(Path, method)
            def inaccessible(item):
                if item == self.work:
                    raise PermissionError("inert workspace denial")
                return original(item)
            with self.subTest(method=method), \
                    mock.patch.object(Path, method, autospec=True, side_effect=inaccessible), \
                    mock.patch.object(u, "_json") as read:
                self.assertIsNone(u.update_result(self.root))
                read.assert_not_called()
                self.assertTrue(result.is_file())

    def test_workspace_enumeration_failure_does_not_consume_partial_results(self):
        result = self.result()
        def inaccessible():
            yield result.parent
            raise PermissionError("inert enumeration denial")
        with mock.patch.object(Path, "iterdir", return_value=inaccessible()), \
                mock.patch.object(u, "_json") as read:
            self.assertIsNone(u.update_result(self.root))
            read.assert_not_called()
            self.assertTrue(result.is_file())

    def test_startup_confirmation_ignores_a_linked_workspace_without_writing(self):
        marker = self.work / "transaction" / "confirmed.json"
        marker.parent.mkdir(parents=True)
        value = json.dumps(dict(path=str(marker), token="a" * 64))
        for method in ("is_symlink", "is_junction"):
            with self.subTest(method=method), self.linked(self.work, method), \
                    mock.patch.dict(os.environ, {u.CONFIRM_ENV: value}):
                self.assertFalse(u.confirm_startup(self.root))
                self.assertFalse(marker.exists())

    def test_startup_does_not_consume_linked_transactions_or_result_files(self):
        result = self.result()
        for linked in (result.parent, result):
            for method in ("is_symlink", "is_junction"):
                with self.subTest(linked=linked.name, method=method), self.linked(linked, method), \
                        mock.patch.object(u, "_json") as read:
                    self.assertIsNone(u.update_result(self.root))
                    read.assert_not_called()
                    self.assertTrue(result.is_file())


if __name__ == "__main__":
    unittest.main()
