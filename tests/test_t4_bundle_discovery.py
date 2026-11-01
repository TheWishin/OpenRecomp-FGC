"""Source-bundle discovery and build gates use synthetic markers and mocked probes."""
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

from openrecomp.adapters import t4, t4_install


MANIFEST = dict(id="t4", adapter="t4", short="T4", locations=[])


class BundleDiscovery(unittest.TestCase):
    def setUp(self):
        temporary = self.enterContext(tempfile.TemporaryDirectory(dir=Path(__file__).parent))
        self.folder = Path(temporary)
        self.root = self.folder / "T4"
        self.root.mkdir()
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_T4_ROOT=""))
        for name in t4_install.SOURCE_TOOLS:
            path = self.root / name
            path.parent.mkdir(exist_ok=True)
            path.write_text("# synthetic source marker\n", encoding="utf-8")
        for name in t4_install.SOURCE_DIRS:
            path = self.root / name
            path.mkdir()
            (path / "placeholder.txt").write_text("synthetic source", encoding="utf-8")

    def test_source_catalog_found_as_default_sibling_without_loading_game_core(self):
        with mock.patch.object(t4, "DEFAULT_SOURCE_ROOT", str(self.root)):
            self.assertEqual(t4.find_root(MANIFEST, {}), str(self.root.resolve()))
        self.assertFalse((self.root / "launcher").exists())
        self.assertEqual(t4_install.install_root(self.folder), str(self.root.resolve()))

    def test_explicit_native_install_still_takes_priority(self):
        chosen = self.folder / "chosen"
        (chosen / "launcher").mkdir(parents=True)
        (chosen / "launcher/t4core.py").write_text("# synthetic marker", encoding="utf-8")
        with mock.patch.object(t4, "DEFAULT_SOURCE_ROOT", str(self.root)):
            self.assertEqual(t4.find_root(MANIFEST, dict(roots=dict(t4=str(chosen)))), str(chosen.resolve()))

    def test_incomplete_source_catalog_is_refused(self):
        with mock.patch.object(t4_install, "SOURCE_TOOLS", t4_install.SOURCE_TOOLS + ("tools/missing.py",)):
            self.assertIsNone(t4_install.install_root(self.root))

    def test_source_core_facade_is_selected_without_importing_native_launcher(self):
        facade = object()
        with mock.patch("openrecomp.adapters.t4_source.create_core", return_value=facade) as create, \
                mock.patch.object(t4.importlib.util, "spec_from_file_location") as native:
            self.assertIs(t4.load_core(str(self.root)), facade)
            create.assert_called_once_with(str(self.root))
            native.assert_not_called()

    def test_source_archive_registration_retains_its_catalog_without_native_launcher(self):
        archive = self.folder / "synthetic.zip"
        with zipfile.ZipFile(archive, "w") as output:
            for path in self.root.rglob("*"):
                if path.is_file():
                    output.write(path, "T4/" + path.relative_to(self.root).as_posix())
        cfg = {}
        with mock.patch.object(t4_install, "user_dir", return_value=str(self.folder / "user")):
            self.assertEqual(t4_install.install_source(MANIFEST, cfg, str(archive)), "reload")
        self.assertTrue(t4_install.source_root(cfg["roots"]["t4"]))


class SourceBuild(unittest.TestCase):
    def setUp(self):
        self.core = SimpleNamespace(source_only=True, load_settings=lambda: {}, play_problems=lambda settings: [],
                                    effective_iso=lambda settings: settings.get("iso", ""),
                                    build_command=lambda iso: ["synthetic-builder", iso],
                                    build_env=lambda: {"SYNTHETIC_BUILD": "contained"})
        self.thread = self.enterContext(mock.patch.object(t4.threading, "Thread"))
        self.adapter = t4.T4(MANIFEST, {}, "synthetic-root", core=self.core)
        self.thread.return_value.is_alive.return_value = False
        self.adapter.s["iso"] = "synthetic-source"
        self.adapter._verified_iso = ("synthetic-source", 1, 2)
        self.enterContext(mock.patch.object(self.adapter, "_iso_stamp", return_value=self.adapter._verified_iso))

    def test_tool_probe_is_background_work_and_snapshot_reads_do_not_repeat_it(self):
        self.thread.assert_called_once()
        self.thread.return_value.start.assert_called_once_with()
        self.assertEqual(len(self.adapter.prerequisites()), 6)
        self.assertEqual(self.adapter.prerequisites()[0]["value"], "@t4.tools.checking")
        self.assertTrue(self.adapter.prerequisites()[0]["busy"])
        self.adapter.prerequisites()[0]["ok"] = True
        self.assertFalse(self.adapter.prerequisites()[0]["ok"])
        self.assertEqual(self.thread.call_count, 1)

    def test_source_build_requires_tools_instead_of_portable_release(self):
        self.core.bundled_toolchain = lambda: False
        self.assertEqual(self.adapter.build_ready(), "@t4.tools.required")
        self.assertEqual([row["id"] for row in self.adapter.sources()], ["iso"])
        self.adapter._prerequisite_rows = [dict(id="synthetic", ok=True)]
        self.assertEqual(self.adapter.build_ready(), "")
        self.assertEqual(self.adapter.native_label, "")
        with self.assertRaisesRegex(RuntimeError, "no_native"):
            self.adapter.open_native()

    def test_source_build_passes_contained_environment_to_worker(self):
        self.adapter._prerequisite_rows = [dict(id="synthetic", ok=True)]
        self.adapter.build_error = "previous synthetic failure"
        with mock.patch.object(t4, "ProcessBuild") as process:
            self.adapter.build_start()
        process.assert_called_once_with(["synthetic-builder", "synthetic-source"], cwd="synthetic-root",
                                        on_line=self.adapter._on_line, env={"SYNTHETIC_BUILD": "contained"})
        self.assertEqual(self.adapter.build_error, "")

    def test_source_failure_keeps_cause_after_repeated_output_and_full_log_footer(self):
        self.adapter.build = SimpleNamespace(running=lambda: False, cancelled=False, code=1)
        self.adapter._on_line("[8/8] runtime - Build runtime")
        cause = "FAILED at step 'runtime': Build failed: synthetic compiler error C1083"
        self.adapter._on_line("")
        self.adapter._on_line(cause)
        self.adapter._on_line("--- last output ---")
        for line in range(40):
            self.adapter._on_line("synthetic repeated compiler output " + str(line))
        self.adapter._on_line("-------------------")
        self.adapter._on_line("Full log: synthetic-build.log")
        self.assertNotIn(cause, self.adapter.build_lines)
        self.adapter._build_end(self.adapter.build)
        self.assertEqual(self.adapter.last_result["_values"]["error"], cause)
        self.assertEqual(self.adapter.last_result["_values"]["name"], "runtime")

    def test_completed_tool_probe_clears_busy_and_worker_failure_leaves_retry_available(self):
        target = self.thread.call_args.kwargs["target"]
        with mock.patch("openrecomp.adapters.t4_prerequisites.check_prerequisites",
                        return_value=[dict(id="synthetic", ok=True, command="synthetic-command")]):
            target()
        self.assertFalse(self.adapter.prerequisites()[0]["busy"])
        self.assertEqual(self.adapter.build_ready(), "")
        self.thread.return_value.start.side_effect = RuntimeError("synthetic worker unavailable")
        self.assertFalse(self.adapter.refresh_prerequisites())
        self.assertFalse(self.adapter.prerequisites()[0]["busy"])
        self.assertEqual(self.adapter.build_ready(), "@t4.tools.required")

    def test_refresh_invalidates_previous_success_and_avoids_duplicate_probe(self):
        self.adapter._prerequisite_rows = [dict(id="synthetic", ok=True, command="synthetic-command")]
        self.thread.return_value.is_alive.return_value = True
        self.assertFalse(self.adapter.refresh_prerequisites())
        self.thread.return_value.is_alive.return_value = False
        self.assertTrue(self.adapter.refresh_prerequisites())
        self.assertEqual(self.adapter.build_ready(), "@t4.tools.required")
        self.assertEqual(self.adapter.prerequisites()[0]["command"], "synthetic-command")

    def test_source_direct_profile_survives_beta_defaults_and_clears_inherited_harness(self):
        received = []
        self.core.run_lock_holder = lambda: ""
        self.core.take_run_lock = mock.Mock()
        self.core.graphics_support = lambda exe: dict(aa=True)
        self.core.game_env = lambda settings, exe=None: dict(
            TEKKEN4_RAND_SEED="inherited", TEKKEN4_RB_TEST="inherited",
            TEKKEN4_NET_AUTO_VS="1", TEKKEN4_NET_COALESCE="0")
        self.core.GameRun = lambda settings: SimpleNamespace(
            proc=SimpleNamespace(pid=123, poll=lambda: 0),
            start=lambda: received.append(self.core.game_env(settings, "synthetic-runtime")))
        for diagnostics in ("0", "1"):
            self.adapter._start(dict(TEKKEN4_NET="host:7400", TEKKEN4_NET_DIAG=diagnostics,
                                     TEKKEN4_NET_COALESCE="1", TEKKEN4_NET_AUTO_VS="0",
                                     TEKKEN4_RB_AUDIO_TIMELINE="0"))
            self.assertEqual(received[-1]["TEKKEN4_NET_DIAG"], diagnostics)
            self.assertEqual(received[-1]["TEKKEN4_NET_COALESCE"], "1")
            self.assertEqual(received[-1]["TEKKEN4_NET_AUTO_VS"], "0")
            self.assertEqual(received[-1]["TEKKEN4_RB_AUDIO_TIMELINE"], "0")
            self.assertNotIn("TEKKEN4_RAND_SEED", received[-1])
            self.assertNotIn("TEKKEN4_RB_TEST", received[-1])


if __name__ == "__main__":
    unittest.main()
