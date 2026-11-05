# Compact match card and crimson DR theme

The match offer now sits over a dimmed live lobby. Its art card occupies 64% of
the main pane's width and 55% of its height, with the chat pane outside the dimmer.
Two cropped fighter pictures fill the halves; gradient nameplates overlay the
bottom, and VS/countdown overlap the seam. Match details sit on one short line
above a large Ready action and smaller Decline action.

Local Ready keeps the same card and shows Waiting for opponent. Both-ready keeps
the same card and selected fighters while showing Starting.
The first valid start ticket reserves a bounded 350 ms presentation interval at
the launch worker boundary; session and authorization checks still run before
launch. Queue discovery and accepted challenges use the existing ready flow.

T5DR now uses charcoal/crimson surfaces, crimson focus and actions, white primary
labels, orange-to-red selection highlights, gold ranks and steel neutral text.
T4 retains its blue/silver palette. Automated contrast checks cover white-on-red
primary actions and text over both ends of the selected-row gradient.

## Review captures

`tools/match_shots.py` renders synthetic adapter scenes using explicitly supplied
read-only PNG caches. It does not discover installs, instantiate the real backend,
open a network session or launch a game. Captures and contact sheets stay in ignored
`build/shots/withart`, with coverage and geometry in `compact-report.json`.

The review matrix contains 40 captures: English and German, both games, 1920×1080
and 1280×720, for home, lobby, match found, starting and profile. Full native T4
248×307 pictures from the previous review cache are available. The supplied T5DR
cache contains small faces only: native large-crop quality could not be verified.
Separate side-specific render caches are unavailable; supplied fallback art uses
the existing QML P2 mirror. Synthetic tests exercise separate large render inputs
and rank plates independently of the small list faces.

No game, build or live matchmaking session was started. Actual controller hardware,
live server timing and game launch were not checked; automated tests use fake
adapters and mocked launch boundaries. No git metadata was changed.

## Final verification

- Required bundle Python, `QT_QPA_PLATFORM=offscreen`, `QT_QUICK_BACKEND=software`.
- `python -m unittest discover -s tests`: 2,270 tests in 484.790 seconds,
  OK (10 skipped). Log: `build/compact-full-tests-final.log`.
- All 40 final captures visually reviewed through the eight locale/game/size
  contact sheets. Capture report: zero QML warnings and zero text overflow.
- `git diff --check`: passed.
- The working tree contains all changes; no commit, branch change or git metadata
  write was performed.

## Changed files

- `openrecomp/adapters/t4_online.py`
- `openrecomp/adapters/t5_match.py`
- `openrecomp/adapters/t5_online.py`
- `openrecomp/i18n/de.json`
- `openrecomp/i18n/en.json`
- `openrecomp/i18n/es.json`
- `openrecomp/i18n/fr.json`
- `openrecomp/i18n/ja.json`
- `openrecomp/i18n/ko.json`
- `openrecomp/i18n/pt-BR.json`
- `openrecomp/nav.py`
- `openrecomp/nav_feedback.py`
- `openrecomp/nav_online_layout.py`
- `openrecomp/ui/ArcadeAction.qml`
- `openrecomp/ui/ArcadePlayer.qml`
- `openrecomp/ui/FighterPortrait.qml`
- `openrecomp/ui/MainMenu.qml`
- `openrecomp/ui/OnlineButton.qml`
- `openrecomp/ui/OnlineCard.qml`
- `openrecomp/ui/OnlineHub.qml`
- `openrecomp/ui/Theme.qml`
- `tests/test_challenge_ping.py`
- `tests/test_compact_match_card.py`
- `tests/test_crimson_theme.py`
- `tests/test_fighter_fallback.py`
- `tests/test_global_offers.py`
- `tests/test_main_menu.py`
- `tests/test_match_card_flow.py`
- `tests/test_match_shots.py`
- `tests/test_online_shots.py`
- `tests/test_ui_arcade.py`
- `tools/match_shots.py`
- `tools/online_shots.py`
- `docs/UI_COMPACT_MATCH_REVIEW.md`

## Proposed commit message

Compact match-ready cards and give T5DR a crimson theme
