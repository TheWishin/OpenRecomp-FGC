"""Updater safety regressions using inert files; no downloads or launcher processes."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

from openrecomp import updater as u
from openrecomp.update_service import UpdateService
from tools import release_sign


CHANNEL = u.Channel("example/OpenRecomp", "12345", "audit-channel", ("01" * 32,))


class UpdateSafety(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory(dir=Path(__file__).parent))
        self.root = Path(self.temp) / "install"
        self.root.mkdir()
        self.channel = CHANNEL
        self.enterContext(mock.patch.object(u, "configured_channel", side_effect=lambda: self.channel))
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_HOME=str(Path(self.temp) / "player-data")))

    def program(self, root, version):
        for item in u.REQUIRED_ITEMS:
            path = root / item
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("inert audit fixture", encoding="utf-8")
        (root / "release.json").write_text(json.dumps(dict(
            project=u.PROJECT, channel=CHANNEL.name, version=version)), encoding="utf-8")

    def transaction(self, current="v1.0.0"):
        self.program(self.root, current)
        staged = u._work_root(self.root) / "audit" / "new"
        staged.mkdir(parents=True, exist_ok=True)
        self.program(staged, "v1.2.3")
        seed = os.urandom(32)
        public = release_sign.public_key(seed)
        self.channel = u.Channel(CHANNEL.repository, CHANNEL.repository_id, CHANNEL.name, (public.hex(),))
        archive_path = staged.parent / "release.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            for source in staged.rglob("*"):
                if source.is_file():
                    archive.write(source, u.ARCHIVE_TOP + "/" + source.relative_to(staged).as_posix())
        sums = (hashlib.sha256(archive_path.read_bytes()).hexdigest() + "  OpenRecomp-v1.2.3.zip\n").encode("ascii")
        signature = release_sign.sign(seed, u.signature_message(self.channel.name, "v1.2.3", sums))
        (staged.parent / "SHA256SUMS").write_bytes(sums)
        (staged.parent / "SHA256SUMS.sig").write_text(json.dumps(dict(algorithm="ed25519",
            channel=self.channel.name, version="v1.2.3", key_id=hashlib.sha256(public).hexdigest()[:16],
            signature=signature.hex())), encoding="utf-8")
        path = staged.parent / "plan.json"
        path.write_text(json.dumps(dict(root=str(self.root), staged=str(staged),
            version="v1.2.3", channel=CHANNEL.name, pid=123, token="a" * 64)), encoding="utf-8")
        (staged.parent / "verified.json").write_text(json.dumps(dict(
            version="v1.2.3", channel=self.channel.name)), encoding="utf-8")
        return path

    def assert_tampering_refused(self, mutate):
        plan = self.transaction()
        staged = plan.parent / "new"
        mutate(staged)
        with mock.patch.object(u.subprocess, "Popen") as spawn:
            with self.assertRaises(u.UpdateError):
                u.prepare_update(self.root, staged, self.channel)
        spawn.assert_not_called()
        move = mock.Mock()
        with self.assertRaises(u.UpdateError):
            u.apply_plan(plan, wait=0, alive=lambda _pid: False, processes=lambda _root: [],
                         restart=mock.Mock(), move=move)
        move.assert_not_called()
        self.assertEqual(u.local_version(self.root), "v1.0.0")
        self.assertFalse((u._work_root(self.root) / "apply.lock").exists())

    def test_unchanged_stage_authenticates_again_with_retained_signed_evidence(self):
        plan = self.transaction()
        u._verify_staged(plan.parent / "new", dict(version="v1.2.3"), self.channel)

    def test_changed_staged_code_is_rejected_before_helper_launch_or_swap(self):
        self.assert_tampering_refused(lambda stage: (stage / "openrecomp" / "app.py").write_text(
            "changed inert fixture", encoding="utf-8"))

    def test_extra_staged_code_is_rejected_before_helper_launch_or_swap(self):
        self.assert_tampering_refused(lambda stage: (stage / "portable" / "extra.py").write_text(
            "inert audit fixture", encoding="utf-8"))

    def test_extra_staged_directory_is_rejected_before_helper_launch_or_swap(self):
        self.assert_tampering_refused(lambda stage: (stage / "portable" / "extra").mkdir())

    def test_modified_retained_archive_cannot_authorize_a_changed_stage(self):
        def modify(stage):
            with (stage.parent / "release.zip").open("ab") as archive:
                archive.write(b"inert archive corruption")
        self.assert_tampering_refused(modify)

    def test_missing_signature_cannot_be_replaced_with_a_verified_json_marker(self):
        self.assert_tampering_refused(lambda stage: (stage.parent / "SHA256SUMS.sig").write_text(
            "{}", encoding="utf-8"))

    def test_staged_directory_links_are_rejected(self):
        def modify(stage):
            try:
                os.symlink(self.root / "portable", stage / "openrecomp" / "linked", target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Directory symlinks are unavailable without changing system permissions")
        self.assert_tampering_refused(modify)

    def test_real_helper_preparation_runs_on_worker_and_spawn_waits_for_ui_busy_check(self):
        plan = self.transaction()
        staged = plan.parent / "new"
        threads = {}
        ui_thread = threading.get_ident()
        busy = [False]
        def prepare(root, stage):
            threads["prepare"] = threading.get_ident()
            return u.prepare_update(root, stage, self.channel)
        def launch(root, prepared):
            threads["launch"] = threading.get_ident()
            return u.launch_update(root, prepared, self.channel)
        def worker(fn):
            thread = threading.Thread(target=fn)
            thread.start()
            thread.join(timeout=30)
            self.assertFalse(thread.is_alive())
        api = SimpleNamespace(check_release=lambda _root, **_kw: dict(version="v1.2.3"),
            stage_update=lambda _root, _release, **_kw: staged, prepare_update=prepare, launch_update=launch)
        quit_app = mock.Mock()
        service = UpdateService(self.root, api=api, worker=worker,
                                busy=lambda: busy[0], quit=quit_app)
        service.check()
        service.poll()
        with mock.patch.object(u.subprocess, "Popen") as spawn:
            self.assertTrue(service.install())
            self.assertNotEqual(threads["prepare"], ui_thread)
            spawn.assert_not_called()
            busy[0] = True
            service.poll()
            spawn.assert_not_called()
            busy[0] = False
            service.poll()
            self.assertEqual(threads["launch"], ui_thread)
            spawn.assert_called_once()
            quit_app.assert_called_once()

    def test_corrupt_result_does_not_prevent_startup_or_hide_valid_recovery(self):
        work = u._work_root(self.root)
        valid, broken = work / "older" / "result.json", work / "newer" / "result.json"
        valid.parent.mkdir(parents=True)
        broken.parent.mkdir()
        valid.write_text(json.dumps(dict(status="recovery_required", version="v1.2.3")), encoding="utf-8")
        for raw in ("{", "[]", "null", '"wrong type"'):
            with self.subTest(raw=raw):
                valid.write_text(json.dumps(dict(status="recovery_required", version="v1.2.3")), encoding="utf-8")
                broken.write_text(raw, encoding="utf-8")
                os.utime(valid, (1, 1))
                os.utime(broken, (2, 2))
                self.assertEqual(u.update_result(self.root)["status"], "recovery_required")
                self.assertIsNone(u.update_result(self.root))

    def test_expanded_player_home_is_checked_before_any_download(self):
        with mock.patch.object(u.os.path, "expanduser", return_value=str(self.root / "openrecomp" / "data")), \
                mock.patch.dict(os.environ, OPENRECOMP_HOME="~/data"), \
                mock.patch.object(u, "_download") as download:
            with self.assertRaises(u.UpdateError):
                u.stage_update(self.root, dict(version="v1.2.3"), CHANNEL)
        download.assert_not_called()

    def test_default_player_home_is_checked_before_any_download(self):
        with mock.patch.dict(os.environ, OPENRECOMP_HOME="", LOCALAPPDATA=str(self.root / "openrecomp")), \
                mock.patch.object(u, "_download") as download:
            with self.assertRaises(u.UpdateError):
                u.stage_update(self.root, dict(version="v1.2.3"), CHANNEL)
        download.assert_not_called()

    def test_second_helper_cannot_move_files_while_first_owns_transaction(self):
        plan = self.transaction()
        lock = u._work_root(self.root) / "apply.lock"
        lock.mkdir()
        move, restart = mock.Mock(), mock.Mock()
        with self.assertRaises(u.UpdateError):
            u.apply_plan(plan, wait=0, alive=lambda _pid: False, processes=lambda _root: [],
                         restart=restart, move=move)
        move.assert_not_called()
        restart.assert_not_called()
        self.assertTrue(lock.is_dir())
        self.assertEqual(u.local_version(self.root), "v1.0.0")

    def test_offer_cannot_downgrade_an_install_updated_while_waiting(self):
        for current in ("v1.2.3", "v2.0.0"):
            with self.subTest(current=current):
                plan = self.transaction(current)
                move, restart = mock.Mock(), mock.Mock()
                with self.assertRaises(u.UpdateError):
                    u.apply_plan(plan, wait=0, alive=lambda _pid: False, processes=lambda _root: [],
                                 restart=restart, move=move)
                move.assert_not_called()
                self.assertEqual(u.local_version(self.root), current)
                self.assertFalse((u._work_root(self.root) / "apply.lock").exists())
                # Reuse the inert transaction after this preflight refusal.
                self.assertEqual(u.update_result(self.root)["status"], "unchanged")

    def test_exclusive_lock_is_held_through_rollback_and_released_afterward(self):
        plan = self.transaction()
        lock = u._work_root(self.root) / "apply.lock"
        def move(source, destination):
            self.assertTrue(lock.is_dir())
            os.replace(source, destination)
        def restart(root, marker=None):
            self.assertTrue(lock.is_dir())
            if marker:
                raise OSError("inert restart failure")
        with self.assertRaises(u.UpdateError):
            u.apply_plan(plan, wait=0, alive=lambda _pid: False, processes=lambda _root: [],
                         restart=restart, move=move)
        self.assertEqual(u.local_version(self.root), "v1.0.0")
        self.assertFalse(lock.exists())
        self.assertEqual(u.update_result(self.root)["status"], "rolled_back")

    def test_failed_restoration_keeps_lock_until_manual_recovery(self):
        plan = self.transaction()
        lock = u._work_root(self.root) / "apply.lock"
        def move(source, destination):
            if source.parent.name == "backup":
                raise OSError("inert restoration failure")
            os.replace(source, destination)
        def restart(root, marker=None):
            if marker:
                raise OSError("inert restart failure")
        with self.assertRaises(u.UpdateError):
            u.apply_plan(plan, wait=0, alive=lambda _pid: False, processes=lambda _root: [],
                         restart=restart, move=move)
        self.assertTrue(lock.is_dir())
        self.assertEqual(u.update_result(self.root)["status"], "recovery_required")
