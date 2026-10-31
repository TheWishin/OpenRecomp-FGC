"""The public author contract and disabled catalog entry stay usable."""
import json
from pathlib import Path
import re
import unittest

from openrecomp import manifest


ROOT = Path(__file__).resolve().parents[1]


class GenericAuthorDocsTests(unittest.TestCase):
    def test_documented_manifest_is_a_valid_public_v1_manifest(self):
        text = (ROOT / "docs/ADD_YOUR_GAME.md").read_text(encoding="utf-8-sig")
        examples = re.findall(r"```json\s*\n(.*?)\n```", text, re.S)
        self.assertEqual(len(examples), 1)
        example = manifest.validate_external(json.loads(examples[0]))
        self.assertEqual(example["schema_version"], 1)
        self.assertEqual(example["adapter"], "generic")
        self.assertEqual(example["online"]["mode"], "own")
        self.assertEqual(example["releases"]["verification"]["method"], "github-sha256")

    def test_known_catalog_keeps_tt2_unconfigured_and_outside_loadable_manifests(self):
        path = ROOT / "openrecomp/data/known_games.json"
        catalog = json.loads(path.read_text(encoding="utf-8-sig"))
        self.assertEqual(catalog["schema_version"], 1)
        entry = next(game for game in catalog["games"] if game["id"] == "tt2")
        self.assertEqual(entry["title"], "Tekken Tag Tournament 2")
        self.assertIsNone(entry["repository"])
        self.assertEqual(entry["status"], "placeholder")
        manifests, problems = manifest.load_all([ROOT / "games"])
        self.assertEqual(problems, [])
        self.assertNotIn("tt2", {item["id"] for item in manifests})

    def test_readme_links_author_contract_without_obsolete_absolute_exe_example(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        section = text.split("## Add a game", 1)[1].split("## Layout", 1)[0]
        self.assertIn("docs/ADD_YOUR_GAME.md", section)
        self.assertIn("owner/repo", section)
        self.assertIn("local folder", section)
        self.assertNotIn('"env"', section)
        self.assertNotIn('D:\\\\MyGame', section)


if __name__ == "__main__":
    unittest.main()
