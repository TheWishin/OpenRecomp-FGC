# Round 7 review

Changes are left in the working tree. No branch or index was changed; no commit, release or remote operation was performed. Research was limited to the authorized written inputs and read-only release source. All images below use fake adapters with image fields scrubbed; no installed game, real online search, game art, reference assets or player logs were opened.

| ID | Result and limits |
| --- | --- |
| P01 | Restored the actual lobby's profile-left/find-adjacent composition, including name, fallback/avatar, rank, rating, W/L, server ping and profile/logout. Ranked precedes Quick match, uses the accent, and remains full-size with an account reason for guests. Chat has its own width budget. |
| P02 | Dedicated compact player rows, sortable headings, honest missing values and full accessible data. Selection follows player ID; refresh/sort retains scroll. Selected actions replace trailing metadata without increasing row height. Single select and guarded double-click/pad challenge remain distinct. The fixture contains 40 identities with mixed status/ranks/ping and missing data. |
| P03 | Preserved the single shell-owned chat and existing drafts/history/tab/unread/follow-latest machinery. Scroll memory is now also namespaced by game. Lobby, rooms, friends, leaderboard, profile, statistics, tournaments, spectating, account, Ranked, match phases and logged-in main menu retain the dock. |
| P04 | Community tabs scroll rather than compress localized labels. Ranked identifies its actual route instead of incorrectly marking Lobby active. Existing capability-gated destinations and semantic Back behavior remain. Opening a destination does not search. |
| P05 | Rooms and live games remain beside players. Create is the first room action, beside Join-code. Existing focused creation, supported preference fields, in-place validation, cancel/draft/retry and duplicate-operation guards are retained. Unsupported transport options are not invented. |
| P06 | Preserved native Return/keypad Enter, IME/caret/selection, clipboard/secret and field-specific submit contracts. OSK Done already submitted chat in the starting tree; repeated/stale Done is now explicitly inert. Ordinary form fields commit without inventing network actions. |
| P07 | Bounded outgoing/terminal feedback and a global incoming stack replace the growing lobby notice. Offers show supplied identity/rank/ping/terms/deadline. Arrival does not move focus. Review (Y/F8/mouse) enables A/B or Enter/Esc responses; editing and capture retain input ownership. Accept switches to the offering game's Online page. Stable identities prevent repeated and late responses, including Ready/Decline. |
| P08 | The initiating search action contains status, elapsed time and a separate Cancel; the other main action stays disabled in place. Cancelling/found/starting/playing/result/error retain the operation. A reserved shell activity row remains visible on secondary Online chapters and the main menu; it and the controller Quick-access entry return to the existing operation with Cancel selected, without reissuing it. Chat retains its full height. No ETA, ping expansion, acceptance timeout or queue-practice support is fabricated. |
| P09 | Compact shell and independent table tokens preserve body/type floors, 100/115/130% text and standalone targets. Search text reflows at enlarged German 720p. Shelf Open grows with its text instead of clipping. Existing fonts/resources are retained. |
| P10 | Five Settings tabs/eight groups and IDs remain. Rows emphasize label/value; selected help stays in detail. Existing setters, informational/disabled controls, save failure and disconnected-device explanations remain. |
| P11 | Ranked keeps standing/season/placement/progress/recent form; secondary metrics/options are tighter. Search remains dominant. Unsupported games retain the capability explanation. |
| P12 | Compact leaderboard rows/filters retain sticky headings and own-position access. Podium disclosure is controller-operable and remembered. Filters still describe the loaded page; loading/empty/error/retry and record selection remain. |
| P13 | Community tables use aligned compact data, concise summaries and contextual actions. Repeated generic helper prose is limited to the focused row; disabled reasons remain visible. Missing records remain unavailable/empty rather than receiving fabricated values. |
| P14 | Existing input readers, device glyphs and navigation algorithm remain. New choices, podium, search return and offer review use semantic actions. Capture/editing own input; notification arrival cannot consume an unrelated held Confirm. |
| P15 | Focus/selection/primary/status have borders, underlines, symbols and text as well as colour. Full elided names and disabled reasons remain accessible. Global announcements occur once per identity; countdown ticks stay quiet. Reduced motion and high contrast retain their existing immediate behavior. Catalog/geometry/font checks are expanded. Font limitations below prevent a complete CJK visual pass. |

The owner addenda also receive independently chosen per-game colour roles: warm charcoal/orange for T5DR, cool navy/steel/cyan for T4, with the split shelf retained. The main menu composes a runtime three-fighter banner; profile, character selection and the match-found VS presentation use the adapter picture boundary and geometric/name fallbacks. The VS card includes both identities, supplied rank/rating/region, direct/relay ping, effective delay when supplied, configured online feel, real supplied countdown, opponent-ready state when supplied, and Ready/Decline. The existing T5DR fighter-art loader remains the source of player-owned renders. T4 now accepts bounded per-fighter user-cache paths; its existing verified Jin portrait can be reused. A verified per-fighter T4 disc-entry mapping is still required for automatic extraction of the remaining roster. No cache or install was inspected here. Result/playing cards and profile character/history rows now share the runtime image boundary and geometric fallbacks for supplied fighters. Missing history characters remain empty. No real-art visual pass is claimed.

Global incoming challenge, invite and match-ready offers are exercised over shelf, main menu, settings, build, replays, another game's page and binding/editing states. The full same-game VS page owns Ready/Decline itself, avoiding duplicate popup buttons. While a game runs, the launcher suppresses its popup/sound/attention and leaves the game's own panel responsible. The launcher calls its existing notify sound once and uses `QWindow.alert` for an inactive launcher without activating it. The actual queueplay in-game panel, physical sound and Windows taskbar flashing were not exercised. Incoming negotiated delay is displayed; changing the challenger's terms on receipt is not offered without adapter support.

Measured output geometry (default text):

| Measurement | 1920 × 1080 | 1280 × 720 |
| --- | ---: | ---: |
| Profile/find height | 226 px | 164 px |
| Ranked / Quick match action | 80 px | 80 px |
| Player row | 32 px | 22.83 px |
| Portrait | 24 px | 16 px |
| Player text minimum | 14 px | 14 px |
| Fully visible clipped player rows | **18** | **14** |
| Open chat | 568 × 920 px | 378.67 × 584 px |

Counts come from the actual clipped viewport, including all ancestor clips, with profile/find, navigation, rooms/live and chat visible. Enlarged text scrolls; the 115% pass shows 17/12 complete rows. Standalone profile/options/Create/Join controls retain 44-output-pixel targets. Dense row actions stay within their row and use smaller contained targets.

The release comparison (`build/shots/round7-comparison/comparison-en-1920x1080.png`) renders the original `343b01c` OnlineHub source with the same synthetic identity. The original top grouping is exactly 226 stage pixels. Round 7 keeps that height at 1080p while reserving chat instead of retaining a 1920-wide child. Extracted temporary QML lives only under `build/tmp-home`; before/baseline evidence was preserved. English/German comparison images exist at both sizes.

Reviewed evidence includes all seven catalogs at both sizes: general and Online overview sheets, readable Online contact pages for both games, enlarged-text/high-contrast contact pages, and individual German small-viewport search/cancelling, room creation, leaderboard, profile, Settings, VS and three popup-origin pages. Japanese/Korean tofu is explicitly not a glyph/layout pass. Useful individual captures are dense lobby (`build/shots/final/after-final/en/t5/1920x1080/lobby_dense.png`), creation with chat (`build/shots/final/after-final/de/t5/1280x720/rooms_create.png`), game main menu (`build/shots/final/after-final/en/t5/1920x1080/home.png`), match found (`build/shots/final/after-final/en/t5/1920x1080/matched.png`), ranked selection (`build/shots/final/after-final/en/t5/1920x1080/ranked_select.png`), search while browsing Rooms (`build/shots/final/after-final/en/t5/1920x1080/activity_rooms.png`), search on the main menu (`build/shots/final/after-final/en/t5/1920x1080/activity_home.png`), and incoming over shelf (`build/shots/final/after-final/en/t5/1920x1080/offer_shelf.png`), main menu (`build/shots/final/after-final/en/t5/1920x1080/offer_home.png`), Settings (`build/shots/final/after-final/en/t5/1920x1080/offer_settings.png`).

Capture audit: **4,968 captures, zero QML warnings, zero reported overflow and zero pane collisions**: general, 336 (`build/shots/after/report.json`), Online, 1,456 (`build/shots/online/after/report.json`), 115% text, 1,456 (`build/shots/online/after-large/report.json`), 130% high contrast, 1,456 (`build/shots/online/after-larger-high-contrast/report.json`), final English/German, 264 (`build/shots/final/after-final/report.json`). Full commands were run as requested; affected cases were refreshed with the new merge-report option, preserving complete scene coverage and contact sheets. An additional 72-image art/fallback matrix (`build/shots/round7-art-qa/report.json`) covers focused history, missing-character data and results across both games/sizes and all three text variants, with zero warnings/overflow/collisions. It exposed and verified the empty-cell alignment and hidden-caption fixes.

**Full suite passed: 2,140 tests in 426.299 seconds, 10 skipped, zero failures/errors (exit 0).** The final run used frozen production and test sources; its local transcript is `build/tmp-home/uipolish7-final-validation.txt`. `git diff --check` is clean. Earlier diagnostic captures/runs were superseded after the relevant fixes; before/baseline evidence remains preserved.

From the repository root, the full suite uses the supplied existing bundle interpreter with this setup:

```powershell
$uiPython = '..\fgc-bundle\.venv\Scripts\python.exe'
$uiTestHome = Join-Path (Get-Location).Path 'build\tmp-home\uipolish7-tests'
New-Item -ItemType Directory -Force -Path $uiTestHome | Out-Null
foreach ($uiEnvName in @('OPENRECOMP_HOME','APPDATA','LOCALAPPDATA','TMP','TEMP')) {
    [Environment]::SetEnvironmentVariable($uiEnvName, $uiTestHome, 'Process')
}
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:QT_QPA_PLATFORM = 'offscreen'
$env:QT_QUICK_BACKEND = 'software'
$env:QML_DISABLE_DISK_CACHE = '1'
& $uiPython -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) { throw 'Full suite failed' }
```

All seven JSON catalogs have equal keys/placeholders and independently localized new strings. The font audit now tests every printable catalog character rather than three sample glyphs. Available offscreen fonts miss seven characters in each Latin catalog (native Japanese/Korean language labels and the hourglass), 577 of 666 distinct Japanese catalog characters, and 502 of 595 Korean characters. Report JSON contains exact missing codepoints. No font was installed or substituted. A suitable licensed system fallback and another CJK visual pass are needed.

No real service, game/build, controller/device, native desktop IME, screen reader, installed render cache or in-game queueplay behavior was tested. Qt/native-key/IME simulations, fake late replies, controller semantic actions, accessible announcements, output contrast and clipped geometry were checked by regression tests. `nav.py` and navigation helpers remain Qt-free; no dependency was added.

Proposed commit message only: `Polish online lobby density, persistent chat and global match feedback`.

Changed files (including focused regressions and capture/inventory tooling):

- `docs/`: `UI_POLISH7_REVIEW.md`.
- `openrecomp/adapters/`: `t4.py`, `t5_match.py`, `t5_online.py`.
- `openrecomp/`: `app.py`, `nav.py`, `nav_arcade.py`, `nav_challenges.py`, `nav_drawer.py`, `nav_feedback.py`, `nav_hub.py`, `nav_keyboard.py`, `nav_main_menu.py`, `nav_online.py`, `nav_online_layout.py`, `nav_profiles.py`, `nav_ranked.py`.
- `openrecomp/i18n/`: `de.json`, `en.json`, `es.json`, `fr.json`, `ja.json`, `ko.json`, `pt-BR.json`.
- `openrecomp/ui/`: `ActionReceipt.qml`, `ArcadeFloor.qml`, `ArcadePlayer.qml`, `FighterPortrait.qml`, `GlobalOffer.qml`, `LeaderboardPage.qml`, `LobbyChat.qml`, `Main.qml`, `MainMenu.qml`, `OnlineBody.qml`, `OnlineButton.qml`, `OnlineCard.qml`, `OnlineHub.qml`, `OnlineSections.qml`, `OnlineStyle.qml`, `OnlineTable.qml`, `Overlays.qml`, `PeerPing.qml`, `RankedPage.qml`, `SettingsHub.qml`, `Shelf.qml`, `Theme.qml`.
- `tests/`: `test_accessibility.py`, `test_action_feedback.py`, `test_arcade_floor.py`, `test_challenge_ping.py`, `test_community_lobby.py`, `test_global_offers.py`, `test_i18n.py`, `test_native_editing.py`, `test_nav_layout.py`, `test_online_adapter.py`, `test_online_shots.py`, `test_profile_history_labels.py`, `test_ranked_presentation.py`, `test_round7_shell.py`, `test_social_nav.py`, `test_t5_match_flow.py`, `test_ui_arcade.py`, `test_ui_secondary_polish.py`, `test_ui_shelf_settings_polish.py`, `test_ui_shots.py`, `test_ui_sound.py`.
- `tools/`: `online_shots.py`, `package_release.py`, `release_top_comparison.py`, `ui_shots.py`.
