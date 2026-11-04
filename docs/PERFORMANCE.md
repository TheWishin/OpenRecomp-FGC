# Launcher performance

Measured on Windows, Python 3.12 / PySide6, on 2026-11-04. Results below are
medians of three fresh processes per version, each with a 60-second idle
interval. The benchmark runs offscreen with software rendering, fake adapters,
a fake lobby and a synthetic colour swatch. It never starts games or builds,
uses player installs, connects to a network, or captures screenshots.

| Metric | Before | After |
| --- | ---: | ---: |
| Process start to first populated frame | 1,675.56 ms | 777.56 ms |
| Process start to usable hub | 1,701.38 ms | 834.13 ms |
| Idle working set (MiB) | 95.42 | 88.95 |
| Working set after page walk (MiB) | 108.12 | 103.77 |
| Idle CPU, one core = 100% | 1.875% | 1.146% |
| Navigation CPU, one core = 100% | 20.734% | 20.102% |
| Navigation stalls >50 ms, count / worst across all runs | 3 / 95 ms | 0 / 0 ms |
| Startup logical read bytes (MiB) | 8.40 | 7.48 |
| Startup logical read operations | 3,736 | 3,434 |
| Cumulative `openrecomp.app` import time (ms) | 367.02 | 209.28 |

Start-to-interactive improved **51.0%**, exceeding the 30% target. Idle working
set fell 6.8%, visited-page working set 4.0%, and idle CPU 38.9%. No navigation
stall exceeded 50 ms in the final three runs. Idle CPU remains measurable at
1.146% of one core; a strict near-zero idle target is not established here.

Work moves from startup to first visits. Median first action-to-render intervals:

| Section | Before | After |
| --- | ---: | ---: |
| Online | 102.54 ms | 134.97 ms |
| Build | 22.81 ms | 64.70 ms |
| Settings | 21.19 ms | 44.93 ms |

These intervals include asynchronous loading across multiple frames and do not
mean the GUI thread was blocked for their duration.

## Changes

- Shelf, hub, online layouts, build, settings and overlays use an asynchronous
  `PageLoader`. A page exists only while its loader is active. The required
  root property is supplied before bindings run. Navigation state stays in Nav;
  no Qt was added to the state machine. The release inventory includes the loader.
- Library and game-update modules load when their operations are requested.
  Game setup is created when needed; idle polling and shutdown do not create it.
  Setup's release descriptions are imported only by its relevant views.
  The launcher updater imports HTTP dependencies when its transport is used;
  its URL/redirect checks remain enforced and covered by existing tests.
- Controller polling remains at 16 ms. Background model/update polling is
  coalesced to about 100 ms; holds and toasts retain frequent updates. Window
  visibility/focus is cached from Qt signals instead of queried every pad tick.
- The fast timer stops when hidden, minimized or a game runs. A 250 ms
  maintenance timer continues processing completions. Tile/status reconciliation
  stays at 0.5 seconds, within the five-second refresh bound. T4's existing
  controller return chord retains fast polling while its game runs.
- Preference saves coalesce over 200 ms, flush at exit, and surface save errors.
  Transactional library/install writes keep their existing immediate behavior.
- The logo path is checked once and unchanged views do not notify QML. Existing
  asynchronous, shared Qt caching of fighter/rank images is retained; the logo
  also loads asynchronously. No new dependencies or game-file caches were added.

## Reproduction

From the repository root, set `$python` to the launcher's Python 3.12 interpreter:

```powershell
& $python tools/perf_probe.py --label before --runs 3 --idle-seconds 60
# Apply the optimization, then use the same probe:
& $python tools/perf_probe.py --label after --runs 3 --idle-seconds 60
```

For this continuation, the original launcher sources were copied under ignored
`build/perf-baseline/` before changing them. The same probe was run there for
`before`; the final working tree was measured with label `final`. Earlier runs
that overlapped unittest discovery were excluded. Raw results are local only:

- `build/perf-baseline/build/perf/before/results.json`
- `build/perf/final/results.json`
- Corresponding `<run>-importtime.txt` files contain per-module `-X importtime`.

Each child isolates OPENRECOMP_HOME, APPDATA, LOCALAPPDATA, TEMP and TMP under
its repository's `build/tmp-home/`. Python socket connects/binds and subprocess
creation are blocked in the child. Hardware readers and automatic update checks
are replaced with fakes. The synthetic image is a 1024px plain colour PNG under
`build/perf-assets/`, shared by fake hero, fighter and rank image sources.

The clock begins immediately before child process creation. First frame waits
for the shelf's active loaders and a populated frame. Interactive waits for a
controller confirm to enter the hub, all active page loaders to finish, and a
rendered frame. Idle starts after a one-second settling interval. CPU is process
CPU time divided by elapsed wall time; 100% means one fully occupied core.
The diagnostic watchdog and its heartbeat are stopped during idle CPU sampling,
then a fresh 50 ms stall watch measures navigation. The main input timer still
wakes approximately 3,750 times per idle minute; model polling is coalesced.

The walk covers shelf, play, online, build, replays, settings, drawer, and login,
status-card and logged-in lobby layouts, using semantic controller actions.
`page_first_render_ms` records the first action-to-render interval for each
section, including model work, QML loading/incubation and drawing. Loading pages
on demand moves work to first visits; those visits can take longer while the
GUI stays responsive. `qml_compile_ms` is a separate warm component lookup
measurement after the walk, not a cold compilation or creation measurement.

## Limits and verification

Fresh process means the QML disk cache is disabled; the OS file cache is not
flushed. Startup includes the offline fixture/instrumentation imports, and is
not a measurement of discovery against real installations. Working set includes
shared native pages and Qt caches; it is not private allocated memory.
The probe exercises Backend and make_engine directly; the CLI's taskbar setup,
other-launcher detector and update-confirmation handshake are outside its timing.

Process I/O counters are logical reads, not physical disk traffic. The startup
Python audit inventory gives repository file opens and file sizes, not bytes
actually read per file. Native Qt QML/font/image opens are not inventoried;
`asset_files` lists available repository assets and their sizes. The image-mode
inventory checks asynchronous loading and shared-cache flags with synthetic
assets. Exact decode durations and native-thread attribution require a Qt
profiler and were not measured. Real game art, controllers, installations,
network behavior, desktop rendering and physical cold-disk startup were not
checked. The stall table covers navigation, with watchdog overhead excluded
from the idle CPU interval.

Python thread names, backend timer intervals and input timeout counts are
recorded; native Qt thread wakeups are not enumerated individually.

The regression tests cover lazy service construction, controller access to all
sections (including optional controls/support), asynchronous online layouts,
inactive page destruction, deferred save/error/exit behavior, unchanged-view
caching, window-state caching, and background tile maintenance. Existing module
and geometry tests now await deferred work before checking their original
assertions. The T4 region fixture models a separate launcher/home even when
TEMP is under this checkout; the production path guard is unchanged.
The watchdog stack test excludes scheduling before its initial heartbeat from
the controlled pause it asserts.

Run the full suite with isolated homes:

```powershell
$env:OPENRECOMP_HOME = Join-Path $PWD 'build/tmp-home/tests'
$env:APPDATA = $env:OPENRECOMP_HOME
$env:LOCALAPPDATA = $env:OPENRECOMP_HOME
$env:TEMP = $env:OPENRECOMP_HOME
$env:TMP = $env:OPENRECOMP_HOME
$env:QT_QPA_PLATFORM = 'offscreen'
& $python -m unittest discover -s tests -p 'test_*.py'
```

Final verification: **1,775 tests run in 189.514 seconds, 15 skipped, no failures
or errors** (`OK (skipped=15)`). The exact discovery command above passed with
all five home/temp variables isolated under `build/tmp-home/tests/` and the
offscreen platform. Output is retained locally in `build/full-tests-pass.txt`.
`git diff --check` also passes. No commit or other Git write was made.

## Changed files

- `.gitignore`, `docs/PERFORMANCE.md`
- `openrecomp/app.py`, `openrecomp/app_game_setup.py`, `openrecomp/nav_game_setup.py`, `openrecomp/updater.py`
- `openrecomp/ui/Main.qml`, `openrecomp/ui/Hub.qml`, `openrecomp/ui/PageLoader.qml`
- `tools/perf_probe.py`, `tools/package_release.py`
- `tests/test_gui_stalls.py`, `tests/test_launcher_perf.py`, `tests/test_module_entrypoint.py`, `tests/test_online_bc_ui.py`, `tests/test_t4_region.py`, `tests/test_ui_polish.py`
