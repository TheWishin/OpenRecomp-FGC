"""Build comparisons use inert metadata, never an installed game or executable."""
import io
import os
import unittest
from unittest import mock

from openrecomp.adapters.t5_compatibility import build_compatibility, rebuild_needed


class BuildCompatibilityTests(unittest.TestCase):
    def compare(self, release, stamp):
        with mock.patch("builtins.open", mock.mock_open(read_data=stamp)) as opened:
            result = rebuild_needed(release, "chosen-output")
        opened.assert_called_once_with(
            os.path.join("chosen-output", "build", "t5dr_build.json"), encoding="utf-8")
        return result

    def test_different_launcher_versions_with_same_game_code_need_no_rebuild(self):
        self.assertIs(self.compare(dict(version="1.2.0", code_id="aaaaaaaaaaaaaaaa"),
                                   '{"version":"1.1.9","code_id":"aaaaaaaaaaaaaaaa"}'), False)

    def test_same_launcher_version_with_different_code_needs_rebuild(self):
        self.assertIs(self.compare(dict(version="1.1.9", code_id="bbbbbbbbbbbbbbbb"),
                                   '{"version":"1.1.9","code_id":"aaaaaaaaaaaaaaaa"}'), True)

    def test_unknown_release_identity_does_not_even_read_build_stamp(self):
        for release in ({}, None, [], {"code_id": ""}, {"code_id": " "}, {"code_id": 4}):
            with self.subTest(release=release), mock.patch("builtins.open") as opened:
                self.assertIsNone(rebuild_needed(release, "chosen-output"))
                opened.assert_not_called()

    def test_unknown_output_directory_does_not_read_relative_stamp(self):
        with mock.patch("builtins.open") as opened:
            self.assertIsNone(rebuild_needed({"code_id": "aaaaaaaaaaaaaaaa"}, ""))
            opened.assert_not_called()

    def test_missing_and_unreadable_stamp_are_unknown(self):
        for error in (FileNotFoundError, PermissionError):
            with self.subTest(error=error), mock.patch("builtins.open", side_effect=error):
                self.assertIsNone(rebuild_needed({"code_id": "aaaaaaaaaaaaaaaa"}, "chosen-output"))

    def test_invalid_or_incomplete_stamp_never_claims_compatibility(self):
        for stamp in ("{", "null", "[]", "{}", '{"code_id":null}', '{"code_id":9}',
                      '{"code_id":""}', '{"code_id":" "}'):
            with self.subTest(stamp=stamp):
                self.assertIsNone(self.compare({"code_id": "aaaaaaaaaaaaaaaa"}, stamp))

    def test_status_is_explicit_for_all_three_comparisons(self):
        for value, status in ((False, "same"), (True, "different"), (None, "unknown")):
            with self.subTest(value=value), mock.patch(
                    "openrecomp.adapters.t5_compatibility.rebuild_needed", return_value=value):
                self.assertEqual(build_compatibility({}, "chosen-output"), status)

    def test_metadata_is_read_only(self):
        stream = io.StringIO('{"code_id":"aaaaaaaaaaaaaaaa"}')
        stream.write = mock.Mock(side_effect=AssertionError("metadata must stay read-only"))
        with mock.patch("builtins.open", return_value=stream) as opened:
            self.assertFalse(rebuild_needed({"code_id": "aaaaaaaaaaaaaaaa"}, "chosen-output"))
        opened.assert_called_once()
        stream.write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
