"""0.1.3: one T4 folder for Play, Build and Online, said on the page; why another player's build differs.

Synthetic installs only (marker files, no game data, no build, no server).
"""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp import adapters
from openrecomp.adapters import t4, t4_install
from openrecomp.adapters.base import Missing
from openrecomp.adapters.t4_online import T4Online


MANIFEST = dict(id="t4", adapter="t4", short="T4", title="Tekken 4", locations=[])


def source_tree(root):
    for name in t4_install.SOURCE_TOOLS:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# synthetic source marker\n", encoding="utf-8")
    for name in t4_install.SOURCE_DIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def portable_release(root, version="0.1.3"):
    source_tree(root)
    (root / "toolchain").mkdir(parents=True, exist_ok=True)
    (root / "toolchain" / "toolchain.json").write_text("{}", encoding="utf-8")
    (root / "release.json").write_text(json.dumps(dict(version=version, path="B")), encoding="utf-8")
    return root


class OneFolder(unittest.TestCase):
    def setUp(self):
        self.dir = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_T4_ROOT=""))
        self.beside = source_tree(self.dir / "beside" / "T4")
        self.enterContext(mock.patch.object(t4, "DEFAULT_SOURCE_ROOT", str(self.beside)))

    def test_the_chosen_folder_is_the_only_one_and_never_falls_back(self):
        chosen = portable_release(self.dir / "chosen" / "T4")
        self.assertEqual(t4.find_root(MANIFEST, dict(roots=dict(t4=str(chosen)))), str(chosen.resolve()))
        # The chosen folder moved/deleted: NOT the T4 beside the launcher, not the developer override.
        with mock.patch.dict(os.environ, OPENRECOMP_T4_ROOT=str(self.beside)):
            self.assertIsNone(t4.find_root(MANIFEST, dict(roots=dict(t4=str(self.dir / "gone")))))

    def test_without_a_choice_the_bundle_folder_beside_the_launcher_is_used(self):
        self.assertEqual(t4.find_root(MANIFEST, {}), str(self.beside.resolve()))

    def test_a_chosen_folder_that_is_no_install_is_said_with_its_path(self):
        wrong = self.dir / "Pictures" / "tekken4"
        wrong.mkdir(parents=True)
        config = dict(roots=dict(t4=str(wrong)))
        self.assertEqual(t4.configured_problem(MANIFEST, config), str(wrong))
        game = adapters.make(MANIFEST, config)
        self.assertIsInstance(game, Missing)
        note = game.sources()[0]["note"]
        self.assertEqual(note["_text"], "t4.folder_not_install")
        self.assertEqual(note["_values"]["folder"], str(wrong))

    def test_release_version_and_folder_problems(self):
        release = portable_release(self.dir / "new" / "T4", "0.1.3")
        self.assertEqual(t4.release_version(str(release)), "0.1.3")
        self.assertEqual(t4.folder_problem(str(release)), "")
        old = source_tree(self.dir / "old" / "T4")                    # the 0.1.2 source-only bundle
        self.assertEqual(t4.folder_problem(str(old)), "@t4.folder_old")
        broken = portable_release(self.dir / "broken" / "T4")
        os.remove(broken / "toolchain" / "toolchain.json")
        self.assertEqual(t4.folder_problem(str(broken)), "@t4.folder_incomplete")
        dev = source_tree(self.dir / "dev" / "T4")
        (dev / ".git").mkdir()
        self.assertEqual(t4.folder_problem(str(dev)), "")             # a developer checkout builds as before

    def test_status_names_folder_and_version(self):
        release = portable_release(self.dir / "new" / "T4", "0.1.3")
        holder = SimpleNamespace(root=str(release), s={}, problems=lambda: [], message=t4.T4.message,
                                 release_version=lambda: t4.release_version(str(release)),
                                 folder_problem=lambda: t4.folder_problem(str(release)))
        status = t4.T4.status(holder)
        self.assertEqual(status["folder"], str(release))
        self.assertEqual(status["version"]["_values"]["release"], "0.1.3")


class BuildNotes(unittest.TestCase):
    """The lobby list carries each player's build id and release: the launcher says why a build differs."""

    def holder(self, mine_release="0.1.3", mine_build="a" * 16):
        holder = SimpleNamespace(message=t4.T4.message, _t4_release=lambda: mine_release,
                                 _online_client=SimpleNamespace(build=SimpleNamespace(build_id=mine_build)))
        holder._online_same_build = lambda player: T4Online._online_same_build(holder, player)
        return holder

    def test_same_build_has_no_note(self):
        self.assertIsNone(T4Online._t4_build_note(self.holder(), dict(build="a" * 16, release="0.1.3")))

    def test_other_release_is_another_version_with_both_numbers(self):
        note = T4Online._t4_build_note(self.holder(), dict(build="b" * 16, release="0.1.2"))
        self.assertEqual(note["_text"], "t4.mismatch_version")
        self.assertEqual(note["_values"], dict(theirs="0.1.2", mine="0.1.3"))

    def test_same_release_other_build_is_other_files_or_compiler(self):
        note = T4Online._t4_build_note(self.holder(), dict(build="b" * 16, release="0.1.3"))
        self.assertEqual(note, "@t4.mismatch_same_version")

    def test_a_strange_release_string_is_never_shown(self):
        note = T4Online._t4_build_note(self.holder(), dict(build="b" * 16, release="<script>"))
        self.assertEqual(note["_values"]["theirs"], "?")


class MicrosoftNote(unittest.TestCase):
    def adapter(self, bundled, ready, folder=""):
        core = SimpleNamespace(source_only=False, bundled_toolchain=lambda: bundled, sysroot_ready=lambda: ready)
        holder = SimpleNamespace(core=core, folder_problem=lambda: folder)
        holder._bundled_release = lambda: t4.T4._bundled_release(holder)
        return holder

    def test_the_licence_line_shows_until_the_headers_are_there(self):
        self.assertEqual(t4.T4.microsoft_note(self.adapter(True, False)), "@t4.microsoft_note")
        self.assertEqual(t4.T4.microsoft_note(self.adapter(True, True)), "")
        self.assertEqual(t4.T4.microsoft_note(self.adapter(False, False)), "")

    def test_an_old_folder_is_said_first(self):
        self.assertEqual(t4.T4.microsoft_note(self.adapter(False, False, "@t4.folder_old")), "@t4.folder_old")


if __name__ == "__main__":
    unittest.main()


class FolderRowAndLongPaths(unittest.TestCase):
    def test_the_folder_row_names_the_folder_in_use(self):
        holder = SimpleNamespace(root=r"D:\Games\T4", s={}, iso_note="", _source_state=dict(running=False, result="", id="", ok=False),
                                 core=SimpleNamespace(effective_iso=lambda s: ""), _needs_toolchain=lambda: False,
                                 folder_problem=lambda: "")
        rows = t4.T4.sources(holder)
        folder = [row for row in rows if row["id"] == "folder"][0]
        self.assertEqual(folder["value"], r"D:\Games\T4")
        self.assertTrue(folder["ok"])
        self.assertEqual(folder["hint"], "@t4.folder_change_hint")
        self.assertEqual(rows[0]["id"], "iso")

    def test_long_install_folders_get_a_note_and_too_long_ones_are_refused(self):
        from openrecomp import game_setup
        setup = game_setup.GameSetup({}, worker=lambda fn: fn())
        setup.offers["t4"] = dict(version="0.1.3", tag="v0.1.3", zip=dict(size=1))
        with mock.patch.object(game_setup.gr, "check_target", return_value=""), \
                mock.patch.object(game_setup.gr, "space_needed", return_value=1), \
                mock.patch.object(game_setup.gr, "free_space", return_value=10):
            for parent, long, problem in (("C:\Games", False, ""), ("D:\\" + "x" * 70, True, ""),
                                          ("D:\\" + "x" * 130, True, "@setup.path_too_long")):
                with mock.patch.object(game_setup.gr, "target_folder", return_value=parent + "\T4"):
                    space = setup.space("t4", parent)
                self.assertEqual((space["long"], space["problem"]), (long, problem), parent[:12])
