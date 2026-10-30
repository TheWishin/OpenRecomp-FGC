"""Actionable T4 first-run copy in every catalog, without a game or window."""
import unittest

from openrecomp import i18n


FIRST_RUN_KEYS = (
    "iso.checking", "iso.refused", "iso.changed", "iso.check_failed",
    "t4.installing", "t4.work_busy", "t4.build_start_failed",
    "t4.build_cancelled", "t4.build_finished", "t4.build_incomplete",
    "t4.no_build_output", "t4.build_failed", "t4.step_failed",
    "t4.play_failed", "t4.portable_required", "t4.complete_release",
    "t4.install_next", "t4.build_next", "t4.play_hint", "t4.build_wait",
    "updates.waiting", "t4.returning", "t4.quit_busy",
    "t4.online_setup_hint", "t4.online_name_required",
    "t4.onboarding_hint", "t4.onboarding_source",
    "t4.build_output",
)


class FirstRunCatalogs(unittest.TestCase):
    def test_first_run_guidance_is_present_and_translated_in_every_catalog(self):
        english = i18n.catalog("en")
        for code in i18n.LANGUAGES:
            catalog = i18n.catalog(code)
            for key in FIRST_RUN_KEYS:
                with self.subTest(code=code, key=key):
                    self.assertIn(key, catalog)
                    self.assertTrue(catalog[key].strip())
                    if code != "en":
                        self.assertNotEqual(catalog[key], english[key])

    def test_error_recovery_comes_before_unbounded_native_diagnostic(self):
        for code in i18n.LANGUAGES:
            for key in ("iso.refused", "iso.check_failed", "t4.build_start_failed",
                        "t4.build_failed", "t4.play_failed"):
                with self.subTest(code=code, key=key):
                    template = i18n.catalog(code)[key]
                    self.assertTrue(template.endswith("{error}"))
                    self.assertGreater(template.index("{error}"), 15)

    def test_disc_and_return_guidance_keep_identifiers_in_every_language(self):
        for code in i18n.LANGUAGES:
            for key in ("iso.checking", "iso.refused", "t4.install_next", "t4.onboarding_hint"):
                with self.subTest(code=code, key=key):
                    self.assertIn("SLUS-20328", i18n.catalog(code)[key])
            for key in ("t4.build_next", "t4.play_hint"):
                with self.subTest(code=code, key=key):
                    template = i18n.catalog(code)[key]
                    self.assertIn("View + Menu", template)
                    self.assertIn("Share + Options", template)
                    self.assertIn("2", template)


if __name__ == "__main__":
    unittest.main()
