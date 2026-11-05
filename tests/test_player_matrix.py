"""Player release checks use inert packages and fake child processes only."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from tools import player_matrix as matrix


ROOT = Path(__file__).resolve().parents[1]


class MatrixFixture(unittest.TestCase):
    def setUp(self):
        self.temp = Path(self.enterContext(tempfile.TemporaryDirectory(prefix=".matrix-test-", dir=ROOT)))
        self.launcher = self.temp / "release" / "OpenRecomp-FGC"
        self.write("portable/pythonw.exe", "inert private interpreter marker")
        self.write("openrecomp/app.py", "# Inert launcher source marker.\n")
        self.write("games/t5dr.json", "{}")

    def write(self, name, text):
        path = self.launcher / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def evidence(self, case_id="fresh-t5dr"):
        root = self.temp / "isolated-game"
        python = str(root / "python" / "python.exe")
        result = dict(packaged_python=str(self.launcher / "portable/pythonw.exe"),
                      imported_launcher=str(self.launcher / "openrecomp/app.py"), qml_loaded=True,
                      root=str(root), expected_root=str(root), build_python=python,
                      commands=[[python, "inert-build-marker"]], build_started=True, first_steps=True,
                      offered_existing=True, second_copy=False)
        if case_id in matrix.T4_CASES:  # Tekken 4 builds on the package's portable Python
            python = str(self.launcher / "portable/pythonw.exe")
            result.update(build_python=python, commands=[[python, "-I", "-B", "inert-build-marker"]])
        if case_id in matrix.REPAIRS:
            result.update(build_python="", commands=[], build_started=False,
                          repair_message="The game package Python needs repair. Reinstall or choose a complete folder.")
        return result

    def report(self):
        return dict(schema=matrix.SCHEMA, source_commit="reviewed-commit", launcher=str(self.launcher),
                    source_fingerprint=matrix.source_fingerprint(self.launcher),
                    runtime_fingerprint=matrix.runtime_fingerprint(self.launcher),
                    package_fingerprint=matrix.fingerprint(self.launcher), package_unchanged=True,
                    cases=[dict(id=name, status="PASS", evidence=self.evidence(name)) for name in matrix.REQUIRED_CASES])

    def check_report(self, report):
        path = self.temp / "report.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        return matrix.check_matrix_report(path, commit="reviewed-commit", source_root=self.launcher,
                                          runtime_root=self.launcher / "portable")


class PackageBoundary(MatrixFixture):
    def test_exact_package_and_release_parent_resolve_private_runtime(self):
        self.assertEqual(matrix.package_root(self.launcher), self.launcher.resolve())
        self.assertEqual(matrix.package_root(self.launcher.parent), self.launcher.resolve())

    def test_developer_checkout_or_incomplete_package_is_refused(self):
        (self.launcher / "portable/pythonw.exe").unlink()
        self.write(".venv/Scripts/python.exe", "inert dev interpreter marker")
        with self.assertRaises(matrix.MatrixError):
            matrix.package_root(self.launcher)

    def test_fingerprints_change_for_launcher_and_runtime_changes(self):
        source = matrix.source_fingerprint(self.launcher)
        runtime = matrix.runtime_fingerprint(self.launcher / "portable")
        package = matrix.fingerprint(self.launcher)
        self.write("openrecomp/app.py", "# Changed launcher marker.\n")
        self.assertNotEqual(matrix.source_fingerprint(self.launcher), source)
        self.assertEqual(matrix.runtime_fingerprint(self.launcher / "portable"), runtime)
        self.assertNotEqual(matrix.fingerprint(self.launcher), package)
        self.write("portable/pythonw.exe", "changed private interpreter marker")
        self.assertNotEqual(matrix.runtime_fingerprint(self.launcher / "portable"), runtime)

    def test_source_fingerprint_matches_archive_line_endings_and_ignores_bytecode(self):
        source = matrix.source_fingerprint(self.launcher)
        (self.launcher / "openrecomp/app.py").write_bytes(b"# Inert launcher source marker.\r\n")
        self.write("openrecomp/__pycache__/app.cpython-312.pyc", "inert bytecode marker")
        self.assertEqual(matrix.source_fingerprint(self.launcher), source)


class PlayerEnvironment(MatrixFixture):
    def test_every_home_and_temp_directory_is_isolated_and_qt_is_offscreen(self):
        home = self.temp / "J\u00f6rg player" / "long folder"
        base = dict(PATH="developer-python;winget", SystemRoot="C:/Windows", PYTHONPATH="developer-site",
                    PYTHONHOME="developer-home", OPENRECOMP_HOME="player-profile", OPENRECOMP_RELEASES_TEST="bad",
                    T5_ACCOUNT="must-not-leak", T4_TEST="must-not-leak", TEKKEN4_NET="must-not-leak",
                    PS3_AUDIO_MUTE="0", QT_QPA_PLATFORM="windows", SAFE_MARKER="retained")
        env = matrix.isolated_env(home, "no-python", base)
        self.assertEqual(env["SAFE_MARKER"], "retained")
        for name in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "OPENRECOMP_HOME", "TEMP", "TMP"):
            self.assertTrue(Path(env[name]).is_relative_to(home.resolve()), (name, env[name]))
        for name in ("PYTHONPATH", "PYTHONHOME", "OPENRECOMP_RELEASES_TEST", "T5_ACCOUNT", "T4_TEST", "TEKKEN4_NET"):
            self.assertNotIn(name, env)
        self.assertEqual(env["QT_QPA_PLATFORM"], "offscreen")
        self.assertEqual(env["PS3_AUDIO_MUTE"], "1")
        self.assertEqual(env["PS3_WINDOW_BACKGROUND"], "1")
        self.assertNotIn("developer-python", env["PATH"])
        self.assertNotIn("winget", env["PATH"])
        self.assertEqual(base["OPENRECOMP_HOME"], "player-profile")

    def test_foreign_python_is_first_only_in_its_deliberate_case(self):
        home = self.temp / "profile"
        foreign = matrix.isolated_env(home, "foreign-python", {})["PATH"].split(os.pathsep)
        normal = matrix.isolated_env(home, "no-python", {})["PATH"].split(os.pathsep)
        self.assertEqual(foreign[0], str(home.resolve() / "foreign-python"))
        self.assertEqual(foreign[1:], normal)

    def test_tool_folders_reach_path_only_for_the_t4_case_and_never_with_a_python(self):
        git, snake = self.temp / "git" / "cmd", self.temp / "pytools"
        git.mkdir(parents=True); snake.mkdir()
        (snake / "python.exe").write_bytes(b"x")
        inputs = {"tools_path": [str(git), str(snake), str(self.temp / "missing")]}
        t4 = next(c for c in matrix.cases() if c["id"] == "t4-iso")
        other = next(c for c in matrix.cases() if c["id"] == "no-winget")
        self.assertEqual(matrix._case_tools(t4, inputs), [str(git)])
        self.assertEqual(matrix._case_tools(other, inputs), [])
        path = matrix.isolated_env(self.temp / "p", "t4-iso", {}, tools=[str(git)])["PATH"].split(os.pathsep)
        self.assertEqual(path[0], str(git))
        self.assertNotIn(str(git), matrix.isolated_env(self.temp / "p", "t4-iso", {})["PATH"])

    def test_case_definitions_cover_every_required_selection_once(self):
        cases = matrix.cases()
        self.assertEqual(len(cases), len(matrix.REQUIRED_CASES))
        self.assertEqual({c["id"] for c in cases}, set(matrix.REQUIRED_CASES))
        selections = {c["id"]: c["selection"] for c in cases}
        for case, value in (("parent-t5dr", "parent"), ("native-t5dr", "native"), ("child-t5dr", "child")):
            self.assertEqual(selections[case], value)
        self.assertEqual(next(c for c in cases if c["id"] == "t4-iso")["game"], "t4")


class EvidenceChecks(MatrixFixture):
    def test_tekken4_builds_on_the_packages_portable_python_not_a_game_python_or_a_foreign_one(self):
        self.assertEqual(matrix.evaluate_case("t4-iso", self.evidence("t4-iso"), self.launcher)[0], "PASS")
        for wrong in (str(self.temp / "isolated-game" / "python" / "python.exe"), str(self.temp / "path" / "python.exe")):
            with self.subTest(python=wrong):
                evidence = self.evidence("t4-iso")
                evidence.update(build_python=wrong, commands=[[wrong, "-I", "-B", "inert-build-marker"]])
                self.assertEqual(matrix.evaluate_case("t4-iso", evidence, self.launcher)[0], "FAIL")
        self.assertEqual(matrix.evaluate_case("fresh-t5dr", self.evidence("t4-iso"), self.launcher)[0], "FAIL")

    def test_success_requires_observed_game_python_and_successful_first_steps(self):
        self.assertEqual(matrix.evaluate_case("fresh-t5dr", self.evidence(), self.launcher)[0], "PASS")
        for key, value in (("build_started", False), ("first_steps", False), ("commands", []),
                           ("build_python", str(self.launcher / "portable/pythonw.exe")),
                           ("packaged_python", "developer-python"), ("imported_launcher", str(ROOT / "openrecomp/app.py")),
                           ("qml_loaded", False), ("fallback", True), ("foreign_python_used", True),
                           ("network_denied", ["unexpected operation"]),
                           ("qml_warnings", ["synthetic warning"]), ("error", "callback failed")):
            with self.subTest(key=key):
                evidence = self.evidence()
                evidence[key] = value
                self.assertEqual(matrix.evaluate_case("fresh-t5dr", evidence, self.launcher)[0], "FAIL")

    def test_claimed_python_without_matching_observed_command_is_rejected(self):
        evidence = self.evidence()
        evidence["commands"] = [[str(self.launcher / "portable/pythonw.exe"), "inert-build-marker"]]
        self.assertEqual(matrix.evaluate_case("fresh-t5dr", evidence, self.launcher)[0], "FAIL")

    def test_crypto_import_probe_alone_is_not_an_observed_build(self):
        evidence = self.evidence()
        evidence["commands"] = [[evidence["build_python"], "-I", "-c", "from Crypto.Cipher import AES"]]
        self.assertEqual(matrix.evaluate_case("fresh-t5dr", evidence, self.launcher)[0], "FAIL")

    def test_folder_variants_must_resolve_to_the_expected_root(self):
        for name in ("existing-t5dr", "parent-t5dr", "native-t5dr", "child-t5dr"):
            with self.subTest(case=name):
                evidence = self.evidence()
                self.assertEqual(matrix.evaluate_case(name, evidence, self.launcher)[0], "PASS")
                evidence["expected_root"] = str(self.temp / "different-game")
                self.assertEqual(matrix.evaluate_case(name, evidence, self.launcher)[0], "FAIL")

    def test_discovered_old_install_must_be_offered_without_a_second_copy(self):
        for key, value in (("offered_existing", False), ("second_copy", True)):
            with self.subTest(key=key):
                evidence = self.evidence()
                evidence[key] = value
                self.assertEqual(matrix.evaluate_case("discover-old-t5dr", evidence, self.launcher)[0], "FAIL")

    def test_damaged_runtime_requires_repair_guidance_and_no_build(self):
        for name in matrix.REPAIRS:
            with self.subTest(case=name):
                good = self.evidence(name)
                self.assertEqual(matrix.evaluate_case(name, good, self.launcher)[0], "PASS")
                for key, value in (("repair_message", ""), ("build_started", True), ("build_python", "foreign-python")):
                    evidence = dict(good, **{key: value})
                    self.assertEqual(matrix.evaluate_case(name, evidence, self.launcher)[0], "FAIL")

    def test_no_winget_can_pass_with_clear_guidance_or_successful_game_build(self):
        evidence = self.evidence("no-winget")
        self.assertEqual(matrix.evaluate_case("no-winget", evidence, self.launcher)[0], "PASS")
        evidence.update(build_started=False, build_python="", commands=[], first_steps=False,
                        guidance="Install the required build tools manually, then retry Build.")
        self.assertEqual(matrix.evaluate_case("no-winget", evidence, self.launcher)[0], "PASS")
        evidence["guidance"] = ""
        self.assertEqual(matrix.evaluate_case("no-winget", evidence, self.launcher)[0], "FAIL")


class ForeignFolderEvidence(MatrixFixture):
    """A folder T5DR's own launcher set up: the build must show the notice, the lock and untouched T5DR files."""

    def evidence_for(self, **changes):
        evidence = self.evidence("existing-t5dr")
        evidence.update(foreign_folder=True, notice_shown=True, lock_held=True, launcher_files_unchanged=True)
        evidence.update(changes)
        return evidence

    def test_complete_foreign_folder_evidence_passes(self):
        self.assertEqual(matrix.evaluate_case("existing-t5dr", self.evidence_for(), self.launcher)[0], "PASS")

    def test_each_missing_observation_fails(self):
        for change in ({"notice_shown": False}, {"lock_held": False}, {"launcher_files_unchanged": False},
                       {"launcher_files_unchanged": None}):
            with self.subTest(change=change):
                status, reason = matrix.evaluate_case("existing-t5dr", self.evidence_for(**change), self.launcher)
                self.assertEqual(status, "FAIL", reason)

    def test_an_openrecomp_made_install_needs_none_of_it(self):
        evidence = self.evidence("existing-t5dr")
        self.assertEqual(matrix.evaluate_case("existing-t5dr", evidence, self.launcher)[0], "PASS")


class Reports(MatrixFixture):
    def test_complete_evidence_is_accepted(self):
        checked = self.check_report(self.report())
        self.assertEqual(checked["status"], "PASS")
        self.assertEqual(checked["cases"], len(matrix.REQUIRED_CASES))

    def test_incomplete_duplicate_skipped_and_failed_reports_are_refused(self):
        for kind in ("missing", "duplicate", "skipped", "failed", "false-pass"):
            with self.subTest(kind=kind):
                report = self.report()
                if kind == "missing":
                    report["cases"].pop()
                elif kind == "duplicate":
                    report["cases"][-1] = copy.deepcopy(report["cases"][0])
                elif kind == "false-pass":
                    report["cases"][0]["evidence"]["first_steps"] = False
                else:
                    report["cases"][0]["status"] = "BLOCKED" if kind == "skipped" else "FAIL"
                with self.assertRaises(matrix.MatrixError):
                    self.check_report(report)

    def test_report_is_bound_to_commit_source_runtime_and_package(self):
        for key in ("schema", "source_commit", "source_fingerprint", "runtime_fingerprint", "package_fingerprint"):
            with self.subTest(field=key):
                report = self.report()
                report[key] = "stale"
                with self.assertRaises(matrix.MatrixError):
                    self.check_report(report)
        report = self.report()
        self.write("release.json", "changed package metadata")
        with self.assertRaises(matrix.MatrixError):
            self.check_report(report)

    def test_report_from_modified_package_is_refused(self):
        report = self.report()
        report["package_unchanged"] = False
        with self.assertRaises(matrix.MatrixError):
            self.check_report(report)

    def test_missing_and_malformed_reports_are_refused(self):
        path = self.temp / "absent-report.json"
        for text in (None, "{broken", "[]"):
            with self.subTest(text=text), self.assertRaises(matrix.MatrixError):
                if text is not None:
                    path.write_text(text, encoding="utf-8")
                matrix.check_matrix_report(path, commit="reviewed-commit", source_root=self.launcher,
                                           runtime_root=self.launcher / "portable")


class OwnerWaiver(MatrixFixture):
    """Owner decision 2026-11-05: the T4 ISO case (a PowerShell build the audit cannot sandbox) is covered by the
    Tekken 4 release gate. An explicit, named waiver, accepted for that one case and nothing else."""

    def blocked_report(self, case_id="t4-iso"):
        report = self.report()
        for row in report["cases"]:
            if row["id"] == case_id:
                row.update(status="BLOCKED", reason="offline safety guard refused an unauditable installer", evidence={})
        return report

    def waive(self, report, requested=("t4-iso",)):
        matrix.apply_waivers(report["cases"], set(requested))
        return report

    def test_only_t4_iso_has_a_waiver(self):
        self.assertEqual(set(matrix.WAIVERS), {"t4-iso"})
        waiver = matrix.waiver_for("t4-iso")
        self.assertIn("RELEASE_GATE_0.1.1", waiver["reference"])
        self.assertTrue(waiver["reason"] and waiver["owner_decision"] == "2026-11-05")
        self.assertIsNone(matrix.waiver_for("existing-t5dr"))

    def test_a_blocked_t4_iso_with_the_waiver_is_accepted_and_named_in_the_result(self):
        report = self.waive(self.blocked_report())
        row = next(r for r in report["cases"] if r["id"] == "t4-iso")
        self.assertEqual(row["status"], "WAIVED")
        self.assertEqual(row["waiver"]["original_status"], "BLOCKED")
        self.assertIn("unauditable", row["waiver"]["original_reason"])
        checked = self.check_report(report)
        self.assertEqual(checked["status"], "PASS")
        self.assertEqual([w["case"] for w in checked["waivers"]], ["t4-iso"])
        self.assertIn("RELEASE_GATE_0.1.1", checked["waivers"][0]["reference"])

    def test_a_plain_report_has_no_waivers(self):
        self.assertEqual(self.check_report(self.report())["waivers"], [])

    def test_a_blocked_t4_iso_without_the_waiver_is_still_refused(self):
        with self.assertRaises(matrix.MatrixError):
            self.check_report(self.blocked_report())

    def test_no_other_case_can_be_waived_by_flag_or_by_hand(self):
        with self.assertRaises(matrix.MatrixError):
            self.waive(self.blocked_report("existing-t5dr"), ("existing-t5dr",))
        report = self.blocked_report("existing-t5dr")
        row = next(r for r in report["cases"] if r["id"] == "existing-t5dr")
        row.update(status="WAIVED", waiver=dict(matrix.WAIVERS["t4-iso"], case="existing-t5dr", original_status="BLOCKED"))
        with self.assertRaises(matrix.MatrixError):
            self.check_report(report)

    def test_failed_skipped_and_timed_out_cases_are_never_waived(self):
        for status in ("FAIL", "SKIPPED"):
            with self.subTest(status=status):
                report = self.report()
                row = next(r for r in report["cases"] if r["id"] == "t4-iso")
                row.update(status=status, reason="timed out")
                self.waive(report)
                self.assertEqual(row["status"], status)
                self.assertNotIn("waiver", row)
                with self.assertRaises(matrix.MatrixError):
                    self.check_report(report)

    def test_an_altered_or_hand_written_waiver_is_refused(self):
        for change in ({"reason": "because"}, {"reference": "trust me"}, {"owner_decision": "2026-12-31"},
                       {"original_status": "FAIL"}):
            with self.subTest(change=change):
                report = self.waive(self.blocked_report())
                next(r for r in report["cases"] if r["id"] == "t4-iso")["waiver"].update(change)
                with self.assertRaises(matrix.MatrixError):
                    self.check_report(report)
        report = self.waive(self.blocked_report())
        del next(r for r in report["cases"] if r["id"] == "t4-iso")["waiver"]
        with self.assertRaises(matrix.MatrixError):
            self.check_report(report)

    def test_a_case_that_ran_and_passed_keeps_its_pass_when_the_flag_is_given(self):
        report = self.waive(self.report())
        self.assertEqual(next(r for r in report["cases"] if r["id"] == "t4-iso")["status"], "PASS")
        self.assertEqual(self.check_report(report)["waivers"], [])

    def test_the_release_packager_records_the_waiver(self):
        import argparse
        from tools import make_release as release
        path = self.temp / "waived-report.json"
        path.write_text(json.dumps(self.waive(self.blocked_report())), encoding="utf-8")
        args = argparse.Namespace(rehearsal=False, matrix_report=path, skip_matrix=False)
        with mock.patch.object(release, "ROOT", self.launcher):
            facts = release.check_player_matrix(args, "reviewed-commit", self.launcher / "portable")
        self.assertEqual(facts["status"], "passed")
        self.assertEqual([w["case"] for w in facts["evidence"]["waivers"]], ["t4-iso"])
        # the same report with a second waived case is refused by the packager
        report = self.waive(self.blocked_report())
        row = next(r for r in report["cases"] if r["id"] == "existing-t5dr")
        row.update(status="WAIVED", waiver=dict(matrix.WAIVERS["t4-iso"], original_status="BLOCKED"))
        path.write_text(json.dumps(report), encoding="utf-8")
        with mock.patch.object(release, "ROOT", self.launcher), self.assertRaisesRegex(release.ReleaseFailed, "refused"):
            release.check_player_matrix(args, "reviewed-commit", self.launcher / "portable")


class ScratchFixtures(MatrixFixture):
    def setUp(self):
        super().setUp()
        self.source = self.temp / "inert-old-install"
        for name in ("native/marker.txt", "launcher/marker.txt", "python/python.exe",
                     "python/Lib/site-packages/Crypto/marker.txt"):
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("inert fixture; no game code or executable", encoding="utf-8")

    def prepare(self, name):
        case = next(dict(c) for c in matrix.cases() if c["id"] == name)
        home = self.temp / "scratch" / name
        home.mkdir(parents=True)
        original = {"t5dr_existing": str(self.source)}
        inputs = matrix.prepare_case(home, case, original)
        self.assertEqual(original["t5dr_existing"], str(self.source))
        return home, case, inputs

    def test_wrong_folder_variants_map_to_one_private_copy_of_expected_root(self):
        for name, suffix in (("existing-t5dr", ""), ("parent-t5dr", ".."),
                             ("native-t5dr", "native"), ("child-t5dr", "launcher")):
            with self.subTest(case=name):
                home, case, inputs = self.prepare(name)
                root = Path(inputs["t5dr_existing"])
                self.assertEqual(Path(inputs["expected_root"]), root)
                self.assertTrue(root.is_relative_to(home))
                self.assertNotEqual(root, self.source)
                self.assertEqual(Path(case["selection"]).resolve(), (root / suffix).resolve())
                self.assertEqual(len(list((home / "Downloads").iterdir())), 1)
                self.assertTrue((self.source / "python/python.exe").exists())

    def test_an_earlier_openrecomp_install_gets_the_install_marker_in_its_private_copy_only(self):
        case = next(dict(c) for c in matrix.cases() if c["id"] == "existing-t5dr")
        for managed in (False, True):
            home = self.temp / "scratch" / ("managed" if managed else "borrowed")
            home.mkdir(parents=True)
            inputs = matrix.prepare_case(home, dict(case), {"t5dr_existing": str(self.source),
                                                          "t5dr_existing_managed": managed})
            marker = Path(inputs["t5dr_existing"]) / "openrecomp-release.json"
            self.assertEqual(marker.is_file(), managed)
            self.assertFalse((self.source / "openrecomp-release.json").exists())
            if managed:
                info = json.loads(marker.read_text(encoding="utf-8"))
                self.assertEqual((info["game"], info["installed_by"]), ("t5dr", "OpenRecomp-FGC"))

    def test_unicode_case_keeps_the_game_folder_short_while_the_profile_is_long(self):
        case = next(dict(c) for c in matrix.cases() if c["id"] == "unicode-long-path")
        home = self.temp / "scratch" / "unicode-long-path" / ("Jörg Müller " + "long player folder " * 5).rstrip()
        home.mkdir(parents=True)
        inputs = matrix.prepare_case(home, case, {"t5dr_existing": str(self.source)})
        root = Path(inputs["t5dr_existing"])
        self.assertTrue((root / "python" / "python.exe").is_file())
        self.assertIn("ö", str(root))
        self.assertIn(" ", str(root))
        self.assertLess(len(str(root)), len(str(home)))
        self.assertFalse(root.is_relative_to(home))

    def test_discovery_case_does_not_preselect_a_folder(self):
        _, case, inputs = self.prepare("discover-old-t5dr")
        self.assertEqual(case["selection"], "")
        self.assertTrue(Path(inputs["expected_root"]).is_dir())

    def test_antivirus_damage_is_simulated_on_scratch_copy_only(self):
        _, _, missing_python = self.prepare("missing-python")
        runtime_root = Path(missing_python["t5dr_existing"])
        self.assertFalse((runtime_root / "python").exists())
        self.assertTrue((runtime_root / "matrix-quarantined-python/python.exe").exists())
        _, _, missing_crypto = self.prepare("missing-crypto")
        crypto_root = Path(missing_crypto["t5dr_existing"])
        self.assertTrue((crypto_root / "python/python.exe").exists())
        self.assertFalse((crypto_root / "python/Lib/site-packages/Crypto").exists())
        self.assertTrue((crypto_root / "python/Lib/site-packages/matrix-quarantined-Crypto").exists())
        self.assertTrue((self.source / "python/python.exe").exists())
        self.assertTrue((self.source / "python/Lib/site-packages/Crypto/marker.txt").exists())

    def test_foreign_python_is_a_poison_fixture_without_a_real_executable(self):
        home, _, _ = self.prepare("foreign-python")
        for name in ("python.exe", "python3.exe"):
            data = (home / "foreign-python" / name).read_bytes()
            self.assertFalse(data.startswith(b"MZ"))
            self.assertIn(b"must never run", data)


class FakePackagedRuns(MatrixFixture):
    def case(self):
        return next(c for c in matrix.cases() if c["id"] == "fresh-t5dr")

    def fake_run(self, command, **kwargs):
        self.assertEqual(Path(command[0]), self.launcher / "portable/pythonw.exe")
        self.assertNotIn(".venv", command[0])
        self.assertEqual(kwargs["cwd"], str(self.launcher))
        self.assertEqual(kwargs["env"]["QT_QPA_PLATFORM"], "offscreen")
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(kwargs["timeout"], 35)
        self.assertNotIn("shell", kwargs)
        request = json.loads(Path(command[command.index("--request") + 1]).read_text(encoding="utf-8"))
        self.assertEqual(request["case"]["id"], "fresh-t5dr")
        result = Path(command[command.index("--result") + 1])
        result.write_text(json.dumps(dict(status="PASS", evidence=self.evidence())), encoding="utf-8")
        return SimpleNamespace(returncode=0)

    def test_runner_uses_only_packaged_python_and_writes_private_result_paths(self):
        result = matrix.run_case(self.launcher, self.temp / "scratch", self.case(), {}, timeout=5, run=self.fake_run)
        self.assertEqual(result["status"], "PASS", result)
        self.assertTrue(Path(result["result"]).is_relative_to(self.temp / "scratch"))

    def test_timeout_failure_and_missing_result_never_pass(self):
        for name in ("timeout", "exit", "no-result"):
            with self.subTest(kind=name):
                def run(command, **kwargs):
                    if name == "timeout":
                        raise subprocess.TimeoutExpired(command, kwargs["timeout"])
                    if name == "exit":
                        self.fake_run(command, **kwargs)
                    return SimpleNamespace(returncode=1)
                row = matrix.run_case(self.launcher, self.temp / name, self.case(), {}, timeout=5, run=run)
                self.assertNotEqual(row["status"], "PASS", row)

    def test_child_blocked_input_remains_blocked(self):
        def run(command, **kwargs):
            result = Path(command[command.index("--result") + 1])
            result.write_text(json.dumps(dict(status="BLOCKED", reason="No local signed game release")), encoding="utf-8")
            return SimpleNamespace(returncode=2)
        row = matrix.run_case(self.launcher, self.temp / "scratch", self.case(), {}, run=run)
        self.assertEqual(row["status"], "BLOCKED")
        self.assertIn("No local signed game release", row["reason"])


class HeavySlots(MatrixFixture):
    def test_lock_is_atomic_and_released_even_when_run_raises(self):
        folder = self.temp / "locks"
        folder.mkdir()
        (folder / "HEAVY.lock").write_text("another worker", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "fake run failed"):
            with matrix.heavy_slot(folder) as lock:
                self.assertEqual(lock.name, "HEAVY2.lock")
                self.assertTrue(lock.exists())
                raise RuntimeError("fake run failed")
        self.assertFalse((folder / "HEAVY2.lock").exists())
        self.assertEqual((folder / "HEAVY.lock").read_text(encoding="utf-8"), "another worker")

    def test_all_busy_slots_are_refused_without_touching_other_locks(self):
        folder = self.temp / "locks"
        folder.mkdir()
        for name in ("HEAVY.lock", "HEAVY2.lock", "HEAVY3.lock"):
            (folder / name).write_text("another worker", encoding="utf-8")
        with self.assertRaises(matrix.MatrixError):
            with matrix.heavy_slot(folder):
                self.fail("Acquired an occupied slot")
        self.assertEqual(len(list(folder.iterdir())), 3)

    def test_a_busy_pc_can_be_waited_for_but_never_robbed(self):
        folder = self.temp / "locks"
        folder.mkdir()
        for name in ("HEAVY.lock", "HEAVY2.lock", "HEAVY3.lock"):
            (folder / name).write_text("another worker", encoding="utf-8")
        freed = []

        def sleep(_seconds):
            if not freed:
                (folder / "HEAVY2.lock").unlink()          # the other worker finishes
                freed.append(True)

        with mock.patch.object(matrix.time, "sleep", sleep):
            with matrix.heavy_slot(folder, wait=60, poll=0.01) as lock:
                self.assertEqual(lock.name, "HEAVY2.lock")
        (folder / "HEAVY2.lock").write_text("another worker", encoding="utf-8")
        with self.assertRaises(matrix.MatrixError):          # waiting is bounded
            with matrix.heavy_slot(folder, wait=0.05, poll=0.01):
                self.fail("Acquired an occupied slot")
        self.assertEqual(len(list(folder.iterdir())), 3)


if __name__ == "__main__":
    unittest.main()
