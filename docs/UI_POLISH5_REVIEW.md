# UI polish 5 review

All changes remain in the working tree on `ui-polish`. No commit, branch switch, publication, real launcher capture, game launch, build, live lobby connection, install inspection or online search was performed. Captures use fake adapters and recursively scrub image fields. Before/baseline captures were preserved.

## P1-P15 implementation

| Priority | Result |
| --- | --- |
| P1 | The lobby has permanent 60/40 player/chat panes, inset 24 and gap 16. A compact profile and action strip replaces giant match tiles and the mandatory cabinet rail. |
| P2 | Shared native `EditableField` supports caret, selection, clipboard, AltGr and IME. Stable IDs/types/limits/secret/draft/submit metadata crosses Nav/Backend. Mouse and keyboard use native editing. Pad A opens the existing OSK. Native keys cannot trigger global navigation. Library and legacy name forms use a native fallback modal. |
| P3 | Dense player rows keep name, rank, ping, status and own-player distinction. Selection does not change row geometry or scale its text. Six complete default rows are measured at 1080p and 720p. Long names retain complete accessible names. |
| P4 | Single click selects. Double click and pad A use a guarded identity-based challenge action. Pending requests, unavailable peers, self and unsupported actions are blocked. Challenge keeps its primary role when Profile is focused. |
| P5 | Reusable chat shows all messages supplied by the adapter. Native composition stays at the bottom. Exceptionally short panes use a native field and short Send button in one full-width composer row; Latest moves into the header with its full accessible name. Private tabs share that compact header. Private tabs have per-thread unread counts, named close controls and automatic reveal of the focused tab. Drafts and scroll positions are retained per conversation. Plain segmented mentions and Tab completion never interpret user HTML. A pad-reachable latest-messages action releases held history. Message identities survive received-history prefix trimming. |
| P6 | Challenge notices occupy measured space above both panes. Opponent, terms, connection and supplied countdown/legacy elapsed status remain available. Pending reply controls reject duplicate activation. Terminal results remain nearby after transient receipts expire. No disappearance is labelled a decline or expiry. |
| P7 | Presentation exposes actual adapter phases. Searching/cancelling keeps chat and an explicit guarded Cancel. Match/start/play/result screens reuse existing adapter actions and connection data. Match found has one headline and a pinned existing Ready action. Repeated metadata is removed. No ETA, artificial acceptance step or countdown was added. |
| P8 | D-pad follows the player list and chat pane. Pane and drawer return targets use semantic IDs. Left reaches selected actions; Right reaches chat. Y Profile, valid X Watch and Start More remain supported. Hidden controls are excluded from projected routes. |
| P9 | Theme sizes compensate for viewport scaling. At 720p the measured body/secondary floors are 18/16 output pixels. Shared primary targets are at least 44 output pixels. Headings have 28/22 pixel floors. Longer content wraps or scrolls. Menu/modal/picker targets and large replay table headers have measured regressions. Shared list minimums stay consistent; rows expand when accessible text requires more space. |
| P10 | Five settings tabs remain. Selected help replaces repeated hints. Available values are clearly informational; real changes still use bounded existing cyclers and setters. |
| P11 | Rooms retain browse, Join/Create, invite codes and fixed reachable Create. Advanced draft options collapse and B restores the opener. Joined rooms display the actual room name, numbered supplied queue, members and table scores. Existing actions remain reachable in a separate scrollable controls pane. Drafts and existing receipts remain intact. No transport or room-flow change was made. |
| P12 | Existing ranked and leaderboard pages remain capability-gated. Ranked options collapse without hidden targets. Leaderboard headings stay pinned. Short viewports and enlarged text omit duplicate podium/own summary cards and use a horizontally scrollable filter strip, revealing the selected control. Actual ranking rows remain visible on entry. Podium activation has accessible semantics. Filters describe the currently loaded page. |
| P13 | Shared palette roles, spacing, physical text/target floors and list minimums are retained centrally. Challenge primary, selection, focus, error, success and disabled states remain distinct. Error pages use the error role. Contrast checks cover actual text/fill pairs, including native form captions on the selected fill. |
| P14 | Main-menu maintenance/setup routes are grouped under More. Secondary destinations remain supported. Optional compact matches, scores and Watch live in More, with Spectating/Rooms still separate destinations. Page navigation never starts a search. |
| P15 | Native editable, list and heading roles are provided. Disabled controls expose their reason. Qt announcements deduplicate actual state/result changes and ignore countdown ticks. Existing sounds remain unchanged. Dense rows do not animate text scale; existing reduced-motion changes take effect immediately. |

## Sorting

Visible local sort controls cover players, rooms, friends, tournaments, spectating and replays. Players default to you, friends and available peers by ping. Other choices are name, rank, rating, ping and status. Rooms prefer open seats, then ping. Friends prefer online/in-match. Tournaments prefer sign-up, then running, then completed. Spectating uses supplied rank/ping. Replays prefer known newest dates; missing dates retain adapter order. Populated replay filters use saved-replay guidance rather than the empty-library message. Leaderboard keeps actual rank ordering and loaded-page ranked/casual/fighter filters. Missing metadata is never invented.

## Verification

The final full suite passed with the supplied bundle Python: **2,051 tests run; 2,041 passed and 10 skipped**, exit 0, in 252.875 seconds. The command was `python -u -m unittest discover -s tests -v`, with the requested repository-private home and offscreen/software Qt environment. The authoritative local log is `build/uipolish5-tests-verified.txt`.

The 10 skips cover unavailable symlink privileges (3), optional installer builds (2), an explicitly opted-in external-source lobby test (1), and unavailable prepared portable-runtime/cache checks (4). No system permission or installer-build opt-in was enabled.

`git diff --check` passed. The frozen changed Python/QML/catalog/tool/test hashes are recorded locally in `build/shots/uipolish5-source.json`. All 87 frozen source/test/catalog/tool hashes still match after the final captures. Intermediate failing runs and probes are diagnostic evidence only. The retained probe audit checks 592 images across six reports; it is separate from the final matrix.

## Capture matrix and visual review

All six commands check their exit code. The final matrix has **4,572 scene captures** at DPR 1. Each set includes both 1920x1080 and 1280x720.

| Set | Coverage | Captures | Report |
| --- | --- | ---: | --- |
| General, 100% | 24 inert scenes, seven catalogs | 336 | `build/shots/after/report.json` |
| Online, 100% | 45 scenes, seven catalogs, T5DR/T4 | 1,260 | `build/shots/online/after/report.json` |
| Online, 115% | Same Online matrix | 1,260 | `build/shots/online/after-large/report.json` |
| Online, 130%, high contrast | Same Online matrix | 1,260 | `build/shots/online/after-larger-high-contrast/report.json` |
| Native Windows, 130%, high contrast | 45 scenes, Japanese/Korean, T5DR/T4 | 360 | `build/shots/online/after-larger-high-contrast-windows/report.json` |
| Owner review, 100% | 12 scenes, English/German, T5DR/T4 | 96 | `build/shots/final/after-final/report.json` |

All six final capture commands exited 0. The strict audit found **zero QML warnings, geometry overflow, collisions or unexplained essential-label elisions**. All 4,572 PNG dimensions match their declared DPR-1 size. The strict report and PNG-dimension audit is `build/shots/uipolish5-verification.json`. Contact sheets supplement the source images; they are not included in the scene-capture count. Visual review uses all paginated Online sheets across languages, games, resolutions and text settings, plus enlarged state-heavy samples. Actual inspected paths are recorded in `build/tmp-home/uipolish5/inspection-{root,normal,large,accessibility}.json`.

Visual layout coverage includes **766 unique contact-sheet paths**: 224 each at 100%, 115% and 130% high contrast, 64 native CJK, 16 owner sheets and 14 general overviews. Root opened 74 distinct full-resolution source images, including all 48 owner 1080p scenes, their repaired 720p leaderboard/room-create companions, all 14 general replay images and native Japanese/Korean samples. Other reviewers' enlarged readability checks are listed separately in their ledgers. Contact-sheet coverage is not a claim that every source image was enlarged individually.

The only elision exceptions are deliberately long synthetic player names: 14 at 115%, 28 at 130% high contrast and 8 in the native CJK set. Complete Qt accessible names were checked in 84 matching language/game/size/scale contexts (`build/tmp-home/uipolish5/accessible-long-name.json`). No essential action label is accepted as silently elided.

The final comparison covers 5,438 scene/contact/overview PNGs: 4,545 are byte-identical and 893 changed from the pre-repair set. The final caption-only refresh changed 484 PNGs; its separate audit is `build/shots/uipolish5-caption-hash-changes.json`. Byte-identical images retain their visual review. Changed contact pages and the repaired states were opened again. Evidence is in `build/shots/uipolish5-hash-changes.json`. General replay guidance was reopened in all seven catalogs at both resolutions. All 48 requested owner 1080p scene images were opened individually; all four owner 720p leaderboard and four room-create images were also rechecked after repair.

Visual review caught issues that the first report audit missed: records below the initial leaderboard viewport, short-pane chat header overlap, an empty-library hint beside saved replays, and muted captions on a bright selected form row. Each was repaired with a regression before the final test/capture refresh. Deliberately clipped horizontal filter-strip content is distinguished from overflow beyond its full scroll extent. Selecting a pad control reveals it.

Preserved older supplemental reports (`after-arcade`, `after-presentation`, `after-presentation-windows`, `after-windows`) are inventoried separately in `build/shots/uipolish5-superseded-reports.json`. They predate the final source freeze and are superseded diagnostics, with no claim about which prior round produced them. Their old Discord/chat/shortcut elisions and one `topActions` reference warning are absent from the final reports. These old images were preserved and are excluded from the 4,572 current captures.

Japanese/Korean offscreen outputs contain missing-glyph boxes and validate layout only. The separate native Windows synthetic pass uses installed fonts. Kanji, kana and Hangul were checked in actual enlarged native images at both sizes and for both games. No font was imported or installed.

## Fixture commands and scene coverage

The existing explicit CLI now defaults to all 45 Online scenes. `--batch community` selects the new states. `--batch final` selects the owner review set and writes under `build/shots/final/after-final/`. The old arcade batch remains available. All variants render both prescribed sizes. Paginated six-scene contact sheets accompany the overview sheets.

New/default community scenes: `lobby_dense`, `lobby_long_names`, `player_busy`, `player_self`, `private_chat`, `mentions`, `chat_history`, `native_composer`, `pad_composer`, `pad_osk`, `challenge_incoming`, `challenge_sent`, `challenge_waiting`, `challenge_cancelled`, `challenge_declined`, `challenge_expired`, `searching`, `cancelling`, `matched`, `starting`, `playing`, `result`, `reporting`, `disconnect_retry`, `rooms_create`, `community_room`, `controls`.

Owner final scenes: `home`, `mentions`, `private_chat`, `rooms`, `rooms_create`, `community_room`, `matched`, `searching`, `leaderboard`, `profile`, `settings`, `controls`.

The final set includes both games and English/German at both sizes. The requested 1920x1080 files are in `build/shots/final/after-final/{en|de}/{t5|t4}/1920x1080/`.

## Limits

Backdash was neither opened nor measured. This report makes no measured parity claim. No source, strings, fonts, icons or artwork were imported from it.

Networking, authentication, match rules, room transport, hardware controllers, physical IME devices, actual screen-reader speech, audible speaker output and live-service behavior were not exercised. IME composition, clipboard, controller actions, accessibility events and sound hooks were tested synthetically. The capture fixtures force reduced motion; motion/sound behavior has separate tests. The repository .venv lacked PySide6, so verification used the supplied bundle Python. No dependency was installed or changed.

The prescribed image matrix covers 1920x1080 and 1280x720. Additional synthetic lobby/global-chrome geometry checks cover 960x540; this is not an exhaustive 540p page matrix. Rows may scroll at larger text sizes. Arbitrary long player names can elide visually, with the full name retained for accessibility. No server history or pagination was fabricated. Private tabs close locally without deleting server messages.

## Owner 1920x1080 screenshot paths

Files are synthetic, art-free, local and ignored. The 720p companions use the same paths with `1280x720`.

| Screen | EN T5DR | EN T4 | DE T5DR | DE T4 |
| --- | --- | --- | --- | --- |
| Main menu | [PNG](../build/shots/final/after-final/en/t5/1920x1080/home.png) | [PNG](../build/shots/final/after-final/en/t4/1920x1080/home.png) | [PNG](../build/shots/final/after-final/de/t5/1920x1080/home.png) | [PNG](../build/shots/final/after-final/de/t4/1920x1080/home.png) |
| Lobby and mention | [PNG](../build/shots/final/after-final/en/t5/1920x1080/mentions.png) | [PNG](../build/shots/final/after-final/en/t4/1920x1080/mentions.png) | [PNG](../build/shots/final/after-final/de/t5/1920x1080/mentions.png) | [PNG](../build/shots/final/after-final/de/t4/1920x1080/mentions.png) |
| Private conversation | [PNG](../build/shots/final/after-final/en/t5/1920x1080/private_chat.png) | [PNG](../build/shots/final/after-final/en/t4/1920x1080/private_chat.png) | [PNG](../build/shots/final/after-final/de/t5/1920x1080/private_chat.png) | [PNG](../build/shots/final/after-final/de/t4/1920x1080/private_chat.png) |
| Rooms browser | [PNG](../build/shots/final/after-final/en/t5/1920x1080/rooms.png) | [PNG](../build/shots/final/after-final/en/t4/1920x1080/rooms.png) | [PNG](../build/shots/final/after-final/de/t5/1920x1080/rooms.png) | [PNG](../build/shots/final/after-final/de/t4/1920x1080/rooms.png) |
| Create room | [PNG](../build/shots/final/after-final/en/t5/1920x1080/rooms_create.png) | [PNG](../build/shots/final/after-final/en/t4/1920x1080/rooms_create.png) | [PNG](../build/shots/final/after-final/de/t5/1920x1080/rooms_create.png) | [PNG](../build/shots/final/after-final/de/t4/1920x1080/rooms_create.png) |
| Community room and queue | [PNG](../build/shots/final/after-final/en/t5/1920x1080/community_room.png) | [PNG](../build/shots/final/after-final/en/t4/1920x1080/community_room.png) | [PNG](../build/shots/final/after-final/de/t5/1920x1080/community_room.png) | [PNG](../build/shots/final/after-final/de/t4/1920x1080/community_room.png) |
| Match found | [PNG](../build/shots/final/after-final/en/t5/1920x1080/matched.png) | [PNG](../build/shots/final/after-final/en/t4/1920x1080/matched.png) | [PNG](../build/shots/final/after-final/de/t5/1920x1080/matched.png) | [PNG](../build/shots/final/after-final/de/t4/1920x1080/matched.png) |
| Searching banner | [PNG](../build/shots/final/after-final/en/t5/1920x1080/searching.png) | [PNG](../build/shots/final/after-final/en/t4/1920x1080/searching.png) | [PNG](../build/shots/final/after-final/de/t5/1920x1080/searching.png) | [PNG](../build/shots/final/after-final/de/t4/1920x1080/searching.png) |
| Leaderboard | [PNG](../build/shots/final/after-final/en/t5/1920x1080/leaderboard.png) | [PNG](../build/shots/final/after-final/en/t4/1920x1080/leaderboard.png) | [PNG](../build/shots/final/after-final/de/t5/1920x1080/leaderboard.png) | [PNG](../build/shots/final/after-final/de/t4/1920x1080/leaderboard.png) |
| Profile | [PNG](../build/shots/final/after-final/en/t5/1920x1080/profile.png) | [PNG](../build/shots/final/after-final/en/t4/1920x1080/profile.png) | [PNG](../build/shots/final/after-final/de/t5/1920x1080/profile.png) | [PNG](../build/shots/final/after-final/de/t4/1920x1080/profile.png) |
| Settings | [PNG](../build/shots/final/after-final/en/t5/1920x1080/settings.png) | [PNG](../build/shots/final/after-final/en/t4/1920x1080/settings.png) | [PNG](../build/shots/final/after-final/de/t5/1920x1080/settings.png) | [PNG](../build/shots/final/after-final/de/t4/1920x1080/settings.png) |
| Pad bindings | [PNG](../build/shots/final/after-final/en/t5/1920x1080/controls.png) | [PNG](../build/shots/final/after-final/en/t4/1920x1080/controls.png) | [PNG](../build/shots/final/after-final/de/t5/1920x1080/controls.png) | [PNG](../build/shots/final/after-final/de/t4/1920x1080/controls.png) |

## Exact changed files

The 88-path inventory matches the final changed/new working-tree paths. Earlier uncommitted work was preserved and refined where this task required it. This run's generated images and local JSON/log evidence stay ignored.

- `docs/UI_POLISH5_REVIEW.md`
- `openrecomp/app.py`
- `openrecomp/i18n/de.json`
- `openrecomp/i18n/en.json`
- `openrecomp/i18n/es.json`
- `openrecomp/i18n/fr.json`
- `openrecomp/i18n/ja.json`
- `openrecomp/i18n/ko.json`
- `openrecomp/i18n/pt-BR.json`
- `openrecomp/nav.py`
- `openrecomp/nav_arcade.py`
- `openrecomp/nav_feedback.py`
- `openrecomp/nav_hub.py`
- `openrecomp/nav_keyboard.py`
- `openrecomp/nav_library.py`
- `openrecomp/nav_list_sort.py`
- `openrecomp/nav_lobby_chat.py`
- `openrecomp/nav_main_menu.py`
- `openrecomp/nav_online.py`
- `openrecomp/nav_online_layout.py`
- `openrecomp/nav_online_login.py`
- `openrecomp/nav_sections.py`
- `openrecomp/nav_settings_page.py`
- `openrecomp/nav_shelf.py`
- `openrecomp/nav_tools.py`
- `openrecomp/ui/ArcadeAction.qml`
- `openrecomp/ui/ArcadeFloor.qml`
- `openrecomp/ui/ArcadePlayer.qml`
- `openrecomp/ui/BuildPage.qml`
- `openrecomp/ui/EditableField.qml`
- `openrecomp/ui/Hub.qml`
- `openrecomp/ui/Interaction.qml`
- `openrecomp/ui/LeaderboardPage.qml`
- `openrecomp/ui/LobbyChat.qml`
- `openrecomp/ui/Main.qml`
- `openrecomp/ui/MainMenu.qml`
- `openrecomp/ui/OnlineBody.qml`
- `openrecomp/ui/OnlineButton.qml`
- `openrecomp/ui/OnlineCard.qml`
- `openrecomp/ui/OnlineHub.qml`
- `openrecomp/ui/OnlineLogin.qml`
- `openrecomp/ui/OnlineSections.qml`
- `openrecomp/ui/OnlineStyle.qml`
- `openrecomp/ui/OnlineTable.qml`
- `openrecomp/ui/Overlays.qml`
- `openrecomp/ui/RankedPage.qml`
- `openrecomp/ui/SessionPage.qml`
- `openrecomp/ui/SettingsHub.qml`
- `openrecomp/ui/Shelf.qml`
- `openrecomp/ui/Theme.qml`
- `tests/pad_step.py`
- `tests/test_accessibility.py`
- `tests/test_accessible_announcements.py`
- `tests/test_action_feedback.py`
- `tests/test_arcade_catalogs.py`
- `tests/test_arcade_floor.py`
- `tests/test_click_target_floors.py`
- `tests/test_community_lobby.py`
- `tests/test_community_sort.py`
- `tests/test_disabled_accessibility.py`
- `tests/test_global_chrome.py`
- `tests/test_i18n.py`
- `tests/test_main_menu.py`
- `tests/test_native_editing.py`
- `tests/test_nav.py`
- `tests/test_nav_layout.py`
- `tests/test_navigation_polish.py`
- `tests/test_online_bc_safety.py`
- `tests/test_online_hierarchy.py`
- `tests/test_online_page.py`
- `tests/test_online_shots.py`
- `tests/test_osk_clipboard.py`
- `tests/test_private_chat_nav.py`
- `tests/test_ranked_presentation.py`
- `tests/test_replay_typography.py`
- `tests/test_session_presentation.py`
- `tests/test_t4_beta_layout.py`
- `tests/test_t4_online_nav.py`
- `tests/test_t5_netext_ui.py`
- `tests/test_ui_arcade.py`
- `tests/test_ui_loads.py`
- `tests/test_ui_polish.py`
- `tests/test_ui_secondary_polish.py`
- `tests/test_ui_shelf_settings_polish.py`
- `tests/test_ui_shots.py`
- `tools/online_shots.py`
- `tools/package_release.py`
- `tools/ui_shots.py`

## Proposed commit message

`Make the community lobby readable and support direct text input`

## Owner continuation: compact Online layout

This section supersedes the layout and verification claims above for the latest owner feedback. Earlier changes and the game shelf layout were retained. Changes remain in the working tree on `ui-polish`; no commit, branch switch, push or PR was made.

The Online top area again groups the profile at the left and matchmaking beside it, following release `343b01c`. The profile shows the fighter/avatar, player, rank, supplied rating and W/L, connection, Profile and Log out. Ranked is the accent action, Casual the strong secondary, both at least 64 stage pixels high at 1080p. Guests retain the full disabled Ranked button with an account reason. Searching replaces the corresponding action with its elapsed time and guarded Cancel.

Players now use fixed single-line 34 px rows at 1080p with 24 px portraits, name, rank/plate, rating, main, status and ping bars. Clicking headers sorts locally; clicking the same header reverses the order while retaining the own-player row first. The selected row has inline Challenge, Profile and Message actions; compact viewports use named icons. Double-click and controller A share the guarded challenge path. Dense fixtures verify at least 18 complete rows at 1080p and 10 at 720p for both games and English/German. Larger text can scroll. Body text has a 14 output-pixel floor and respects Text size; titles remain larger.

Live matches and rooms are visible next to the table. Create room and Join with code are at the rooms header and the Rooms page top. Create opens a cancellable draft with name, capacity, turns, access, hidden and the server-supported FT1-10 choices, plus one Create action. B/Esc restores the opener without creating a room. Unsupported adapter data is not fabricated.

One shell-owned chat dock stays visible across all nine Online chapters, match cards, and the logged-in game menu. It opens by default, occupies about 30% of the width below the top bar, and collapses to a narrow unread/mention rail. Tabs, drafts and held scroll positions survive page changes. Controller navigation enters and leaves both the menu dock and match-card dock.

Native Return, keypad Enter and the on-screen keyboard's Done/Enter path close single-line editing and confirm the value; chat submits through the existing send action. The OSK no longer types the currently selected character on physical Enter, and pasted control characters cannot add newlines. Keyboard, native editing, IME-preserving behavior and OSK submission have regressions.

### Verification for this continuation

The full offscreen suite passed: **2,084 tests run, 2,074 passed and 10 skipped**, exit 0, in 366.649 seconds. The log is `build/owner-complete-suite.txt`. The final B/Cancel caption correction also passed **77 relevant navigation, room, menu and chat tests** (`build/owner-cancel-final.txt`). No test failed. The final screenshot/source evidence is local under `build/shots/final/`.

The required repository `.venv` command was attempted; that environment lacks PySide6. Verification used the owner-supplied bundle Python instead, with offscreen/software Qt and private homes under `build/tmp-home`. No dependency was installed. `git diff --check` passed.

The final image audit covers 224 scene captures: 160 normal Online captures, 48 at 130% text/high contrast, and 16 general shelf/input/settings/control captures. Every report has zero QML warnings, text overflow, essential-label elision, pane overlaps and image-dimension errors. Declared horizontal tab strips are checked against their full scroll extent, and controller focus reveals their selected tab. The audit is `build/shots/final/owner-density-audit.json`.

All eight normal 20-scene overview sheets were visually inspected, followed by enlarged room-create, guest, dense-list, selected-player, searching, main-menu, profile and friends samples. The 720p/130% checks caught and repaired cramped profile metadata, rating headings and room action wrapping. Inspection notes are local at `build/owner-final-layout-review.json`.

Release/current comparisons use the same 31-player fake adapter data and art-free launcher QML from `343b01c`. Both resolutions and English/German were captured side by side. The profile/find grouping is preserved; matchmaking, table density, room discovery and full-height chat are clearer. The owner-specified comparison notes informed structure only; no external code, art, fonts, palette or text was copied, and no measured parity claim is made.

### Screenshot locations

- Normal owner matrix: `build/shots/final/after-final/{en|de}/{t5|t4}/{1920x1080|1280x720}/`.
- Enlarged/high-contrast checks: `build/shots/final/after-larger-high-contrast-final/`, with the same language/game/size structure.
- Input, unchanged shelf, settings and controls: `build/shots/final/input-and-shelf/{en|de}/{1920x1080|1280x720}/`.
- Release comparison: `build/shots/final/comparison/{en|de}/{1920x1080|1280x720}/side-by-side.png`.

The normal matrix contains all 12 round-5 final scenes plus `lobby_dense`, `lobby_guest`, `arcade_selected`, `friends`, `stats`, `tournaments`, `spectating` and `account`. In particular, `rooms_create.png` shows the creation card. Reports and contact sheets accompany the images. All captures are synthetic, art-free, local and ignored by git.

Reproduce the owner matrix with:

```text
python tools/online_shots.py after --batch final --languages en de --scenes home mentions private_chat rooms rooms_create community_room matched searching leaderboard profile settings controls lobby_dense lobby_guest arcade_selected friends stats tournaments spectating account
```

### Files changed during this continuation

These paths include refinements to earlier uncommitted work; the earlier inventory above remains historical. No shelf implementation file was changed during this continuation.

- `docs/UI_POLISH5_REVIEW.md`
- `openrecomp/app.py`
- `openrecomp/adapters/t5_community.py`
- `openrecomp/i18n/{en,de,es,fr,ja,ko,pt-BR}.json`
- `openrecomp/nav_arcade.py`
- `openrecomp/nav_community.py`
- `openrecomp/nav_hub.py`
- `openrecomp/nav_keyboard.py`
- `openrecomp/nav_lobby_chat.py`
- `openrecomp/nav_main_menu.py`
- `openrecomp/nav_online.py`
- `openrecomp/nav_online_layout.py`
- `openrecomp/ui/ArcadeAction.qml`
- `openrecomp/ui/ArcadeFloor.qml`
- `openrecomp/ui/ArcadeIcon.qml`
- `openrecomp/ui/ArcadePlayer.qml`
- `openrecomp/ui/Hub.qml`
- `openrecomp/ui/LobbyChat.qml`
- `openrecomp/ui/Main.qml`
- `openrecomp/ui/MainMenu.qml`
- `openrecomp/ui/OnlineBody.qml`
- `openrecomp/ui/OnlineButton.qml`
- `openrecomp/ui/OnlineCard.qml`
- `openrecomp/ui/OnlineHelp.qml`
- `openrecomp/ui/OnlineHub.qml`
- `openrecomp/ui/OnlineLabel.qml`
- `openrecomp/ui/OnlineStyle.qml`
- `openrecomp/ui/OnlineTable.qml`
- `openrecomp/ui/Theme.qml`
- `tests/pad_step.py`
- `tests/test_accessibility.py`
- `tests/test_arcade_floor.py`
- `tests/test_community_lobby.py`
- `tests/test_i18n.py`
- `tests/test_native_editing.py`
- `tests/test_online_hierarchy.py`
- `tests/test_online_page.py`
- `tests/test_online_shots.py`
- `tests/test_osk_clipboard.py`
- `tests/test_persistent_chat.py`
- `tests/test_ranked_presentation.py`
- `tests/test_room_creation_flow.py`
- `tests/test_social_nav.py`
- `tests/test_t4_beta_layout.py`
- `tests/test_t5_netext_ui.py`
- `tests/test_t5_community.py`
- `tests/test_ui_arcade.py`
- `tools/online_shots.py`

### Limits and proposed commit

No installed game, game build, real authentication, online search, live match, room transport, hardware controller or actual screen-reader speech was exercised. Rendered scenes, pad actions, adapter requests, keyboard/OSK and accessibility behavior used inert fixtures. Existing optional/environment-dependent suite skips remain documented in the test log. Screenshots cannot establish live-service behavior.

Proposed commit message: `Restore compact Online layout, persistent chat and Enter submission`.
