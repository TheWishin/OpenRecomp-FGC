"""Offline author-manifest integration, with synthetic metadata and no game code."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from openrecomp import adapters, manifest as mf
from openrecomp.game_library import Library


ROOT = Path(__file__).parents[1]


def author_manifest(**changes):
    return dict(dict(schema_version=1, id="example", title="Example", numeral="E",
                     accent="#123456", adapter="generic", platform="PC", exe="game.exe",
                     author="Example Author", repository="example/recomp", license="MIT",
                     credits=["Example Author"]), **changes)


class GenericIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "author"
        self.source.mkdir()
        self.home = self.root / "launcher-data"
        patch = mock.patch.dict("os.environ", OPENRECOMP_HOME=str(self.home))
        patch.start()
        self.addCleanup(patch.stop)
        self.config = {}

    def write_manifest(self, **changes):
        path = self.source / "openrecomp-game.json"
        path.write_text(json.dumps(author_manifest(**changes)), encoding="utf-8")

    def test_preview_then_registration_uses_generic_without_starting_any_code(self):
        self.write_manifest()
        library = Library(self.config)
        with mock.patch("subprocess.Popen") as start:
            preview = library.preview(str(self.source))
            self.assertEqual(preview["author"], "Example Author")
            self.assertEqual(preview["warning"], "@library.third_party")
            self.assertEqual(self.config, {})
            self.assertFalse(self.home.exists())
            registered = library.accept(preview)
            manifests, problems = mf.load_all([mf.user_games_dir()])
            self.assertEqual(problems, [])
            self.assertEqual(manifests, [registered])
            game = adapters.make(manifests[0], self.config)
            self.assertEqual(game.m["adapter"], "generic")
            self.assertEqual(Path(game.exe()), self.source / "game.exe")
            self.assertEqual(Path(self.config["roots"]["example"]), self.source)
            start.assert_not_called()

    def test_removing_a_registration_preserves_author_folder_and_other_games(self):
        self.write_manifest()
        marker = self.source / "player-owned.txt"
        marker.write_text("synthetic player-owned data", encoding="utf-8")
        self.config["roots"] = {"t5dr": "other-install"}
        library = Library(self.config)
        library.accept(library.preview(str(self.source)))
        self.assertTrue(library.remove("example"))
        self.assertEqual(marker.read_text(encoding="utf-8"), "synthetic player-owned data")
        self.assertTrue((self.source / "openrecomp-game.json").is_file())
        self.assertEqual(self.config["roots"]["t5dr"], "other-install")
        self.assertNotIn("example", self.config.get("roots", {}))
        self.assertFalse((Path(mf.user_games_dir()) / "example.json").exists())

    def test_native_adapter_cannot_be_selected_by_an_author_manifest(self):
        for adapter in ("t4", "t5dr"):
            self.write_manifest(adapter=adapter)
            with self.subTest(adapter=adapter), self.assertRaises(mf.ManifestError):
                Library(self.config).preview(str(self.source))
        self.assertEqual(self.config, {})

    def test_release_inventory_contains_the_complete_manifest_feature(self):
        spec = importlib.util.spec_from_file_location("generic_package", ROOT / "tools/package_release.py")
        package = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(package)
        required = {"openrecomp/game_library.py", "openrecomp/game_updates.py",
                    "openrecomp/nav_library.py", "openrecomp/adapters/base.py",
                    "openrecomp/data/known_games.json", "docs/ADD_YOUR_GAME.md"}
        self.assertEqual(required - package.SOURCE_FILES, set())


if __name__ == "__main__":
    unittest.main()
