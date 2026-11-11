"""T5DR 1.2.4's SSE2 runtime as OpenRecomp sees it (openrecomp/adapters/t5_runtime.py, the Play page's reason and the
"Check my problem" hint), with a fake install only.

The runtime is picked by the install's own code (tools/build_game.py runtime_for_this_pc, through core.this_pc_runtime);
OpenRecomp asks it, it does not decide. To test that path with a mocked processor, FakeBuildGame below carries T5DR's
selection rule (choose_runtime / runtime_for_this_pc, T5DR branch t5-oldhw-019 186d3d64) with the two processor
questions replaced: Windows' IsProcessorFeaturePresent and the bundled clang's CPUID answer."""
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp.adapters import t5_runtime, t5dr
from openrecomp.adapters.base import Adapter
from openrecomp.adapters.support import T5Support

PF_SSE3, PF_SSE4_1 = 13, 37


class FakeBuildGame:
    """The install's build_game as far as the runtime choice goes; the processor is mocked."""

    def __init__(self, shipped=True, pf=None, cpuid=None):
        self.shipped = shipped
        self.pf = dict(pf or {})            # feature -> True/False (None: Windows could not be asked)
        self.cpuid = cpuid                  # the bundled clang's -march=native: True/False/None (did not run)
        self.asked = []

    def prebuilt_host_sse2(self):
        return self.shipped

    def _pf(self, feature):
        self.asked.append(("pf", feature))
        return self.pf.get(feature)

    def clang_has_sse41(self, llvm_bin):
        self.asked.append(("cpuid", llvm_bin))
        return self.cpuid

    # T5DR's rule (tools/build_game.py), unchanged apart from self.
    def choose_runtime(self, sse2_shipped, forced=None, pf_sse41=None, clang_sse41=None, pf_sse3=None):
        if forced in ("sse2", "sse41"):
            if forced == "sse2" and not sse2_shipped:
                return "sse41", "forced, not shipped"
            return forced, "forced"
        if not sse2_shipped:
            return "sse41", "no SSE2 runtime in this folder"
        if pf_sse41:
            return "sse41", "this processor has SSE4.1"
        if clang_sse41 is True:
            return "sse41", "this processor has SSE4.1 (CPUID)"
        if clang_sse41 is False:
            return "sse2", "this processor has no SSE4.1 (CPUID)"
        if pf_sse3 is False:
            return "sse2", "no SSE3"
        return "sse41", "SSE4.1 unknown (assumed)"

    def runtime_for_this_pc(self, llvm_bin=None):
        forced = os.environ.get("T5DR_RUNTIME", "").strip().lower() or None
        shipped = self.prebuilt_host_sse2()
        if forced or not shipped:
            return self.choose_runtime(shipped, forced)
        pf41 = self._pf(PF_SSE4_1)
        if pf41:
            return self.choose_runtime(shipped, pf_sse41=True)
        return self.choose_runtime(shipped, pf_sse41=pf41, clang_sse41=self.clang_has_sse41(llvm_bin),
                                   pf_sse3=self._pf(PF_SSE3))


def install_core(build_game, with_this_pc=True, state=None):
    """The install's launcher/core.py: its this_pc_runtime asks build_game once per process, as T5DR's does."""
    cache = []

    def this_pc_runtime():
        if not cache:
            try:
                cache.append(build_game.runtime_for_this_pc(core.prereqs.portable_llvm())[0])
            except Exception:  # noqa: BLE001 -- as the install: never stop the Play tab
                cache.append("sse41")
        return cache[0]

    core = SimpleNamespace(build_game=build_game, prereqs=SimpleNamespace(portable_llvm=lambda: "toolchain-llvm-bin"),
                           game_state=mock.Mock(return_value=state or dict(ok=False, built=True, needs_rebuild=True)))
    if with_this_pc:
        core.this_pc_runtime = this_pc_runtime
    return core


class Base(unittest.TestCase):
    def setUp(self):
        self.out = self.enterContext(tempfile.TemporaryDirectory(dir=os.path.dirname(__file__)))
        env = {k: v for k, v in os.environ.items() if k != "T5DR_RUNTIME"}
        self.enterContext(mock.patch.dict(os.environ, env, clear=True))

    def stamp(self, runtime="absent"):
        os.makedirs(os.path.join(self.out, "build"), exist_ok=True)
        info = dict(code_id="synthetic", built="2026-11-11T20:00:00")
        if runtime != "absent":
            info["runtime"] = runtime
        with open(os.path.join(self.out, "build", "t5dr_build.json"), "w", encoding="utf-8") as stream:
            json.dump(info, stream)


class Selection(Base):
    """Which runtime this PC needs, with the processor mocked (Windows' answer and CPUID)."""

    def test_windows_says_sse41_no_cpuid_probe(self):
        bg = FakeBuildGame(pf={PF_SSE4_1: True})
        self.assertEqual(t5_runtime.this_pc(install_core(bg)), "sse41")
        self.assertEqual(bg.asked, [("pf", PF_SSE4_1)])          # a normal PC starts nothing extra

    def test_windows_before_2004_says_no_but_cpuid_has_it(self):
        bg = FakeBuildGame(pf={PF_SSE4_1: False, PF_SSE3: True}, cpuid=True)
        self.assertEqual(t5_runtime.this_pc(install_core(bg)), "sse41")
        self.assertIn(("cpuid", "toolchain-llvm-bin"), bg.asked)  # the fallback probe through the bundled clang

    def test_no_sse41_by_cpuid_is_the_sse2_runtime(self):
        bg = FakeBuildGame(pf={PF_SSE4_1: False, PF_SSE3: True}, cpuid=False)
        self.assertEqual(t5_runtime.this_pc(install_core(bg)), "sse2")

    def test_no_sse3_by_windows_when_cpuid_could_not_run(self):
        bg = FakeBuildGame(pf={PF_SSE4_1: False, PF_SSE3: False}, cpuid=None)
        self.assertEqual(t5_runtime.this_pc(install_core(bg)), "sse2")

    def test_unknown_is_the_normal_runtime(self):
        bg = FakeBuildGame(pf={}, cpuid=None)
        self.assertEqual(t5_runtime.this_pc(install_core(bg)), "sse41")

    def test_forced_by_t5dr_runtime(self):
        for forced, shipped, want in (("sse2", True, "sse2"), ("sse41", True, "sse41"), ("sse2", False, None)):
            with self.subTest(forced=forced, shipped=shipped), mock.patch.dict(os.environ, T5DR_RUNTIME=forced):
                bg = FakeBuildGame(shipped=shipped, pf={PF_SSE4_1: True})
                self.assertEqual(t5_runtime.this_pc(install_core(bg)), want)

    def test_install_without_the_sse2_runtime_is_not_asked(self):
        bg = FakeBuildGame(shipped=False, pf={PF_SSE4_1: False}, cpuid=False)
        self.assertIsNone(t5_runtime.this_pc(install_core(bg)))
        self.assertEqual(bg.asked, [])
        self.assertIsNone(t5_runtime.this_pc(SimpleNamespace()))                  # 1.2.3 and older: no build_game API

    def test_build_game_without_core_helper_is_asked_directly(self):
        bg = FakeBuildGame(pf={PF_SSE4_1: False, PF_SSE3: True}, cpuid=False)
        self.assertEqual(t5_runtime.this_pc(install_core(bg, with_this_pc=False)), "sse2")

    def test_a_failing_install_answers_nothing(self):
        core = install_core(FakeBuildGame())
        core.this_pc_runtime = mock.Mock(side_effect=OSError("clang gone"))
        self.assertIsNone(t5_runtime.this_pc(core))
        core.this_pc_runtime = mock.Mock(return_value="avx512")
        self.assertIsNone(t5_runtime.this_pc(core))

    def test_build_stamp(self):
        self.assertIsNone(t5_runtime.of_build(None, self.out))                    # not built
        self.stamp()
        self.assertEqual(t5_runtime.of_build(None, self.out), "sse41")            # a build before 1.2.4
        self.stamp("sse2")
        self.assertEqual(t5_runtime.of_build(None, self.out), "sse2")
        self.stamp("mmx")
        self.assertIsNone(t5_runtime.of_build(None, self.out))

    def test_rebuild_for_only_when_the_build_has_the_other_runtime(self):
        old = install_core(FakeBuildGame(pf={PF_SSE4_1: False, PF_SSE3: True}, cpuid=False))
        new = install_core(FakeBuildGame(pf={PF_SSE4_1: True}))
        self.assertIsNone(t5_runtime.rebuild_for(old, self.out))                  # nothing built yet
        self.stamp("sse41")
        self.assertEqual(t5_runtime.rebuild_for(old, self.out), "sse2")
        self.assertIsNone(t5_runtime.rebuild_for(new, self.out))
        self.stamp("sse2")
        self.assertEqual(t5_runtime.rebuild_for(new, self.out), "sse41")
        self.assertIsNone(t5_runtime.rebuild_for(old, self.out))


class PlayPage(Base):
    def adapter(self, core):
        adapter = object.__new__(t5dr.T5DR)
        adapter.m, adapter.config = dict(id="t5dr", adapter="t5dr", locations=[]), {}
        adapter.root = "synthetic-install"
        adapter.s = SimpleNamespace(coexistence=False, out_dir=self.out)
        adapter.core = core
        adapter.release = mock.Mock(return_value=dict(version="1.2.4"))
        adapter.replay_entries = mock.Mock(return_value=[])
        adapter._state = None
        return adapter

    def test_old_processor_with_a_normal_build_names_the_reason(self):
        self.stamp("sse41")
        a = self.adapter(install_core(FakeBuildGame(pf={PF_SSE4_1: False, PF_SSE3: True}, cpuid=False)))
        self.assertFalse(a.ready())
        self.assertEqual(a.state()["runtime_rebuild"], "sse2")
        self.assertEqual(a.status()["status"], "@build_again")
        self.assertEqual(a.status()["detail"], "@t5.rebuild_runtime_sse2")

    def test_sse2_build_on_a_processor_with_sse41_names_the_faster_version(self):
        self.stamp("sse2")
        a = self.adapter(install_core(FakeBuildGame(pf={PF_SSE4_1: True})))
        self.assertEqual(a.status()["detail"], "@t5.rebuild_runtime_sse41")

    def test_other_rebuilds_keep_their_text(self):
        self.stamp("sse41")                     # the right runtime; the install wants a rebuild for its code
        a = self.adapter(install_core(FakeBuildGame(pf={PF_SSE4_1: True})))
        self.assertNotIn("runtime_rebuild", a.state())
        self.assertEqual(a.status()["detail"], "@t5.rebuild_detail")
        b = self.adapter(install_core(FakeBuildGame(shipped=False)))           # 1.2.3 and older installs
        self.assertEqual(b.status()["detail"], "@t5.rebuild_detail")

    def test_ready_build_never_asks_the_processor(self):
        self.stamp("sse41")
        bg = FakeBuildGame(pf={PF_SSE4_1: False, PF_SSE3: True}, cpuid=False)
        a = self.adapter(install_core(bg, state=dict(ok=True, built=True, needs_rebuild=False)))
        self.assertTrue(a.ready())
        self.assertEqual(a.status()["status"], "@ready")
        self.assertEqual(bg.asked, [])


class FakeSupport(T5Support, Adapter):
    def __init__(self, findings):
        super().__init__(dict(id="test", short="Test"))
        self.root = "fake-install"
        self.s = SimpleNamespace(out_dir="fake-output")
        self.core = SimpleNamespace(desktop_dir=mock.Mock(return_value="unused"))
        self._support_modules = (SimpleNamespace(check=mock.Mock(return_value=findings)),
                                 SimpleNamespace(Context=mock.Mock(), settings_lines=mock.Mock(), build_info_for=mock.Mock(),
                                                 discover=mock.Mock(), build=mock.Mock()))


class CheckMyProblem(unittest.TestCase):
    def found(self, *findings):
        a = FakeSupport([SimpleNamespace(key=key, kind=kind) for key, kind in findings])
        with mock.patch("openrecomp.adapters.support.threading.Thread") as thread:
            a.support_start("check")
            thread.call_args.kwargs["target"](*thread.call_args.kwargs["args"])
        return a.support_state()["findings"]

    def test_sse2_release_gives_the_hint_older_release_the_problem(self):
        hint, = self.found(("old_cpu", "hint"))         # T5DR 1.2.4+: runtime\sse2 shipped, BUILD GAME picks it
        self.assertEqual((hint["label"], hint["fix"], hint["kind"]),
                         ("@support.finding.old_cpu_sse2.title", "@support.finding.old_cpu_sse2.fix", "hint"))
        problem, = self.found(("old_cpu", "problem"))   # an install without it: the game stops at its start
        self.assertEqual((problem["label"], problem["fix"], problem["kind"]),
                         ("@support.finding.old_cpu.title", "@support.finding.old_cpu.fix", "problem"))

    def test_other_hints_keep_their_texts(self):
        two, other = self.found(("two_cores", "hint"), ("future_case", "hint"))
        self.assertEqual(two["label"], "@support.finding.two_cores.title")
        self.assertEqual(other["fix"], "@support.finding.unknown.fix")


class Shipped(unittest.TestCase):
    def test_new_modules_are_in_the_release(self):
        from tools.package_release import SOURCE_GROUPS
        self.assertIn("t5_runtime.py", SOURCE_GROUPS["openrecomp/adapters"])
        self.assertIn("t4_rematch.py", SOURCE_GROUPS["openrecomp"])


if __name__ == "__main__":
    unittest.main()
