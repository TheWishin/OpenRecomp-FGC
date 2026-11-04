"""Release gating uses inert reports and runtimes; nothing is packaged or run."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

import tools
from tools import make_release as release


class PlayerMatrixReleaseTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory(dir=Path(__file__).parent)))
        self.args = argparse.Namespace(rehearsal=False, matrix_report=None, skip_matrix=False)
        self.runtime = self.root / "runtime"

    def test_missing_report_is_refused(self):
        with self.assertRaisesRegex(release.ReleaseFailed, "passing player matrix"):
            release.check_player_matrix(self.args, "commit", self.runtime)

    def test_skip_requires_both_rehearsal_and_explicit_test_environment(self):
        self.args.skip_matrix = True
        for rehearsal, switch in ((False, ""), (True, ""), (False, "1"), (True, "true")):
            with self.subTest(rehearsal=rehearsal, switch=switch):
                self.args.rehearsal = rehearsal
                with mock.patch.dict(os.environ, OPENRECOMP_RELEASE_TESTS=switch):
                    with self.assertRaisesRegex(release.ReleaseFailed, "only for tests"):
                        release.check_player_matrix(self.args, "commit", self.runtime)
        self.args.rehearsal = True
        with mock.patch.dict(os.environ, OPENRECOMP_RELEASE_TESTS="1"):
            self.assertEqual(release.check_player_matrix(self.args, "commit", self.runtime),
                             dict(status="skipped-for-tests"))

    def test_validator_receives_the_exact_commit_source_and_runtime(self):
        report = self.root / "report.json"
        report.write_text(json.dumps(dict(schema=1)), encoding="utf-8")
        self.args.matrix_report = report
        validator = mock.Mock(return_value=dict(cases=15))
        with mock.patch.object(tools, "player_matrix", types.SimpleNamespace(check_matrix_report=validator), create=True):
            result = release.check_player_matrix(self.args, "exact-commit", self.runtime)
        validator.assert_called_once_with(report, commit="exact-commit", source_root=release.ROOT,
                                          runtime_root=self.runtime)
        self.assertEqual(result, dict(status="passed", report_sha256=release.digest(report), evidence=dict(cases=15)))

    def test_failed_stale_or_malformed_report_cannot_be_accepted(self):
        self.args.matrix_report = self.root / "report.json"
        for error in (ValueError("stale source"), OSError("missing package"), KeyError("cases"), TypeError("bad schema")):
            with self.subTest(error=error):
                validator = mock.Mock(side_effect=error)
                with mock.patch.object(tools, "player_matrix", types.SimpleNamespace(check_matrix_report=validator), create=True):
                    with self.assertRaisesRegex(release.ReleaseFailed, "player matrix refused"):
                        release.check_player_matrix(self.args, "commit", self.runtime)

    def test_no_release_directory_or_export_before_passing_matrix(self):
        self.runtime.mkdir()
        (self.runtime / "pythonw.exe").write_bytes(b"inert fixture")
        args = argparse.Namespace(version="v0.1.0", t4_tag="v0.1.0", rehearsal=True,
                                  t4_ref="fake-ref", t4_repo=self.root, out=self.root / "out",
                                  runtime=self.runtime, runtime_cache=self.root / "cache",
                                  matrix_report=None, skip_matrix=False)
        with mock.patch.object(release, "check_environment"), \
                mock.patch.object(release, "check_tree", return_value=("commit", object())), \
                mock.patch.object(release, "git", return_value="t4-commit"), \
                mock.patch.object(release, "export") as export, \
                mock.patch.object(release.bundle, "create_bundle") as package:
            with self.assertRaisesRegex(release.ReleaseFailed, "passing player matrix"):
                release.make(args)
        self.assertFalse(args.out.exists())
        export.assert_not_called()
        package.assert_not_called()


if __name__ == "__main__":
    unittest.main()
