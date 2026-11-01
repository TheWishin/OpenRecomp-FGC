# Pinned Qt startup regression

The launcher pins PySide6-Essentials 6.8.2.1. Its installed Python stubs
and QML module metadata were checked directly for this review.

Two Python calls were incompatible with that version:

- Startup called `QFontDatabase.addApplicationFallbackFontFamily`, which
  is absent. `make_engine` now registers the CJK fallback families with
  `QFont.insertSubstitutions` for Big Shoulders and IBM Plex Sans.
- Saving display preferences called `isMinimized` on the QML root window.
  That method belongs to QWidget, not QWindow. The backend now checks
  `windowState() & Qt.WindowMinimized` before changing the window mode.

The remaining Qt calls in `app.py`, and the Qt calls in the three developer
tools, match the installed `.pyi` signatures and enums. The pad, update
service and translation modules have no direct Qt calls.

All six QML files were checked against the installed `qmldir` and
`plugins.qmltypes` files, including inherited properties, attached
properties, signals and enums. No unavailable QML API was found. The pinned
`qmllint` exits successfully for all six files. It still reports static
outer-scope qualification advice in delegates; this is separate from
runtime QML warnings, which the startup regression must reject.

All seven language catalogs have matching sets of 1,075 keys, nonempty
string values and matching formatting placeholders.

The older scene test constructs its own backend and engine; the older
main-path tests mock `make_engine`. Neither can catch a crash inside the
real engine factory. `tests/test_startup_offscreen.py` is designed to exercise
that path with the offscreen platform, real Backend/Nav and synthetic
controller and adapter data. Its child process has a 55-second timeout and
an event-loop watchdog. It rejects engine warnings and QML message-handler
errors. The walk covers the shelf, T4 tools, ISO picker, blocked build,
synthetic build progress/result, cancel dialog, Host/Join, address keyboard,
log result, settings, quick access, seven languages and quit dialog.

Run it alone with:

```text
.venv\Scripts\python.exe -m unittest discover -s tests -p test_startup_offscreen.py
```

Run the required complete suite with:

```text
.venv\Scripts\python.exe -m unittest discover -s tests
```

Execution result for this checkout: the required complete-suite command
could not start because the virtual environment's base Python executable
is missing. No Python tests ran, and the new runtime test remains unverified.
The metadata, catalog and QML lint checks above did complete.

An offscreen test cannot establish visual layout, installed CJK glyph
coverage, physical controller behavior, real tool availability, ISO
validation, build success, real game startup, two-PC networking or the
contents of collected player logs. Those remain owner acceptance checks.
No game installation or player data is needed by the regression.
The synthetic adapter renders the empty settings page; installed T4 settings
content is outside its coverage. All seven catalogs are rebound in quick
access; the complete T4 walk uses English.
