# Rules for coding agents

This repository is public. These rules apply to any agent working here, on any task.

## Never in this repository
No game data of any kind: ISO, packages, licences, executables, saves, game pictures or screenshots, translated or generated game code. No keys, no BIOS, no player logs, no personal paths or email addresses. Pictures on the launcher come from the player's own build and stay on their PC.

## Stay inside this repository
- Read and change files only in this folder. `adapters/` load each game's own code from its install at run time: do not open, copy or quote those installs.
- Do not start a game, a build or an online search. Do not press Ranked or Quick Match. Do not take screenshots of the running launcher: they can show game art.
- Do not change system or security settings.

## Git
- **Do not commit, push, merge, tag, release or open pull requests.** Leave your changes in the working tree. The maintainer reviews them and does all of that.
- Read-only git commands are fine (`git status`, `git diff`, `git log`, `git show`). Do not create or switch branches.
- One topic per task. Do not reformat or restructure code the task does not need.

## Code
- Python 3.12 + PySide6 + QML. Match the surrounding code: its naming, its comment density, its idiom. No new dependency without asking.
- `openrecomp/nav.py` is the whole state machine and has no Qt: actions in, one plain dict out. Keep it that way. `adapters/base.py` is the only interface the screens use.
- Every screen must work by controller alone.
- Every fix or feature gets a test that fails on the old code and passes on the new.

## Check before you hand over
Run `.venv\Scripts\python.exe -m unittest discover -s tests` (`run.cmd` makes `.venv` on first start). All tests must pass.

Your report says: test result, what changed, and plainly what you did not or could not check.

## Tests: never with the installed Python
Never run tests with the installed portable Python (`...\OpenRecomp-FGC\portable\python.exe`) and never touch the
owner's real install folder: its `python312._pth` ignores the cwd, so the INSTALLED launcher gets imported and an
uninstall test removed real T5DR/T4 installs. Use the repo's `.venv` or the system Python from the worktree root.
Safety nets (`openrecomp/safety.py`): a test run (unittest/pytest/`OPENRECOMP_TESTING=1`) redirects LOCALAPPDATA,
APPDATA, USERPROFILE, HOME and OPENRECOMP_HOME to a temp sandbox and `uninstall.execute` raises for any path outside
the temp folders. New tests that touch installs must still use their own temp dirs.
