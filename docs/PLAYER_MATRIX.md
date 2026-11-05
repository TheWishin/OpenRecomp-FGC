# Player release matrix

`tools/player_matrix.py` drives the real packaged module entry point, Backend,
controller picker and QML offscreen. Its coordinator may use a development Python;
each case runs with the selected package's **portable/pythonw.exe**. Neither the
development adapters nor synthetic game builds can satisfy a release report.

Use an unpacked release candidate or Setup's installed `OpenRecomp-FGC` folder.
Prepare the candidate with the existing bundle tools before the final
`make_release.py` invocation. The final release packager refuses to proceed until
the candidate's source and portable runtime match a passing report.

```powershell
python tools/player_matrix.py --launcher D:\or-matrix\candidate\OpenRecomp-FGC `
    --config D:\or-matrix\inputs.json
```

Keep the inputs file, reports and all run folders outside this public repository.
The private JSON object accepts these fields:

| Field | Read-only input |
|---|---|
| `t5dr_existing` | An old-launcher T5DR install folder |
| `t5dr_release` | Exactly one signed T5DR release zip, SHA256SUMS and SHA256SUMS.sig |
| `t5dr_pkg`, `t5dr_rap` | The owner's own package and licence paths |
| `t4_root` | A T4 install/source folder |
| `t4_iso` | The owner's ISO path, read from their configuration |
| `t5dr_keys` | Optional. A `ps3.keys` made offline (`tools/make_keys.py --source <folder with key_vault.h/.cpp>`); copied into each T5DR case's `native/keys` because the build's first step otherwise downloads the key data from github.com, which the offline guard refuses |
| `t5dr_existing_managed` | Optional, `true`: the private copy of `t5dr_existing` gets OpenRecomp's install marker (an install an earlier OpenRecomp made). Without it (the default, and the real situation of a player who used T5DR's own launcher) the folder is one T5DR's launcher set up, which OpenRecomp builds after a one-time notice while T5DR's launcher keeps working on it (`T5DR_COEXISTENCE.md` "Building a folder from the T5DR launcher") |
| `tools_path` | Optional list of folders put first on PATH in the `t4-iso` case only (a PC that has Git installed); folders containing a `python*.exe` are ignored |

The tool never reads account fields, logs in or starts a game. It copies the
configured existing installs into each private case folder before folder selection
or simulated antivirus quarantine; the input folders and ISO/package/licence files
are not changed. Copies can be large; budget enough scratch space. Fixture folders
must not contain symlinks or junctions. Do not put the scratch directory inside an
input install.

There are 13 required cases:

| Case | Required observation |
|---|---|
| `fresh-t5dr` | Install through the launcher's signed local release transport, then build |
| `existing-t5dr` | Choose the old folder exactly |
| `parent-t5dr`, `native-t5dr`, `child-t5dr` | Each selection resolves to that same root |
| `discover-old-t5dr` | Existing install offered, no second install offered |
| `missing-python`, `missing-crypto` | Visible repair action and message, no build starts |
| `no-winget` | T4 build-tools fallback or actionable manual guidance |
| `t4-iso` | Select the owner's ISO and start its build |
| `foreign-python`, `no-python` | Game's own Python used regardless of PATH |
| `unicode-long-path` | Spaces, umlauts and a long private profile path |

Every successful T5DR build case needs an observed process using `<game>/python/python.exe`,
successful early build steps, and the compile boundary. Tekken 4 has no Python of its own: its
disc image check and build run on the package's `portable/pythonw.exe` (`-I -B`), and that
is the one Python the T4 cases accept; any other Python, found on PATH or not, is a failure.
A launcher-Python fallback in T5DR is a failure. Known older packages may therefore fail this gate.
Tekken 4's build is a PowerShell pipeline (`tools/build_game.ps1`): the guard cannot audit it, so
`t4-iso` is **BLOCKED** until an externally isolated offline machine or sandbox exists. The owner has approved one
named waiver for exactly that case (2026-11-05): `player_matrix.py --waive t4-iso` turns a BLOCKED `t4-iso` into
`WAIVED`, with the original reason, the owner's reason and the Tekken 4 v0.1.1 release gate as reference written into
the report row (`WAIVERS` in `tools/player_matrix.py`). `make_release.py` accepts the report only for that waiver, word
for word, on that case, and only if the case was BLOCKED: no other case, and no FAIL, skipped or timed-out case, can be
waived, and the waiver is recorded in the release facts. Every other case must still pass.
Repair and manual-guidance cases pass only without starting an inappropriate build.

The default run stops before spawning CMake/Ninja/compiler work. `--full` allows
long Python build work and requires a successful build result. Native compilation
in full mode is currently BLOCKED: native tools cannot inherit Python network
auditing, and no system network/security setting is changed. Full native coverage
needs an externally isolated offline machine/sandbox before it can be supported.
The runner never guesses a
successful build from elapsed time, a progress label alone or a started process.
Skipped, missing-input and blocked cases prevent release, as do timeouts and errors.

All homes, caches and temporary files go under a new timestamped run folder in
`D:\or-matrix` (or explicit `--scratch`). Each case exclusively acquires one of the
three `HEAVY*.lock` slots and releases it on completion or failure. Use
`--heavy-lock-dir` on another coordination machine. Descendant processes run hidden,
muted, in the background and BelowNormal, contained in Windows kill-on-close jobs.
Timeouts terminate the owned process tree. The runner does not change Windows
settings or kill unrelated processes.

Python audit hooks refuse external DNS, non-loopback sockets, writes outside the
private case, unaudited subprocesses and shell/install pipelines. Build Python
subprocesses inherit the same guard through the driver. Local release transport
uses the packaged launcher's signature/checksum/unpack code; it does not replace
the installer. A shell/native pipeline that cannot preserve these guarantees is
reported BLOCKED. Such a run is evidence of incomplete coverage and cannot release.

The console prints a case table. Exit codes are 0 for every required case passing,
1 for a failed or blocked matrix, and 2 for invalid invocation/setup. Each run
contains `report.json`; each case contains `request.json`, `result.json`, launcher
output and safety observations. These contain private local paths; never commit them.

Pass the report to the final packager:

```powershell
python tools/make_release.py <release arguments> --matrix-report D:\or-matrix\run-<timestamp>\report.json
```

The packager rechecks all case evidence, commit, launcher source, full package and
portable runtime fingerprints before creating release output. Checkout CRLF text
matches the release archive's LF text. A missing, duplicate, skipped, blocked,
failed, modified or stale report is refused. Release facts record the accepted
report digest and package identity. A package modified during testing is refused.
After a launcher/runtime change, rerun the matrix. `--skip-matrix` works only with
`--rehearsal` and `OPENRECOMP_RELEASE_TESTS=1`, and records `skipped-for-tests` in the
release facts; it is for packager tests, not release approval.

Tests use inert fixtures, fake builds and mocked process boundaries:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests
```
