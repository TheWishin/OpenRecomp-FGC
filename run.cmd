@echo off
rem Starts OpenRecomp-FGC. Prefer the bundled runtime; otherwise prepare .venv on first start.
setlocal
cd /d "%~dp0"
if exist "portable\python.exe" if exist "portable\pythonw.exe" (
    start "" "portable\pythonw.exe" -B -m openrecomp %*
    exit /b 0
)
if not exist ".venv\Scripts\python.exe" (
    echo First start: installing PySide6...
    py -3.12 -m venv .venv || python -m venv .venv || goto :nopython
    ".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt || goto :nopip
)
start "" ".venv\Scripts\pythonw.exe" -m openrecomp %*
exit /b 0

:nopython
echo Python 3.12 was not found. Install it from https://www.python.org/downloads/ and start this file again.
pause
exit /b 1

:nopip
echo PySide6 could not be installed. Check the internet connection and start this file again.
pause
exit /b 1
