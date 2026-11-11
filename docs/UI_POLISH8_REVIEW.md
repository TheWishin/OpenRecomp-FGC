# Round 8 review

Ready and Decline now center their label and device glyph inside the button. The unexplained primary-button underline is removed; the existing labelled countdown remains in the VS centre. The shared online button fix also applies to room, ranked and popup actions. Tall main-menu actions and plain result actions now center their content, and feedback retains separate space below button content.

Player pictures use each player's normalized most-played fighter for the current game. Shared adapter normalization selects the highest games count, then wins, then latest play. All-mode usage takes precedence over ranked-only tables. A server's usage-derived Main summary remains usable when detailed counts are omitted; absent usage/summary and explicit zero-match summaries produce an empty image key and silhouette. The local player can fall back to full local match history before a paged own-profile history; another player's history and the current character preference cannot supply the local picture.

Profile, lobby icons, match-found cards, incoming popups, results, friends and leaderboard use that identity. When both explicit match picks are known, the VS card shows those picks and separately labels each known main as `Main: X`. Partial/random picks retain the mains. Results use mains. Explicit P1/P2 fighter pairs are mapped through the supplied local slot. Missing runtime artwork still uses a geometric silhouette.

Tests cover games/wins/recency ordering, all-mode counts, server summary and missing/zero usage, local history ownership and aggregate precedence, pick slots, independent player identities on all affected surfaces, art stripping, and real offscreen button/silhouette geometry. The matched-button test reproduced the former top-aligned label before the fix.

Art-free evidence: capture report (`build/shots/online/after-portraits/report.json`), **72 captures**, zero QML warnings, zero detected overflow and zero pane collisions. The batch covers German and English, T4 and T5DR, 1920x1080 and 1280x720, with matched, matched with known picks, searching, result, dense lobby, profile, friends, leaderboard and incoming challenge scenes. Images use fake adapters and scrub all artwork fields, including popup self artwork. No real launcher or game screenshot is included.

Examples: German matched at 720p (`build/shots/online/after-portraits/de/t5/1280x720/matched.png`), English known picks at 1080p (`build/shots/online/after-portraits/en/t4/1920x1080/matched_picks.png`), German searching (`build/shots/online/after-portraits/de/t4/1280x720/searching.png`), English results (`build/shots/online/after-portraits/en/t5/1920x1080/result.png`). Individual images and contact pages for the full matrix are next to the report.

**Full suite passed: 2,211 tests in 456.657 seconds, 10 skipped, zero failures/errors, exit 0.** The final run used fixed production/test sources. The repository `.venv` cannot import PySide6, so validation used the supplied existing bundle interpreter with `QT_QPA_PLATFORM=offscreen`, `QT_QUICK_BACKEND=software`, and `QML_DISABLE_DISK_CACHE=1`. The command was `python -m unittest discover -s tests`; the final transcript is `build/round8-final-tests.log`. Test home, application data and temporary directories were redirected inside the repository. `git diff --check` is clean.

Not checked: real server payloads or server-side `store.char_usage` implementation, installed game code/data/art caches, physical controllers, live networking, actual games, builds, or runtime artwork appearance. The capture audit still flags incomplete font coverage across entire catalogs; these German/English scenes do not establish a full catalog glyph pass. No external install was inspected, game/build started, online search made, dependency added, or git mutation performed. The launcher can select only from usage summaries/counts exposed by its server; this work does not modify an external lobby server.

Proposed commit message: `Center match controls and use each player's most-played fighter portrait`

Changed files for this round:

- `docs/UI_POLISH8_REVIEW.md`.
- `openrecomp/player_main.py`, `nav.py`, `nav_arcade.py`, `nav_feedback.py`, `nav_online.py`, `nav_online_layout.py`, `nav_profiles.py`, `nav_ranked.py`.
- `openrecomp/adapters/arcade_metadata.py`, `base.py`, `t4_online.py`, `t5_online.py`, `t5_profiles.py`, `t5dr.py`.
- `openrecomp/ui/GlobalOffer.qml`, `LeaderboardPage.qml`, `MainMenu.qml`, `OnlineButton.qml`, `OnlineCard.qml`, `OnlineSections.qml`, `OnlineStyle.qml`, `OnlineTable.qml`.
- `tests/test_button_content.py`, `test_player_main.py`, `test_player_picture_surfaces.py`, `test_player_portrait_sessions.py`, `test_i18n.py`, `test_nav_layout.py`, `test_online_shots.py`, `test_second_audit_social.py`, `test_social_online.py`. Existing contract tests now recognize the Back glyph, portrait metadata and known-picks fixture while preserving their missing-data and localization checks.
- `tools/online_shots.py`, `tools/package_release.py`.

All changes remain in the working tree for maintainer review. Generated captures and validation transcripts remain under ignored `build/`.
