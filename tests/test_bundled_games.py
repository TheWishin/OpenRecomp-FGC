"""openrecomp/bundled_games.py: the games a full Setup carries are installed with the launcher's release checks.

The "games" are the inert test releases of release_fixtures (a few text files with the names the launcher checks),
signed with the test key; the test key counts only while OPENRECOMP_RELEASES_TEST names this PC.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from openrecomp import bundled_games as bg, game_releases as gr  # noqa: E402
import release_fixtures as rf  # noqa: E402

OTHER_SEED = bytes(range(1, 33))


def write_release(folder, name, zip_data, version, signer):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(zip_data)
    sums = f"{hashlib.sha256(zip_data).hexdigest()}  {name}\n".encode("ascii")
    (folder / "SHA256SUMS").write_bytes(sums)
    (folder / "SHA256SUMS.sig").write_bytes(signer(version, sums))
    return folder


def t5dr(base, version="1.2.0", seed=rf.TEST_SEED, zip_version=None):
    data = rf.zip_bytes(rf.t5dr_entries(zip_version or version))
    return write_release(base / "t5dr", f"T5DR-Online-{version}.zip", data, version,
                         lambda v, s: rf.t5dr_signature(v, s, seed))


def t4(base, tag="v0.1.0", seed=rf.TEST_SEED):
    data = rf.zip_bytes(rf.t4_entries(tag))
    return write_release(base / "t4", f"OpenRecomp-Tekken4-{tag}.zip", data, gr.plain(tag),
                         lambda v, s: rf.t4_signature(v, s, seed))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.src, self.parent = self.base / "bundle", self.base / "install"
        self.parent.mkdir()
        env = {gr.TEST_ENV: "http://127.0.0.1:9", gr.TEST_KEY_ENV: rf.public_key().hex(),
               "OPENRECOMP_HOME": str(self.base / "home")}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        # free space is this PC's: the checks are tested in test_game_setup; here the drive always has room
        space = mock.patch.object(gr, "free_space", return_value=1 << 50)
        space.start()
        self.addCleanup(space.stop)


class InstallTest(Base):
    def test_both_games_installed_with_markers_and_found_by_the_launcher(self):
        t5dr(self.src)
        t4(self.src)
        results = bg.install(str(self.src), str(self.parent))
        self.assertEqual({g: r["state"] for g, r in results.items()}, {"t5dr": "installed", "t4": "installed"})
        t5root, t4root = self.parent / "T5DR-Online-1.2.0", self.parent / "T4"
        self.assertEqual(results["t5dr"]["root"], str(t5root))
        self.assertEqual(results["t4"]["root"], str(t4root))
        from openrecomp.adapters.t5dr import install_root
        from openrecomp.adapters.t4_install import source_root
        self.assertEqual(install_root(str(t5root)), str(t5root))
        self.assertTrue(source_root(str(t4root)))
        for game, root, version in (("t5dr", t5root, "1.2.0"), ("t4", t4root, "0.1.0")):
            marker = json.loads((root / gr.MARKER).read_text(encoding="utf-8"))
            self.assertEqual((marker["game"], marker["version"], marker["installed_by"]), (game, version, "OpenRecomp-FGC"))
            self.assertTrue(gr.managed(game, str(root)))
            self.assertEqual(gr.installed_version(game, str(root)), version)
        self.assertFalse((self.parent / "OpenRecomp-FGC").exists())            # only the games' own folders
        self.assertFalse(any(p.name.startswith(".openrecomp-setup") for p in self.parent.iterdir()))
        # T4's release zip also carries a launcher: only its T4/ folder is unpacked
        self.assertEqual(sorted(p.name for p in self.parent.iterdir()), ["T4", "T5DR-Online-1.2.0"])

    def test_a_signature_by_another_key_installs_nothing(self):
        t5dr(self.src, seed=OTHER_SEED)
        t4(self.src, seed=OTHER_SEED)
        results = bg.install(str(self.src), str(self.parent))
        self.assertEqual({r["key"] for r in results.values()}, {"@setup.err_signature"})
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_without_the_test_address_the_test_key_does_not_count(self):
        t4(self.src)
        with mock.patch.dict(os.environ, {gr.TEST_ENV: ""}):
            results = bg.install(str(self.src), str(self.parent))
        self.assertEqual(results["t4"]["key"], "@setup.err_signature")

    def test_a_zip_changed_after_signing_is_refused(self):
        folder = t5dr(self.src)
        data = rf.zip_bytes(rf.t5dr_entries("1.2.0", extra=[("T5DR-Online-1.2.0/extra.txt", "changed")]))
        (folder / "T5DR-Online-1.2.0.zip").write_bytes(data)
        results = bg.install(str(self.src), str(self.parent))
        self.assertEqual(results["t5dr"]["key"], "@setup.err_checksum")
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_a_renamed_zip_does_not_pass_as_another_version(self):
        folder = t5dr(self.src)
        (folder / "T5DR-Online-1.2.0.zip").rename(folder / "T5DR-Online-1.3.0.zip")
        sums = (folder / "SHA256SUMS").read_text(encoding="ascii").replace("1.2.0.zip", "1.3.0.zip")
        (folder / "SHA256SUMS").write_text(sums, encoding="ascii")
        results = bg.install(str(self.src), str(self.parent))
        self.assertEqual(results["t5dr"]["key"], "@setup.err_signature")

    def test_unexpected_release_files_are_refused(self):
        folder = t4(self.src)
        (folder / "run.cmd").write_text("echo", encoding="ascii")
        results = bg.install(str(self.src), str(self.parent))
        self.assertEqual(results["t4"]["key"], "@setup.err_release")
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_a_game_already_there_is_left_alone(self):
        t5dr(self.src)
        t4(self.src)
        own = self.parent / "T4" / "tools" / "build_game.ps1"
        own.parent.mkdir(parents=True)
        own.write_text("the player's own T4", encoding="utf-8")
        old = self.parent / "T5DR-Online-1.1.9" / "launcher" / "core.py"
        old.parent.mkdir(parents=True)
        old.write_text("old", encoding="utf-8")
        results = bg.install(str(self.src), str(self.parent))
        self.assertEqual({g: r["state"] for g, r in results.items()}, {"t5dr": "present", "t4": "present"})
        self.assertEqual(own.read_text(encoding="utf-8"), "the player's own T4")
        self.assertEqual(sorted(p.name for p in self.parent.iterdir()), ["T4", "T5DR-Online-1.1.9"])

    def test_only_the_chosen_games(self):
        t5dr(self.src)
        t4(self.src)
        results = bg.install(str(self.src), str(self.parent), games=["t4"])
        self.assertEqual(list(results), ["t4"])
        self.assertEqual([p.name for p in self.parent.iterdir()], ["T4"])

    def test_the_opener_serves_only_the_release_files(self):
        folder = t4(self.src)
        get = bg.opener(str(folder))
        with get(None, bg.BUNDLE_URL + "SHA256SUMS") as r:
            self.assertEqual(r.read(), (folder / "SHA256SUMS").read_bytes())
        for url in ("https://github.com/TheWishin/Tekken4Recomp/releases/download/v0.1.0/SHA256SUMS",
                    bg.BUNDLE_URL + "../t5dr/SHA256SUMS", bg.BUNDLE_URL + "missing.zip", bg.BUNDLE_URL):
            with self.subTest(url=url), self.assertRaises(gr.ReleaseError):
                get(None, url)


class CommandLineTest(Base):
    def test_summary_in_the_players_language_and_exit_codes(self):
        t5dr(self.src)
        t4(self.src, seed=OTHER_SEED)
        summary, result = self.base / "summary.txt", self.base / "result.json"
        code = bg.main(["--from", str(self.src), "--parent", str(self.parent), "--lang", "de",
                        "--summary", str(summary), "--result", str(result)])
        self.assertEqual(code, 4)
        text = summary.read_text(encoding="utf-8")
        self.assertIn("Tekken 5 DR Online 1.2.0 ist installiert.", text)
        self.assertIn("Tekken 4 konnte nicht installiert werden", text)
        self.assertIn("Signatur", text)
        data = json.loads(result.read_text(encoding="utf-8"))
        self.assertEqual(data["results"]["t5dr"]["state"], "installed")
        self.assertEqual(data["results"]["t4"]["state"], "failed")

    def test_setups_language_codes(self):
        t4(self.src)
        summary = self.base / "summary.txt"
        self.assertEqual(bg.main(["--from", str(self.src), "--parent", str(self.parent), "--games", "t4",
                                  "--lang", "pt", "--summary", str(summary), "--status", str(self.base / "s.txt")]), 0)
        self.assertIn("Tekken 4 0.1.0 está instalado.", summary.read_text(encoding="utf-8"))

    def test_every_language_has_the_texts(self):
        from openrecomp import i18n
        for lang in i18n.LANGUAGES:
            with self.subTest(lang=lang):
                for key in ("bundle.installed", "bundle.present", "bundle.failed", "bundle.next"):
                    self.assertIn(key, i18n.catalog(lang))
                text = bg.summary(dict(t4=dict(state="failed", key="@setup.err_space", version="")), lang)
                self.assertIn(i18n.text(lang, "setup.err_space"), text)


class SetupContractTest(unittest.TestCase):
    """setup.cpp and make_installer agree with this module on names and on how the module is run."""

    def test_names_match(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import make_installer as mi
        setup = (ROOT / "tools" / "installer" / "setup.cpp").read_text(encoding="utf-8")
        self.assertIn(f'GAMES_DIR = L"{mi.BUNDLE_DIR}"', setup)
        self.assertIn('GAME_IDS[] = {L"t5dr", L"t4"}', setup)
        self.assertEqual(mi.BUNDLE_GAMES, bg.GAMES)
        for flag in ("-m openrecomp.bundled_games", "--from", "--parent", "--games", "--lang", "--summary", "--status"):
            self.assertIn(flag, setup)
        # the games' release files never become launcher files of the install record
        body = setup[setup.index("// 2. The files moved into place"):setup.index("if (!write_record(folder, rec))")]
        self.assertIn("if (is_bundle_entry(e->path)) continue;", body)


if __name__ == "__main__":
    unittest.main()
