"""Repair a T5DR release in its existing folder; all installs and services here are inert fakes."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp import game_releases as gr
from openrecomp.game_setup import GameSetup
from openrecomp.app_game_setup import GameSetupBackend
from openrecomp.nav import Game, Nav
from test_game_setup_nav import Game5, Setup

ROOT = Path(__file__).resolve().parents[1]


class ReinstallNav(unittest.TestCase):
    def setUp(self):
        self.setup = Setup()
        self.nav = Nav([Game(Game5().m, Game5())], language="en", on_setup=self.setup)
        self.game = self.nav.games[0]

    def test_one_click_reinstalls_known_release_without_folder_or_confirmation_dialog(self):
        self.nav.setup_state = {"t5dr": dict(phase="ready", latest="1.2.0")}
        self.nav.setup_reinstall(self.game)
        self.assertEqual(self.setup.calls, [("reinstall", "t5dr", None)])
        self.assertEqual(self.nav.confirm_kind, "setup_progress")
        self.nav.poll_setup([("t5dr", "update", dict(restart=True), None)])
        self.assertEqual(self.nav.confirm_kind, "setup_restart")

    def test_one_click_checks_release_then_reinstalls_without_another_confirmation(self):
        self.nav.setup_reinstall(self.game)
        self.assertEqual(self.setup.calls, [("check", "t5dr", True)])
        self.assertEqual(self.nav.confirm_kind, "setup_loading")
        self.nav.setup_state = {"t5dr": dict(phase="ready", latest="1.2.0")}
        self.nav.poll_setup([("t5dr", "check", {}, None)])
        self.assertEqual(self.setup.calls[-1], ("reinstall", "t5dr", None))
        self.assertEqual(self.nav.confirm_kind, "setup_progress")

    def test_cancel_during_release_check_never_reinstalls(self):
        self.nav.setup_reinstall(self.game)
        self.nav.act("back", device="xbox")
        self.nav.setup_state = {"t5dr": dict(phase="ready", latest="1.2.0")}
        self.nav.poll_setup([("t5dr", "check", {}, None)])
        self.assertEqual(self.setup.calls, [("check", "t5dr", True)])
        self.assertIsNone(self.nav.overlay)

    def test_existing_check_is_reused(self):
        self.nav.setup_state = {"t5dr": dict(phase="checking")}
        self.nav.setup_reinstall(self.game)
        self.assertEqual(self.setup.calls, [])
        self.nav.setup_state["t5dr"].update(phase="ready", latest="1.2.0")
        self.nav.poll_setup([("t5dr", "check", {}, None)])
        self.assertEqual(self.setup.calls, [("reinstall", "t5dr", None)])


class ReinstallBackend(unittest.TestCase):
    def test_backend_uses_existing_root_and_closes_lobby_before_exchange(self):
        backend = GameSetupBackend()
        backend._setup_root = mock.Mock(return_value="fake-existing-install")
        backend._update_busy = mock.Mock(return_value=False)
        backend.nav = SimpleNamespace(close_online=mock.Mock())
        backend.setup = SimpleNamespace(update=mock.Mock(return_value=True))
        self.assertTrue(backend._setup_action("reinstall", "t5dr", None))
        backend.nav.close_online.assert_called_once_with(only="t5dr")
        backend.setup.update.assert_called_once_with("t5dr", "fake-existing-install", reinstall=True)

    def test_worker_forwards_reinstall_and_uses_existing_update_completion(self):
        update = mock.Mock(return_value=dict(version="1.2.0", restart=True, rebuild=False))
        setup = GameSetup({}, worker=lambda fn: fn(), update=update)
        offer = dict(version="1.2.0", zip=dict(size=12), name="v1.2.0", prerelease=False, notes="")
        setup.offers["t5dr"] = offer
        self.assertTrue(setup.update("t5dr", "existing-install", reinstall=True))
        self.assertEqual(update.call_args.args, ("t5dr", offer, "existing-install"))
        self.assertTrue(update.call_args.kwargs["reinstall"])
        self.assertEqual(setup.poll()[0][1], "update")
        self.assertEqual(setup.view("t5dr")["phase"], "updated")
        self.assertTrue(setup.view("t5dr")["restart"])


class ReinstallExchange(unittest.TestCase):
    def setUp(self):
        home = ROOT / "build" / "tmp-home"
        home.mkdir(parents=True, exist_ok=True)
        self.folder = tempfile.TemporaryDirectory(prefix="reinstall-", dir=home)
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name) / "install"
        self.root.mkdir()
        self.write("release.json", json.dumps(dict(version="1.2.0")))
        self.write("launcher/core.py", "# old inert marker\n")
        self.offer = dict(version="1.2.0", tag="v1.2.0", zip=dict(size=1, sha256="test"))

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_same_release_repair_exchanges_program_files_and_preserves_player_markers(self):
        protected = ("native/player-marker.txt", "game/player-marker.txt", "keys/player-marker.txt",
                     "launcher.json", "saves/player-marker.txt")
        for name in protected:
            self.write(name, "inert preservation marker")

        def download(src, offer, destination, **kwargs):
            path = Path(destination) / "release.zip"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"inert archive marker")
            return str(path)

        def unpack(src, archive, destination, offer, **kwargs):
            new = Path(destination)
            (new / "launcher").mkdir(parents=True)
            (new / "launcher" / "core.py").write_text("# repaired inert marker\n", encoding="utf-8")
            (new / "release.json").write_text(json.dumps(dict(version="1.2.0")), encoding="utf-8")
            return str(new)

        with mock.patch.object(gr, "verified_zip", side_effect=download), \
                mock.patch.object(gr, "unpack", side_effect=unpack), \
                mock.patch.object(gr, "processes_under", return_value=[]), \
                mock.patch.object(gr, "free_space", return_value=100_000_000_000):
            result = gr.update_in_place("t5dr", self.offer, str(self.root), keys=(), reinstall=True)
        self.assertTrue(result["restart"])
        self.assertEqual((self.root / "launcher" / "core.py").read_text(), "# repaired inert marker\n")
        for name in protected:
            self.assertEqual((self.root / name).read_text(), "inert preservation marker")

    def test_same_version_update_still_requires_explicit_reinstall_and_downgrades_are_refused(self):
        for reinstall, version in ((False, "1.2.0"), (True, "1.1.9")):
            with self.subTest(reinstall=reinstall, version=version), \
                    mock.patch.object(gr, "verified_zip") as download, \
                    self.assertRaises(gr.ReleaseError) as raised:
                gr.update_in_place("t5dr", dict(self.offer, version=version), str(self.root), reinstall=reinstall)
            self.assertEqual(raised.exception.key, "@setup.err_not_newer")
            download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
