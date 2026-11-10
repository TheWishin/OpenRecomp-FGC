# OpenRecomp-FGC 0.1.7: how the release branch was put together

Branch `release-0170`, made on 2026-11-10 from `release-017-all` (3f9f9d6), the newest of the three candidates
(`launcher-rel-018` e9bb344 and `header-progress-018` 2b1627d are its ancestors; `hotfix-prep-0161` a2c37de is the
0.1.6 hotfix line and older in content). Nothing was tagged, pushed, published or built as an installer.

## Merges and decisions

1. **`hotfix-0.1.6.1` (6179454), L1/R2 binding save fix.** The base already has this fix as a0d43dd (the same change,
   plus the trigger resting-end guard, the HID PlayStation reader and the settings sync that came after it). Every
   conflict (`openrecomp/controls_file.py`, `adapters/t5_controls.py`, `adapters/t5_coexist.py`,
   `tests/test_controls_shared.py`, `tests/test_package_release.py`, `tools/package_release.py`, `CHANGELOG.md`) keeps
   the base: the hotfix side is the older text of the same files and would have removed the resting-end guard and
   three modules from the package list. Taken from the hotfix: its one extra test (a second binding of a session saves
   and keeps the first). `hotfix-prep-0161` was not merged: its changelog line d503873 ("not yet tested with a real pad
   or from a packaged build") is in the v0.1.7 section under Known, and its version commit a2c37de is what step 5 does.
2. **`header-progress-018` (2b1627d).** Already in the base (merge 3f9f9d6). No new merge.
3. **`tag2-adapter-018` (cf73942).** Conflicts only in the seven catalogs: both sides appended keys at the end; all are
   kept (1,963 keys in each language). The gate:
   - The adapter's functions need the published 0.16.33 Core (`tag2_core.TRUSTED_CORES`, SHA-256). Any other TAG2
     version, a missing Core or no Windows PowerShell: the manifest behaviour, TAG2's own launcher.
   - The branch showed sign-in, Play online and Ranked rows as soon as the Core was trusted. They are now off unless
     `OPENRECOMP_TAG2_ONLINE=1` or `"tag2": {"online": true}` is set (own commit after the merge, with tests): by
     default the Online section is the manifest's row (TAG2's own launcher) and the adapter sends nothing to TAG2's
     service.
   - Updates, build, patch, repair and controllers stay with TAG2's own launcher (the adapter has no updater handoff).
   - The no-audio warning is in unchanged.
   - Note: the TAG2 tile itself comes from `games/tag2.json`, which the base already had: it is shown for any TAG2 PC
     install that is found, and opens TAG2's own launcher. That was not changed.
4. **`quick-binds-018`: left out.** The branch is in the T5DR game repository (worktree `D:\t4-night\w018\quickbinds`),
   not in this one, and had no commit of its own (tip = T5DR main db9711a5, clean tree) when this branch was made.
5. **Version 0.1.7** in `openrecomp/__init__.py`, section `v0.1.7` in CHANGELOG.md (the former "Unreleased" entries,
   sorted into Fixed / New / Known).

## To test by hand before the pre-release

- A real pad (Xbox and DualSense/DualShock 4): bind L1, R2 and several buttons in one session in Tekken 5 Pad
  bindings, close and reopen the page, check the game uses them.
- The top bar during a real build and a real launcher update: step, percentage, time left, click / F7, gone at the end.
- Tekken 5 DR settings and controls in both launchers: change in one, see it in the other; the backups exist.
- TAG2 with a real 0.16.33 install: tile, Play (offline through the Core), quick settings, the warning with no audio
  output; an older or newer TAG2 version opens TAG2's own launcher. Ranked and sign-in stay off.
- `--offline`, and a T5DR rematch in the game.
- From a packaged build: the PowerShell host of the TAG2 part with an antivirus on.
