"""The passive promotion cue uses a translated label in every launcher language."""
import json
from pathlib import Path
import unittest

from openrecomp import i18n


class VibeCatalogs(unittest.TestCase):
    def test_rank_up_label_exists_in_each_catalog_and_localizes_the_view(self):
        for language in i18n.LANGUAGES:
            with self.subTest(language=language):
                path = Path(i18n.__file__).parent / (language + ".json")
                catalog = json.loads(path.read_text(encoding="utf-8"))
                label = catalog.get("vibe.rank_up")
                self.assertIsInstance(label, str)
                self.assertTrue(label.strip())
                self.assertNotEqual(label, "vibe.rank_up")
                self.assertEqual(i18n.localize({"promotion": {"label": "@vibe.rank_up"}}, language),
                                 {"promotion": {"label": label}})


if __name__ == "__main__":
    unittest.main()
