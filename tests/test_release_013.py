"""0.1.3 release tools: a portable T4 stage in the bundle, unsigned candidates. Synthetic data only."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import t4_test_bundle as bundle  # noqa: E402
from tools import make_release  # noqa: E402

MARKERS = [("T4/toolchain/toolchain.json", b"{}"), ("T4/release.json", b'{"version": "0.1.3"}')]


class PortableStage(unittest.TestCase):
    def test_a_stage_is_recognized_by_its_two_markers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertFalse(bundle.portable_t4(root))
            (root / "toolchain").mkdir()
            (root / "toolchain" / "toolchain.json").write_text("{}", encoding="utf-8")
            self.assertFalse(bundle.portable_t4(root))
            (root / "release.json").write_text("{}", encoding="utf-8")
            self.assertTrue(bundle.portable_t4(root))

    def test_the_bare_user_name_is_ignored_only_inside_the_portable_t4(self):
        terms = ["someuser", r"C:\Users\someuser"]
        with mock.patch.dict(os.environ, USERNAME="someuser"):
            # Python's pydoc.py credits a person who may share the user's first name: fine inside T4/python ...
            bundle.private_terms_for(MARKERS + [("T4/python/Lib/pydoc.py", b"Someuser Burnette")], terms)
            # ... never in the launcher part, and the profile path never anywhere.
            with self.assertRaises(ValueError):
                bundle.private_terms_for(MARKERS + [("OpenRecomp-FGC/x.py", b"someuser")], terms)
            with self.assertRaises(ValueError):
                bundle.private_terms_for(MARKERS + [("T4/docs/a.md", b"C:\\Users\\someuser\\x")], terms)
            # without the portable markers every term counts everywhere (old source bundles)
            with self.assertRaises(ValueError):
                bundle.private_terms_for([("T4/python/Lib/pydoc.py", b"Someuser Burnette")], terms)


class UnsignedCandidate(unittest.TestCase):
    def test_notes_say_unsigned_instead_of_rehearsal(self):
        self.assertIn("UNSIGNED CANDIDATE", make_release._candidate_line(dict(unsigned=True, rehearsal=True)))
        self.assertIn("REHEARSAL", make_release._candidate_line(dict(unsigned=False, rehearsal=True)))
        self.assertEqual(make_release._candidate_line(dict(unsigned=False, rehearsal=False)), "")

    def test_the_owner_gets_both_signing_commands_without_any_key(self):
        text = make_release.sign_commands(Path(r"D:\out"), "v0.1.3", "v0.1.3", "stable")
        self.assertIn("release_sign.py sign --key-file <keys>", text)
        self.assertIn("--channel stable --version v0.1.3", text)
        self.assertIn("release_sign.py sign-t4 --key-file <keys>", text)
        self.assertIn("--version 0.1.3 ", text)
        self.assertIn(str(Path(r"D:\out") / "t4" / "SHA256SUMS.sig"), text)


class PreReleaseFirst(unittest.TestCase):
    """Owner's rule: every release goes out as a pre-release first; the owner marks it latest after his test."""

    def text(self):
        return make_release.commands(Path(r"D:\out"), "v0.1.3", "v0.1.3", ["a.zip"], ["t.zip"], "a" * 40, "b" * 40, True)

    def test_both_releases_are_created_and_published_as_pre_releases(self):
        lines = [line for line in self.text().splitlines() if line.startswith("gh release")]
        launcher = [line for line in lines if "OpenRecomp-FGC" in line]
        t4 = [line for line in lines if "Tekken4Recomp" in line]
        self.assertIn("--draft --prerelease", launcher[0])
        self.assertTrue(launcher[1].endswith("--draft=false --prerelease"))
        self.assertTrue(launcher[2].endswith("--prerelease=false --latest"))       # the owner's step after his test
        self.assertIn("--draft --prerelease", t4[0])
        self.assertTrue(t4[1].endswith("--draft=false --prerelease"))
        self.assertNotIn("not as a pre-release", self.text())

    def test_player_notes_come_first(self):
        notes = make_release.notes("t4", tag="v0.1.3", commit="a" * 40, t4_commit="b" * 40, key_id="k", sums={},
                                   rehearsal=False, unsigned=False, intro="Update the launcher first.")
        self.assertTrue(notes.startswith("Tekken 4 recompiled (USA SLUS-20328), v0.1.3\n\nUpdate the launcher first."))
        from openrecomp.game_releases import release_notes
        self.assertTrue(release_notes(notes).startswith("Tekken 4 recompiled (USA SLUS-20328), v0.1.3 Update the launcher"))


if __name__ == "__main__":
    unittest.main()
