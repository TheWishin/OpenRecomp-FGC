This UI continuation preserves the two earlier uncommitted rounds. Changes remain in the working tree for maintainer review. No commit, branch change, push, release, or pull request was made.

The per-game home for T5DR and T4 is now a vertical main menu with large entries, an accent marker, a thin player/activity status bar, and the existing player-owned background when available. Missing server capabilities hide their entries. An unfinished installation retains its setup flow. Opening Ranked or Quick match opens a page; starting matchmaking still requires a separate confirmation. Practice focuses the game's existing practice-tools setting when supported; a training HUD option alone is not represented as a practice mode. Back returns from a page to the main menu. Controller shoulder navigation remains available.

Online uses one type scale and shared titles, section cards, labels, values, help text, buttons, chips, and tables. Lobby, Rooms, Friends, Leaderboard, Statistics, Profile, Tournaments, Spectating, Account, and the find-opponent card share that hierarchy. Rooms separates browsing, room creation, and invite-code joining. The Create action stays visible while its fields scroll; empty help text no longer reserves space. Chat stays docked on Online pages. Settings has Video, Audio, Controls, Game, and Help tabs; rows show a bold label, a muted subtitle, and a right-aligned value.

Actions have hover, pressed, and focus outlines and accessible names/roles. A single table click selects; double-click or A/Enter acts. Challenge rows show an in-place waiting receipt, time, Profile and Cancel actions, and matching controller hints. Server decline/expiry results remain visible briefly. Room, friend, invite, and search actions have in-place pending/result/error receipts. Result toasts appear at the top right for about three seconds and fade unless reduced motion is enabled. The footer remains available.

Challenge time is truthful: a server-provided duration produces a countdown. A legacy server that supplies no deadline shows elapsed waiting time instead. The UI does not invent an expiry or automatically cancel a challenge. Small allowlisted snapshot additions retain server challenge terminal events and optional duration data.

Display settings persist Text size (100%, 115%, 130%), High contrast, and reduced motion. Every QML font uses the shared scale with a 14px minimum before window scaling. The default help size is 16px. Theme text/background pairs, arbitrary game accents, and the home overlay over a white background have WCAG AA contrast checks. State text, icons, outlines, and words accompany colour. Focus outlines are 3px normally and 5px in High contrast.

Ranked has a dedicated standing/rating page, progress and placement information when available, explicitly ranked recent results, and a primary Search ranked action. Its competition header uses server season text when supplied. Leaderboard includes a highlighted self row, top-three cards, rank/name/rating/W-L/fighter columns, local record/fighter controls, and a received-at update time when available. Local filters explicitly describe their loaded-page scope. Missing data is shown as unknown; unsupported T4 ranked is hidden from its home and has an explicit unavailable surface in the review fixture.

Qt could deadlock while compiling the earlier external inline Table with nested repeaters. The table and its basic label/button/receipt dependencies are now separate QML files with an acyclic dependency graph. A bounded subprocess regression checks that rendering completes. Navigation remains plain Python with no Qt imports; screens continue to use the adapter interface.

Screenshot evidence is synthetic and contains no game art. No launcher backend, installed game, or real adapter is instantiated by the capture tools. All image fields are stripped.

- Preserved baseline: `build/shots/online/before/` (280 captures).
- Final review matrix: `build/shots/online/after-windows/{language}/{t5,t4}/{1920x1080,1280x720}/{scene}.png` (392 captures).
- Scenes: `home`, `ranked`, `leaderboard`, `rooms`, `settings`, `lobby`, `friends`, `stats`, `profile`, `tournaments`, `spectating`, `account`, `rooms_empty`, `feedback`.
- Catalogs: `en`, `de`, `es`, `fr`, `pt-BR`, `ja`, `ko`.
- Additional size/contrast matrices: `build/shots/online/after-large/`, `after-larger-high-contrast/`, and `after-larger-high-contrast-windows/`.
- Each matrix includes contact sheets and `report.json` with geometry, QML warnings, and font coverage.

The Online contact sheets were visually inspected for both games and both resolutions in every catalog. Home, Ranked, Settings, and feedback sheets were also inspected. Japanese/Korean native Qt captures and enlarged high-contrast captures were inspected with real glyphs. Offscreen Qt does not expose those installed fonts in this environment, so native fixture captures supply the CJK visual evidence. No font files were copied into the repository and no dependency was added.

Validation uses the supplied PySide6 interpreter, `OPENRECOMP_HOME`, `APPDATA`, `LOCALAPPDATA`, `TMP`, and `TEMP` under `build/tmp-home`, and `QT_QPA_PLATFORM=offscreen`:

```text
python -m unittest discover -s tests -p "test_*.py"
```

Ran 1941 tests in 231.475s. OK (skipped=10); no failures or errors. The exact full-discovery command above passed with the supplied PySide6 interpreter and isolated environment. The final native matrix contains 392 captures with zero overflow, zero QML warnings, and Japanese/Korean font coverage confirmed. The additional size/contrast matrices also report zero overflow and warnings. `git diff --check` passed. The sanitized test summary is `build/unittest-final.txt`; the raw full-run log is `build/unittest-verification.txt`.

Not checked: real game/background assets, live servers or matchmaking, builds/installers, physical controller hardware, or an external screen reader. Tests use fakes. Optional external lobby, installer, portable-runtime, and unavailable symlink checks retain their existing skips. No game, game build, online search, Ranked search, or Quick Match search was started.

Proposed commit message: `Polish game menus, online feedback, accessibility and rankings`.

The file inventory below describes the complete pending UI topic, including the preserved earlier rounds.

```text
openrecomp/adapters/base.py
openrecomp/adapters/t5_challenges.py
openrecomp/adapters/t5_online.py
openrecomp/adapters/t5_profiles.py
openrecomp/app.py
openrecomp/i18n/de.json
openrecomp/i18n/en.json
openrecomp/i18n/es.json
openrecomp/i18n/fr.json
openrecomp/i18n/ja.json
openrecomp/i18n/ko.json
openrecomp/i18n/pt-BR.json
openrecomp/nav.py
openrecomp/nav_hub.py
openrecomp/nav_online.py
openrecomp/nav_online_layout.py
openrecomp/nav_profiles.py
openrecomp/nav_sections.py
openrecomp/nav_settings_page.py
openrecomp/nav_shelf.py
openrecomp/ui/BuildAction.qml
openrecomp/ui/BuildPage.qml
openrecomp/ui/Glyph.qml
openrecomp/ui/Hub.qml
openrecomp/ui/Main.qml
openrecomp/ui/OnlineCard.qml
openrecomp/ui/OnlineHub.qml
openrecomp/ui/OnlineLogin.qml
openrecomp/ui/Overlays.qml
openrecomp/ui/PageLoader.qml
openrecomp/ui/PeerPing.qml
openrecomp/ui/ResultCell.qml
openrecomp/ui/SettingsHub.qml
openrecomp/ui/Shelf.qml
tests/test_challenge_ping.py
tests/test_generic_nav.py
tests/test_generic_ui_safety.py
tests/test_i18n.py
tests/test_launcher_perf.py
tests/test_nav_layout.py
tests/test_offline_feedback.py
tests/test_t4_beta_settings.py
tests/test_t4_bundle_app.py
tests/test_t4_first_run_nav.py
tests/test_t5_coexist_nav.py
tests/test_t5_netext_ui.py
tests/test_ui_loads.py
tests/test_ui_sound.py
tools/package_release.py
docs/UI_POLISH_REVIEW.md
openrecomp/nav_feedback.py
openrecomp/nav_main_menu.py
openrecomp/nav_ranked.py
openrecomp/ui/ActionReceipt.qml
openrecomp/ui/Interaction.qml
openrecomp/ui/LeaderboardPage.qml
openrecomp/ui/MainMenu.qml
openrecomp/ui/OnlineBody.qml
openrecomp/ui/OnlineButton.qml
openrecomp/ui/OnlineHelp.qml
openrecomp/ui/OnlineLabel.qml
openrecomp/ui/OnlineSections.qml
openrecomp/ui/OnlineStyle.qml
openrecomp/ui/OnlineTable.qml
openrecomp/ui/RankedPage.qml
openrecomp/ui/SessionPage.qml
openrecomp/ui/Theme.qml
openrecomp/ui/qmldir
tests/test_accessibility.py
tests/test_action_feedback.py
tests/test_main_menu.py
tests/test_online_hierarchy.py
tests/test_online_hierarchy_catalogs.py
tests/test_online_shots.py
tests/test_ranked_presentation.py
tests/test_session_presentation.py
tests/test_ui_secondary_polish.py
tests/test_ui_shelf_settings_polish.py
tests/test_ui_shots.py
tools/online_shots.py
tools/ui_shots.py
```
