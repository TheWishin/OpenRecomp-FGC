import json
import os
import re
import unittest
from pathlib import Path
from unittest import mock

from openrecomp import i18n
from openrecomp.nav import Game, Nav


ROOT = Path(__file__).parents[1]


class FakeAdapter:
    native_label = ""

    def ready(self):
        return True

    def status(self):
        return {"status": "Ready", "version": "1", "players": "No", "last": "Never", "detail": "Ready."}

    def running(self):
        return False

    def hero(self):
        return ""

    def recent_results(self):
        return []

    def settings(self):
        return []

    def quick_settings(self):
        return []


def game():
    manifest = {"id": "test", "short": "Test", "accent": "#ffffff", "numeral": "T", "title": "Test", "subtitle": "", "sections": ["play"]}
    return Game(manifest, FakeAdapter())


class Catalogs(unittest.TestCase):
    def test_catalogs_have_equal_keys_and_placeholders(self):
        catalogs = {code: json.loads((ROOT / "openrecomp" / "i18n" / (code + ".json")).read_text(encoding="utf-8")) for code in i18n.LANGUAGES}
        keys = set(catalogs["en"])
        for code, entries in catalogs.items():
            self.assertEqual(set(entries), keys, code)
            for key in keys:
                self.assertEqual(set(re.findall(r"{(.*?)}", entries[key])), set(re.findall(r"{(.*?)}", catalogs["en"][key])), (code, key))

    def test_missing_translation_falls_back_to_english(self):
        english = i18n.catalog("en")
        german = i18n.catalog("de")
        german.pop("quick_access")
        with mock.patch("openrecomp.i18n.catalog", side_effect=lambda code: english if code == "en" else german):
            self.assertEqual(i18n.text("de", "quick_access"), "Quick access")

    def test_switching_language_changes_the_view(self):
        nav = Nav([game()], language="en")
        nav.act("social")
        before = nav.view()
        nav.act("confirm")
        after = nav.view()
        self.assertNotEqual(before, after)
        self.assertEqual(after["drawer"]["rows"][0]["value"], "Deutsch")

    def test_qml_has_no_player_facing_literals(self):
        forbidden = ("Quick access", "Recent sets", "Choose your fighter", "Your main:", "Folder", "File", "MAIN")
        for path in (ROOT / "openrecomp" / "ui").glob("*.qml"):
            source = path.read_text(encoding="utf-8")
            self.assertFalse(any(text in source for text in forbidden), path.name)


if __name__ == "__main__":
    unittest.main()
