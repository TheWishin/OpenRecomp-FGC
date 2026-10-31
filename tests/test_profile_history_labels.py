import unittest
from types import SimpleNamespace

from openrecomp import i18n, nav_profiles


class ProfileHistoryLabels(unittest.TestCase):
    def history_details(self, **record):
        state = dict(profile=dict(history=[dict(opponent="Rival", **record)]))
        rows = nav_profiles._profile_rows(None, SimpleNamespace(), state, None)
        return next(row["detail"]["rows"] for row in rows if row.get("id") == "profile_history:0")

    def test_history_status_and_reason_use_complete_catalog_keys(self):
        statuses = ("confirmed", "onesided", "forfeit", "resolved", "disputed", "void", "training")
        reasons = ("desync", "too_short", "disputed", "crash", "early_quit", "quit", "disconnect",
                   "connection", "no_report", "both_left", "timeout", "crash_repeat", "early_quit_repeat",
                   "no_report_repeat", "score_mismatch", "no_result", "set_restart", "no_return")
        for field, codes in (("status", statuses), ("reason", reasons)):
            for code in codes:
                with self.subTest(field=field, code=code):
                    details = self.history_details(**{field: code})
                    value = next(row["v"] for row in details if row["k"] == "@online.history_" + field)
                    self.assertEqual(value, "@online.history_" + code)
                    for language in i18n.LANGUAGES:
                        self.assertIn(value[1:], i18n.catalog(language))

    def test_unknown_history_codes_do_not_become_catalog_keys(self):
        details = self.history_details(status="private-status", reason="@online.logout")
        self.assertFalse(any(row["k"] in ("@online.history_status", "@online.history_reason") for row in details))


if __name__ == "__main__":
    unittest.main()
