"""Build-tool recovery and verified downloads are explained in all seven player languages."""
import string
import unittest

from openrecomp import i18n


KEYS = (
    "t4.tools.install_hint", "t4.tools.install_text", "t4.tools.no_winget",
    "t4.tools.install_progress", "build.tools_installing", "build.tools_help_text",
    "t4.tools.download_failed", "t4.tools.verification_failed", "t4.tools.elevation_cancelled",
    "t4.tools.install_unavailable", "t4.tools.downloading", "t4.tools.verifying", "t4.tools.authorizing",
)


class BuildToolCatalogs(unittest.TestCase):
    def test_fallback_and_recovery_are_localized_with_matching_parameters(self):
        english = i18n.catalog("en")
        formatter = string.Formatter()
        for language in i18n.LANGUAGES:
            catalog = i18n.catalog(language)
            for key in KEYS:
                with self.subTest(language=language, key=key):
                    self.assertIn(key, catalog)
                    self.assertTrue(catalog[key].strip())
                    expected = {name for _literal, name, _spec, _conversion in formatter.parse(english[key]) if name}
                    actual = {name for _literal, name, _spec, _conversion in formatter.parse(catalog[key]) if name}
                    self.assertEqual(actual, expected)
                    self.assertNotIn("Microsoft Store", catalog[key])
                    self.assertNotIn("App Installer", catalog[key])
                    if language != "en":
                        self.assertNotEqual(catalog[key], english[key])

    def test_progress_identifies_the_tool_and_help_keeps_the_manual_route(self):
        for language in i18n.LANGUAGES:
            for key in ("t4.tools.install_progress", "build.tools_installing"):
                with self.subTest(language=language, key=key):
                    progress = i18n.text(language, key, done=2, total=4, name="Ninja")
                    self.assertIn("2", progress)
                    self.assertIn("4", progress)
                    self.assertIn("Ninja", progress)
                    self.assertNotIn("{", progress)
            help_text = i18n.text(language, "build.tools_help_text", names="Ninja")
            for name in ("Visual Studio 2022 Build Tools", "Git", "CMake", "Ninja", "winget"):
                self.assertIn(name, help_text)
            self.assertTrue(i18n.text(language, "t4.tools.copy_commands"))


if __name__ == "__main__":
    unittest.main()
