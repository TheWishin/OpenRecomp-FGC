"""Which prebuilt T5DR runtime a build needs on this PC: the normal one (SSE4.1) or, from T5DR 1.2.3 on, the SSE2 one
for processors without SSE4.1 (`runtime\\sse2\\t5dr.exe`; T5DR's docs/SSE2_BASELINE.md "Shipping it").

Nothing is decided here. BUILD GAME (the install's tools/build_game.py, which OpenRecomp runs through the install's
own BuildRun) picks the runtime and stamps it into build/t5dr_build.json ("runtime": "sse2" | "sse41"); the
install's game_state asks for a rebuild when the stamp's runtime is not the one this PC needs. This module only asks
the install the same question with the install's own code -- core.this_pc_runtime() = build_game.runtime_for_this_pc:
Windows' IsProcessorFeaturePresent(PF_SSE4_1), else CPUID through the bundled clang (Windows 10 before 2004 answers
"no" on every processor), T5DR_RUNTIME=sse2|sse41 to force -- so the Play page can say why a build is needed. An
install without an SSE2 runtime (1.2.3 and older) answers nothing and everything stays as before.
"""
import json
import os

RUNTIMES = ("sse41", "sse2")


def shipped(core):
    """Whether the install carries the SSE2 runtime next to the normal one (its build_game says so)."""
    build_game = getattr(core, "build_game", None)
    probe = getattr(build_game, "prebuilt_host_sse2", None)
    if not callable(probe):
        return False
    try:
        return bool(probe())
    except Exception:  # noqa: BLE001 -- an install we cannot ask is an install without it
        return False


def this_pc(core):
    """'sse41' | 'sse2': the runtime the install's BUILD GAME picks on this PC, or None (an older install, or it
    could not answer). Asked only when the install ships the SSE2 runtime, so a normal install starts nothing."""
    if not shipped(core):
        return None
    ask = getattr(core, "this_pc_runtime", None)
    try:
        if callable(ask):
            answer = ask()                  # cached by the install for the life of the process
        else:
            build_game, prereqs = getattr(core, "build_game", None), getattr(core, "prereqs", None)
            pick = getattr(build_game, "runtime_for_this_pc", None)
            llvm = getattr(prereqs, "portable_llvm", None)
            if not callable(pick):
                return None
            answer = pick(llvm() if callable(llvm) else None)
            answer = answer[0] if isinstance(answer, (tuple, list)) and answer else answer
    except Exception:  # noqa: BLE001 -- never stop the Play page over this
        return None
    return answer if answer in RUNTIMES else None


def of_build(core, out_dir):
    """'sse41' | 'sse2': the runtime the build under out_dir was made with, None when there is no build stamp.
    A stamp without the field is from a build before 1.2.3, which only knew the normal runtime."""
    stamp = os.path.join(out_dir or "", "build", "t5dr_build.json")
    try:
        with open(stamp, encoding="utf-8") as stream:
            info = json.load(stream)
    except (OSError, ValueError):
        return None
    value = info.get("runtime", "sse41") if isinstance(info, dict) else None
    return value if value in RUNTIMES else None


def rebuild_for(core, out_dir):
    """The runtime this PC needs when the build has the other one ('sse2' | 'sse41'), else None."""
    built = of_build(core, out_dir)
    if built is None:
        return None
    want = this_pc(core)
    return want if want is not None and want != built else None
