"""Direct-IP beta copy is complete and translated without opening a window."""
import re
import unittest

from openrecomp import i18n


BETA_KEYS = (
    "direct_title", "direct_hint", "direct_host", "direct_join",
    "direct_address", "direct_address_hint", "direct_check", "direct_logs",
    "direct_back", "direct_start", "direct_role", "direct_checks",
    "direct_checking", "direct_checked", "direct_invalid_address",
    "direct_identity_failed", "direct_build_mismatch", "direct_compiler_mismatch",
    "direct_iso_mismatch", "direct_unreachable", "direct_failed",
    "direct_check_required", "direct_logs_saved", "direct_logs_failed",
    "direct_check_build", "direct_check_compiler", "direct_check_iso",
    "direct_check_udp", "direct_pending", "direct_match", "direct_passed",
    "direct_finished", "net_diagnostics", "net_diagnostics_hint",
    "net_diagnostics_lead", "direct_role_host", "direct_role_join",
)


class T4BetaCatalogs(unittest.TestCase):
    def test_direct_ip_copy_exists_without_english_fallback(self):
        english = i18n.catalog("en")
        for language in i18n.LANGUAGES:
            catalog = i18n.catalog(language)
            for suffix in BETA_KEYS:
                key = "t4." + suffix
                with self.subTest(language=language, key=key):
                    self.assertIn(key, catalog)
                    self.assertTrue(catalog[key].strip())
                    # "Host" is also the ordinary German networking term.
                    if language != "en" and (language, suffix) != ("de", "direct_role_host"):
                        self.assertNotEqual(catalog[key], english[key])
                    self.assertEqual(re.findall(r"\{[^{}]*\}", catalog[key]),
                                     re.findall(r"\{[^{}]*\}", english[key]))

    def test_checks_keep_the_protocol_and_disc_requirements(self):
        for language in i18n.LANGUAGES:
            catalog = i18n.catalog(language)
            with self.subTest(language=language):
                self.assertIn("IPv4", catalog["t4.direct_invalid_address"])
                self.assertIn("MSVC", catalog["t4.direct_compiler_mismatch"])
                self.assertIn("1.00", catalog["t4.direct_iso_mismatch"])
                self.assertIn("UDP", catalog["t4.direct_unreachable"])
                self.assertIn("7400", catalog["t4.direct_unreachable"])

    def test_controller_action_labels_stay_compact(self):
        labels = (
            "direct_host", "direct_join", "direct_address", "direct_check",
            "direct_logs", "direct_back", "direct_start", "net_diagnostics",
        )
        for language in i18n.LANGUAGES:
            catalog = i18n.catalog(language)
            for suffix in labels:
                with self.subTest(language=language, key=suffix):
                    self.assertLessEqual(len(catalog["t4." + suffix]), 32)


if __name__ == "__main__":
    unittest.main()
