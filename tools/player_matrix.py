"""Player release gate, using a package's portable Python and the real Qt launcher.

Inputs and reports belong outside the public checkout. See docs/PLAYER_MATRIX.md.
No missing input, skipped scenario, timeout or partial build counts as a pass.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_CASES = (
    "fresh-t5dr", "existing-t5dr", "parent-t5dr", "native-t5dr", "child-t5dr",
    "discover-old-t5dr", "missing-python", "missing-crypto", "no-winget", "t4-iso",
    "foreign-python", "no-python", "unicode-long-path",
)
REPAIRS = {"missing-python", "missing-crypto"}
T4_CASES = {"t4-iso", "no-winget"}
SCHEMA = 1
CHILD = Path(__file__).with_name("player_matrix_child.py")


class MatrixError(ValueError):
    pass


def package_root(path):
    path = Path(path).resolve()
    for root in (path, path / "OpenRecomp-FGC"):
        if ((root / "portable" / "pythonw.exe").is_file()
                and (root / "openrecomp" / "app.py").is_file() and (root / "games").is_dir()):
            return root
    raise MatrixError("Choose an unpacked release or Setup's installed OpenRecomp-FGC folder; portable/pythonw.exe is required")


def _files(root):
    root = Path(root)
    for path in sorted(root.rglob("*")):
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if path.is_symlink() or path.is_junction():
            raise MatrixError("Matrix inputs must not contain links or junctions")
        if path.is_file():
            yield path.relative_to(root).as_posix(), path


def _hash_files(entries, text=False):
    digest = hashlib.sha256()
    for name, path in sorted(entries):
        data = path.read_bytes()
        if text:
            data = data.replace(b"\r\n", b"\n")
        digest.update(name.encode("utf-8") + b"\0" + hashlib.sha256(data).digest())
    return digest.hexdigest()


def source_fingerprint(root):
    # Same omissions as the release bundle; CRLF checkouts match git archive's LF.
    omitted = {"icon.ico", "icon.svg", "logo-mark-light.svg", "logo-mark.svg",
               "logo-wordmark-light.svg", "logo-wordmark.svg"}
    entries = []
    for folder in ("openrecomp", "games"):
        for name, path in _files(Path(root) / folder):
            if folder == "openrecomp" and (path.name in omitted or name.startswith("ui/assets/ranks/t4_rank_")):
                continue
            entries.append((folder + "/" + name, path))
    for name in ("requirements.txt", "run.cmd"):
        path = Path(root) / name
        if path.is_file():
            entries.append((name, path))
    return _hash_files(entries, text=True)


def runtime_fingerprint(root):
    root = Path(root)
    if (root / "portable").is_dir():
        root /= "portable"
    if not (root / "pythonw.exe").is_file():
        raise MatrixError("The tested portable Python is missing")
    return _hash_files(_files(root))


def fingerprint(root):
    return _hash_files(_files(package_root(root)))


def isolated_env(home, mode, base=None, tools=()):
    home = Path(home).resolve()
    base = dict(os.environ if base is None else base)
    env = {k: v for k, v in base.items() if not k.upper().startswith(
        ("OPENRECOMP_", "T5", "T4", "TEKKEN4", "PYTHON", "QT_", "QML_", "PS3_", "VIRTUAL_ENV", "CONDA"))}
    env.update(HOME=str(home), USERPROFILE=str(home), APPDATA=str(home / "Roaming"),
               LOCALAPPDATA=str(home / "Local"), OPENRECOMP_HOME=str(home / "OpenRecomp"),
               TEMP=str(home / "Temp"), TMP=str(home / "Temp"),
               QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QT_QUICK_CONTROLS_STYLE="Basic",
               QML_DISABLE_DISK_CACHE="1", OPENRECOMP_NO_GAME_CHECKS="1", OPENRECOMP_UI_SOUND="0",
               OPENRECOMP_NATIVE_PICKER="0", PS3_AUDIO_MUTE="1", PS3_WINDOW_BACKGROUND="1",
               TEKKEN4_SOUND="0", PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
               HTTP_PROXY="http://127.0.0.1:9", HTTPS_PROXY="http://127.0.0.1:9", ALL_PROXY="http://127.0.0.1:9",
               NO_PROXY="127.0.0.1,localhost,::1")
    env["USERNAME"] = "J\u00f6rg M\u00fcller" if mode == "unicode-long-path" else "Matrix Player"
    # Always construct PATH; inherited dev Python, winget and package managers must not leak in.
    system = Path(base.get("SystemRoot", r"C:\Windows"))
    env["PATH"] = os.pathsep.join(str(p) for p in (system / "System32", system,
                                                system / "System32" / "WindowsPowerShell" / "v1.0"))
    if mode == "foreign-python":
        env["PATH"] = str(home / "foreign-python") + os.pathsep + env["PATH"]
    if tools:
        # A PC that has the build tools installed (Git is the one the T4 steps ask PATH for); never Python.
        env["PATH"] = os.pathsep.join([*(str(Path(t)) for t in tools), env["PATH"]])
    return env


def cases():
    return [dict(id=name, game="t4" if name in T4_CASES else "t5dr", mode=name,
                 selection={"parent-t5dr": "parent", "native-t5dr": "native", "child-t5dr": "child"}.get(name, "exact"))
            for name in REQUIRED_CASES]


def _same(a, b):
    return bool(a and b) and os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def evaluate_case(case_id, evidence, launcher):
    """Validate observations, never accept a child's self-reported PASS without evidence."""
    launcher = Path(launcher).resolve()
    if not _same(evidence.get("packaged_python"), launcher / "portable" / "pythonw.exe"):
        return "FAIL", "Launcher did not run with the package's portable/pythonw.exe"
    origin = Path(evidence.get("imported_launcher", "")).resolve()
    if origin not in (launcher / "openrecomp" / "app.py", launcher / "openrecomp" / "__init__.py"):
        return "FAIL", "Launcher code came from outside the tested package"
    if not evidence.get("qml_loaded"):
        return "FAIL", "The real launcher QML did not load"
    if evidence.get("fallback") or evidence.get("foreign_python_used"):
        return "FAIL", "A build step silently fell back to a different Python"
    if evidence.get("network_denied"):
        return "FAIL", "An unexpected external network operation was requested"
    if evidence.get("qml_warnings") or evidence.get("error"):
        return "FAIL", "The launcher reported a QML or callback error"
    if case_id in REPAIRS:
        if evidence.get("build_started") or evidence.get("build_python"):
            return "FAIL", "Damaged game Python was allowed to build"
        if not evidence.get("repair_message"):
            return "FAIL", "Damaged game Python has no clear repair message"
        return "PASS", "Damaged game runtime blocked with repair guidance"
    if case_id == "no-winget" and evidence.get("guidance") and not evidence.get("build_started"):
        return "PASS", "No winget: clear manual build-tools guidance"
    root = evidence.get("root")
    # Tekken 4 ships no Python of its own: it runs on the package's portable Python (never one found on PATH).
    expected = (launcher / "portable" / "pythonw.exe" if case_id in T4_CASES
                else Path(root or "") / "python" / "python.exe")
    if not _same(evidence.get("build_python"), expected):
        return "FAIL", ("Build did not use the package's portable Python" if case_id in T4_CASES
                        else "Build did not use the game's own python/python.exe")
    commands = evidence.get("commands", [])
    if not commands or not any(_same(c[0], expected) and c[1:] not in (
            ["--version"], ["-version"], ["/?"], ["-I", "-c", "from Crypto.Cipher import AES"])
            for c in commands if isinstance(c, list) and len(c) > 1):
        return "FAIL", "No observed build process using the game's Python"
    if not evidence.get("build_started") or not evidence.get("first_steps"):
        return "FAIL", "Build start and successful first steps were not observed"
    if case_id == "discover-old-t5dr" and (not evidence.get("offered_existing") or evidence.get("second_copy")):
        return "FAIL", "Existing install was not offered without creating a second copy"
    if case_id in {"existing-t5dr", "parent-t5dr", "native-t5dr", "child-t5dr"}:
        if not _same(root, evidence.get("expected_root")):
            return "FAIL", "Selected folder did not resolve to the expected install root"
    return "PASS", "Game Python observed; build's first steps succeeded"


def check_matrix_report(report_path, *, commit, source_root, runtime_root):
    try:
        report = json.loads(Path(report_path).read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise MatrixError("Matrix report must be an object")
        if report.get("schema") != SCHEMA or report.get("source_commit") != commit:
            raise MatrixError("Matrix report has the wrong schema or source commit")
        if report.get("package_unchanged") is not True:
            raise MatrixError("Tested package changed during the matrix run")
        launcher = package_root(report["launcher"])
        for key, actual in (
            ("source_fingerprint", source_fingerprint(source_root)),
            ("runtime_fingerprint", runtime_fingerprint(runtime_root)),
            ("package_fingerprint", fingerprint(launcher)),
        ):
            if report.get(key) != actual:
                raise MatrixError("Stale matrix report: " + key + " changed")
        if source_fingerprint(launcher) != report["source_fingerprint"]:
            raise MatrixError("Tested package does not contain the source being released")
        if runtime_fingerprint(launcher) != report["runtime_fingerprint"]:
            raise MatrixError("Tested package does not contain the runtime being released")
        rows = report["cases"]
        if not isinstance(rows, list) or any(not isinstance(r, dict) or not isinstance(r.get("evidence"), dict)
                                             for r in rows):
            raise MatrixError("Matrix cases need observation objects")
        if len(rows) != len(REQUIRED_CASES) or {r["id"] for r in rows} != set(REQUIRED_CASES):
            raise MatrixError("Matrix report is incomplete or contains duplicate cases")
        for row in rows:
            status, reason = evaluate_case(row["id"], row.get("evidence", {}), launcher)
            if row.get("status") != "PASS" or status != "PASS":
                raise MatrixError("Matrix case " + row["id"] + " did not pass: " + reason)
        return dict(schema=SCHEMA, source_commit=commit, package_fingerprint=report["package_fingerprint"],
                    report_sha256=hashlib.sha256(Path(report_path).read_bytes()).hexdigest(),
                    cases=len(rows), status="PASS")
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise MatrixError("Missing or invalid player matrix report") from error


@contextmanager
def heavy_slot(folder):
    """CreateNew/exclusive creation: never steal or remove another run's lock."""
    folder = Path(folder)
    lock = None
    for name in ("HEAVY.lock", "HEAVY2.lock", "HEAVY3.lock"):
        candidate = folder / name
        try:
            with candidate.open("x", encoding="utf-8") as stream:
                stream.write("player-matrix " + datetime.now(timezone.utc).isoformat() + " packaged launcher\n")
            lock = candidate
            break
        except FileExistsError:
            continue
    if lock is None:
        raise MatrixError("All heavy slots are occupied; rerun when one is free")
    try:
        yield lock
    finally:
        lock.unlink()


def _copy_install(source, target):
    # Fixtures may contain private game data: this is only used inside the scratch directory.
    source = Path(source)
    if source.is_symlink() or source.is_junction():
        raise MatrixError("Existing install is a link/junction")
    source = source.resolve()
    if target.resolve().is_relative_to(source):
        raise MatrixError("Scratch must not be inside an input install")
    if not source.is_dir():
        raise MatrixError("Configured existing install is missing")
    for path in source.rglob("*"):
        if path.is_symlink() or path.is_junction():
            raise MatrixError("Existing install contains a link/junction; use a plain test copy")
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", ".git"))


def prepare_case(home, case, inputs):
    inputs = dict(inputs)
    for name in ("Roaming", "Local", "OpenRecomp", "Temp"):
        (home / name).mkdir(parents=True, exist_ok=True)
    (home / "OpenRecomp" / "config.json").write_text(
        json.dumps(dict(language="en", fullscreen=False, ui_sounds=False)), encoding="utf-8")
    if case["id"] == "foreign-python":
        folder = home / "foreign-python"
        folder.mkdir()
        # A poison executable, never a working Python: selecting it must fail the gate.
        (folder / "python.exe").write_bytes(b"player-matrix foreign Python must never run\r\n")
        (folder / "python3.exe").write_bytes(b"player-matrix foreign Python must never run\r\n")
    source_key = "t4_root" if case["game"] == "t4" else "t5dr_existing"
    source = inputs.get(source_key)
    if source and case["id"] != "fresh-t5dr":
        target = home / "Downloads" / ("T4" if case["game"] == "t4" else "T5DR-Online-old")
        if case["id"] == "unicode-long-path":
            # The long, umlaut-and-space *profile* is what is under test (settings, caches, temp). A game folder as
            # long as that profile would pass Windows' 260 characters inside the game's own Python (pycryptodome's
            # native module fails with WinError 206), which is a different, unrealistic case.
            target = home.parent / "Spiele Jörg Müller" / ("T4" if case["game"] == "t4" else "T5DR-Online-old")
        target.parent.mkdir(exist_ok=True)
        _copy_install(source, target)
        inputs[source_key] = str(target)
        if case["game"] == "t5dr" and inputs.get("t5dr_existing_managed"):
            # An install an earlier OpenRecomp launcher made. One only borrowed from T5DR's own launcher cannot
            # be built in OpenRecomp (docs/T5DR_COEXISTENCE.md), so that fixture could never reach a build step.
            (target / "openrecomp-release.json").write_text(json.dumps(dict(
                game="t5dr", installed_by="OpenRecomp-FGC", version="0.0.0", tag="v0.0.0")), encoding="utf-8")
        inputs["expected_root"] = str(target)
        selection = case.get("selection", "exact")
        case["selection"] = str({"parent": target.parent, "native": target / "native",
                                 "child": target / "launcher"}.get(selection, target))
        if case["id"] == "discover-old-t5dr":
            case["selection"] = ""
        if case["id"] == "missing-python":
            damaged = target / "python"
            if damaged.exists():
                damaged.rename(target / "matrix-quarantined-python")
        if case["id"] == "missing-crypto":
            found = list((target / "python").rglob("Crypto"))
            if not found:
                raise MatrixError("Cannot simulate Crypto quarantine: unpacked Crypto directory not found")
            for damaged in found:
                damaged.rename(damaged.with_name("matrix-quarantined-Crypto"))
    elif case["id"] != "fresh-t5dr":
        case["selection"] = ""
    return inputs


def _run_process(command, *, timeout, check=False, **kwargs):
    """A Windows job closes the whole owned process tree, including on timeout."""
    import ctypes
    from ctypes import wintypes

    job = None
    kernel = None
    if os.name == "nt":
        class Basic(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                        ("flags", wintypes.DWORD), ("minimum", ctypes.c_size_t), ("maximum", ctypes.c_size_t),
                        ("active", wintypes.DWORD), ("affinity", ctypes.c_size_t),
                        ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]

        class Extended(ctypes.Structure):
            _fields_ = [("basic", Basic), ("io", ctypes.c_uint64 * 6),
                        ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                        ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        job = kernel.CreateJobObjectW(None, None)
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not job or not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            if job:
                kernel.CloseHandle(job)
            raise OSError("Cannot create a job to contain the matrix process tree")
    try:
        with subprocess.Popen(command, **kwargs) as process:
            if job and not kernel.AssignProcessToJobObject(job, wintypes.HANDLE(int(process._handle))):
                process.kill()
                process.wait()
                raise OSError("Cannot contain the packaged launcher in its process job")
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                if job:
                    kernel.CloseHandle(job)
                    job = None
                process.kill()
                process.wait()
                raise
            return subprocess.CompletedProcess(command, process.returncode)
    finally:
        if job:
            kernel.CloseHandle(job)


def _case_tools(case, inputs):
    """Folders of tools a normal player PC has on PATH, for the one case that models such a PC (config `tools_path`)."""
    folders = inputs.get("tools_path") or []
    if case["id"] != "t4-iso":
        return []
    return [f for f in folders if Path(f).is_dir() and not list(Path(f).glob("python*.exe"))]


def run_case(launcher, scratch, case, inputs, *, full=False, timeout=180, run=None):
    case = dict(case)
    home = Path(scratch) / case["id"]
    if case["id"] == "unicode-long-path":
        home /= ("J\u00f6rg M\u00fcller " + "long player folder " * 5).rstrip()
    home.mkdir(parents=True, exist_ok=False)
    result_path = home / "result.json"
    row = dict(id=case["id"], status="BLOCKED", reason="", evidence={}, result=str(result_path))
    started = time.monotonic()
    try:
        prepared = prepare_case(home, case, inputs)
        request = dict(launcher=str(launcher), home=str(home), case=case, inputs=prepared, full=full, timeout=timeout)
        request_path = home / "request.json"
        request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
        command = [str(Path(launcher) / "portable" / "pythonw.exe"), "-B", str(CHILD),
                   "--request", str(request_path), "--result", str(result_path)]
        flags = (subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS) if os.name == "nt" else 0
        with (home / "launcher-output.txt").open("w", encoding="utf-8") as output:
            completed = (run or _run_process)(command, cwd=str(launcher), env=isolated_env(home, case["mode"], tools=_case_tools(case, inputs)),
                            stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                            timeout=timeout + 30, creationflags=flags, check=False)
        if not result_path.is_file():
            raise MatrixError("Packaged launcher produced no result (exit " + str(completed.returncode) + ")")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        row["evidence"] = result.get("evidence", {})
        if result.get("status") == "BLOCKED":
            row["reason"] = result.get("reason", "Missing player input")
        else:
            row["status"], row["reason"] = evaluate_case(case["id"], row["evidence"], launcher)
            if completed.returncode or result.get("status") != "PASS":
                row.update(status="FAIL", reason=result.get("reason") or "Packaged launcher failed")
    except subprocess.TimeoutExpired:
        row.update(status="FAIL", reason="Packaged launcher timed out")
    except (OSError, MatrixError, ValueError) as error:
        row["reason"] = str(error)
    row["seconds"] = round(time.monotonic() - started, 2)
    return row


def print_table(rows):
    print("| Case | Result | Evidence / reason |")
    print("|---|---|---|")
    for row in rows:
        print("| " + row["id"] + " | " + row["status"] + " | " + row["reason"].replace("|", "/").replace("\n", " ") + " |")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--launcher", required=True, type=Path, help="unpacked release or installed Setup folder (read only)")
    parser.add_argument("--scratch", type=Path, default=Path(r"D:\or-matrix"))
    parser.add_argument("--config", type=Path, help="private matrix inputs JSON; no accounts or credentials")
    parser.add_argument("--report", type=Path, help="default <run>/report.json")
    parser.add_argument("--heavy-lock-dir", type=Path, default=Path(r"C:\T5DROnline\build\int115"))
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--full", action="store_true", help="request a complete build; unauditable native pipelines remain blocked")
    args = parser.parse_args(argv)
    try:
        launcher = package_root(args.launcher)
        scratch = args.scratch.resolve()
        if scratch == ROOT or ROOT in scratch.parents:
            raise MatrixError("Private player runs must stay outside the public checkout")
        scratch.mkdir(parents=True, exist_ok=True)
        run_root = scratch / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f"))
        run_root.mkdir()
        inputs = json.loads(args.config.read_text(encoding="utf-8")) if args.config else {}
        if not isinstance(inputs, dict):
            raise MatrixError("Matrix config must be an object of input paths")
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        before = fingerprint(launcher)
        rows = []
        for case in cases():
            try:
                with heavy_slot(args.heavy_lock_dir):
                    row = run_case(launcher, run_root, case, inputs, full=args.full, timeout=args.timeout)
            except (MatrixError, OSError) as error:
                row = dict(id=case["id"], status="BLOCKED", reason=str(error), evidence={})
            rows.append(row)
            print(case["id"] + ": " + row["status"] + " - " + row["reason"], flush=True)
        unchanged = before == fingerprint(launcher)
        report = dict(schema=SCHEMA, created=datetime.now(timezone.utc).isoformat(), launcher=str(launcher),
                      source_commit=commit, source_fingerprint=source_fingerprint(launcher),
                      runtime_fingerprint=runtime_fingerprint(launcher), package_fingerprint=before,
                      full=args.full, package_unchanged=unchanged, cases=rows)
        report_path = args.report or run_root / "report.json"
        if ROOT == report_path.resolve() or ROOT in report_path.resolve().parents:
            raise MatrixError("Matrix reports contain private paths and must stay outside the checkout")
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print_table(rows)
        print("Report: " + str(report_path))
        if not unchanged:
            print("FAIL: tested package changed during the run")
        return 0 if unchanged and all(row["status"] == "PASS" for row in rows) else 1
    except (MatrixError, OSError, ValueError, subprocess.SubprocessError) as error:
        print("player_matrix: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
