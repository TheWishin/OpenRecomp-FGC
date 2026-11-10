"""Uninstall OpenRecomp completely (0.1.3): a throwaway OPENRECOMP_HOME and install folders only."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from openrecomp import game_releases, uninstall
from openrecomp.nav import Nav


def managed_install(root, game):
    root.mkdir(parents=True)
    (root / game_releases.MARKER).write_text(json.dumps(dict(game=game, version="0.1.3", installed_by="OpenRecomp-FGC")),
                                             encoding="utf-8")
    return root


class ZipCopyRemoval(unittest.TestCase):
    """The zip copy's program folder really goes once the launcher quit: a folder with spaces, a real cmd.exe."""

    @unittest.skipUnless(os.name == "nt", "Windows only")
    def test_the_folder_is_removed_for_real(self):
        import subprocess
        import time
        with tempfile.TemporaryDirectory() as temp:
            program = Path(temp) / "Games With Spaces" / "OpenRecomp-FGC"
            (program / "openrecomp").mkdir(parents=True)
            (program / "openrecomp" / "app.py").write_text("x", encoding="utf-8")
            with mock.patch.object(uninstall, "WAIT_SECONDS", 1):
                result = uninstall.execute(dict(program=str(program)), start=subprocess.Popen)
            self.assertTrue(result["program_started"])
            deadline = time.monotonic() + 20
            while program.exists() and time.monotonic() < deadline:
                time.sleep(0.2)
            self.assertFalse(program.exists())
            self.assertTrue(program.parent.is_dir())               # only the program folder


class Plan(unittest.TestCase):
    def setUp(self):
        self.dir = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.home = self.dir / "home"
        self.home.mkdir()
        (self.home / "config.json").write_text("{}", encoding="utf-8")
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_HOME=str(self.home)))
        self.t4 = managed_install(self.dir / "Games" / "T4", "t4")
        self.t5 = managed_install(self.dir / "Games" / "T5DR-Online-1.2.1", "t5dr")
        self.program = self.dir / "Games" / "OpenRecomp-FGC"
        self.program.mkdir()
        (self.program / "release.json").write_text("{}", encoding="utf-8")

    def config(self, **roots):
        return dict(roots=dict(dict(t4=str(self.t4), t5dr=str(self.t5)), **roots))

    def test_the_list_names_everything_and_touches_nothing(self):
        plan = uninstall.plan(self.config(), program=str(self.program))
        self.assertEqual([g["root"] for g in plan["games"]], [str(self.t4), str(self.t5)])
        self.assertEqual(plan["data"], str(self.home))
        self.assertEqual(plan["program"], str(self.program))
        self.assertEqual(plan["setup_uninstaller"], "")
        self.assertTrue(self.t4.is_dir() and self.home.is_dir())

    def test_every_known_install_it_made_is_listed_not_only_the_one_in_use(self):
        old = managed_install(self.dir / "Old" / "T4", "t4")
        foreign = self.dir / "Mine" / "T4"
        foreign.mkdir(parents=True)
        config = self.config()
        config["known_roots"] = dict(t4=[str(old), str(foreign), str(self.dir / "gone" / "T4")])
        plan = uninstall.plan(config, program=str(self.program))
        self.assertEqual(sorted(g["root"] for g in plan["games"] if g["game"] == "t4"), sorted([str(self.t4), str(old)]))
        self.assertNotIn(str(foreign), [g["root"] for g in plan["games"]])

    def test_folders_it_did_not_create_stay(self):
        foreign = self.dir / "Pictures" / "tekken4"
        foreign.mkdir(parents=True)
        dev = managed_install(self.dir / "dev" / "T4", "t4")
        (dev / ".git").mkdir()
        # plan() now looks for installs beside the GIVEN program: use one with no installs next to it
        alone = self.dir / "Alone" / "OpenRecomp-FGC"
        alone.mkdir(parents=True)
        (alone / "release.json").write_text("{}", encoding="utf-8")
        plan = uninstall.plan(dict(roots=dict(t4=str(foreign))), program=str(alone))
        self.assertEqual(plan["games"], [])
        self.assertEqual(plan["skipped"][0]["why"], "not_ours")
        plan = uninstall.plan(dict(roots=dict(t4=str(dev))), program=str(alone))
        self.assertEqual(plan["skipped"][0]["why"], "unsafe")
        # a developer checkout of the launcher is never a program folder to remove
        (self.program / ".git").mkdir()
        self.assertEqual(uninstall.plan(self.config(), program=str(self.program))["program"], "")

    def test_setup_installs_go_through_setups_own_uninstaller(self):
        (self.program / uninstall.SETUP_UNINSTALLER).write_bytes(b"MZ")
        (self.program / uninstall.SETUP_RECORD).write_text("x", encoding="utf-8")
        started = []
        plan = uninstall.plan(self.config(), program=str(self.program))
        uninstall.execute(plan, start=lambda argv, **kw: started.append(argv))
        self.assertEqual(started, [[str(self.program / uninstall.SETUP_UNINSTALLER), "/S", "/removesettings"]])

    def test_remove_everything_keeps_the_iso_and_by_default_the_saves(self):
        (self.t4 / "save").mkdir()
        (self.t4 / "save" / "card0.ps2").write_bytes(b"memory card")
        (self.t4 / "Tekken 4 (USA).iso").write_bytes(b"disc")
        (self.t4 / "toolchain").mkdir()
        (self.t4 / "toolchain" / "big.bin").write_bytes(b"x")
        (self.t5 / "native" / "replays").mkdir(parents=True)
        (self.t5 / "native" / "replays" / "r1.t5rp").write_bytes(b"replay")
        (self.t5 / "game.pkg").write_bytes(b"pkg")
        (self.t5 / "x.rap").write_bytes(b"rap")
        started = []
        result = uninstall.execute(uninstall.plan(self.config(), program=str(self.program)),
                                   start=lambda argv, **kw: started.append(argv))
        self.assertFalse(self.t4.exists() or self.t5.exists() or self.home.exists())
        kept = [Path(p) for p in result["kept"]]
        names = sorted(p.name for p in kept)
        self.assertEqual(names, ["Tekken 4 (USA).iso", "game.pkg", "replays", "save", "x.rap"])
        self.assertTrue(all("OpenRecomp-kept-" in str(p) for p in kept))
        self.assertTrue((kept[names.index("save")] / "card0.ps2").is_file() or any((p / "card0.ps2").is_file() for p in kept))
        self.assertIn("cmd.exe\" /d /s /c \"ping", started[0])     # the zip copy's folder goes after the launcher
        self.assertIn('rmdir /s /q "' + str(self.program) + '""', started[0])

    def test_without_keeping_saves_only_the_disc_files_stay(self):
        (self.t4 / "save").mkdir()
        (self.t4 / "save" / "card0.ps2").write_bytes(b"memory card")
        (self.t4 / "disc.iso").write_bytes(b"disc")
        plan = dict(games=[dict(game="t4", root=str(self.t4))])
        result = uninstall.execute(plan, keep_saves=False, start=lambda argv, **kw: None)
        self.assertEqual([Path(p).name for p in result["kept"]], ["disc.iso"])

    def test_a_folder_without_the_marker_is_never_removed(self):
        foreign = self.dir / "other"
        foreign.mkdir()
        with self.assertRaises(ValueError):
            uninstall.remove_game("t4", str(foreign))
        self.assertTrue(foreign.is_dir())


class Dialog(unittest.TestCase):
    def nav(self):
        nav = Nav([])
        calls = []

        def on_uninstall(action, keep):
            calls.append((action, keep))
            return dict(games=[dict(game="t4", root=r"D:\Games\T4")], skipped=[], data=r"C:\data", program=r"D:\Games\OpenRecomp-FGC") \
                if action == "plan" else {}
        nav.on_uninstall = on_uninstall
        return nav, calls

    def test_list_first_then_keep_saves(self):
        nav, calls = self.nav()
        nav.uninstall_ask()
        self.assertEqual((nav.overlay, nav.confirm_kind), ("dialog", "uninstall_all"))
        view = {}
        nav._view_uninstall_dialog(view)
        self.assertEqual([o["label"] for o in view["dialog"]["options"]],
                         ["@cancel", "@uninstall.keep_saves", "@uninstall.everything"])
        nav._dialog("right")
        nav._dialog("confirm")
        self.assertEqual(calls, [("plan", None), ("run", True)])

    def test_cancel_is_the_first_focus_and_does_nothing(self):
        nav, calls = self.nav()
        nav.uninstall_ask()
        nav._dialog("confirm")
        self.assertEqual(calls, [("plan", None)])
        self.assertIsNone(nav.overlay)


if __name__ == "__main__":
    unittest.main()
