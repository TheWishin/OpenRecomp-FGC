# UI round 12: living game menus

The changes stay in the working tree on `ui-polish`. Rounds through 11 remain in
place. Six specialist workers covered backgrounds, sound, motion and capture,
performance, translations and accessibility, and the complete test run.

## What changed

- T5DR uses crimson atmosphere and T4 uses blue/silver. The runtime background
  requests the player's main first, then rotates the roster every 18 seconds.
  Large adapter renders take priority over portraits and the adapter's hero.
  Missing builds use original gradient/streak geometry. No game art is included
  in launcher source or the release inventory.
- Art requests use a bounded roster cache and retry incomplete renders at most
  once a second. The QML decode size is bounded. Ambient drift stops when hidden,
  inactive, high contrast is enabled, or motion is reduced. Both the launcher
  preference and Windows' animation preference make the composition static,
  including fighter rotation. The Windows preference is read, never changed.
- Page and match entry transitions take 150–160 ms. Focus and press feedback,
  the local VS flash, deadline-driven countdown arc, result banner and confirmed
  rank-up cue have finite animations. Rank-up requires an increase for the same
  account; the passive banner expires without taking controller focus.
- T4 and T5DR have original synthesized sound themes for navigation, confirmation,
  back, notifications, ready, the final three countdown seconds and win/loss.
  Synthesis and caching happen on the audio worker. Existing volume/mute controls
  apply; losing focus, muting or running a game immediately stops sound tails.
  Provenance and MIT licensing are in `openrecomp/ui/sounds/LICENSE.txt`.
- Home prioritizes the player's main, shows runtime rank artwork when available,
  recent results, play time and social activity. Confirmed profile results are
  used only for the current account. At large text sizes, art takes the remaining
  height so summary data and controller options fit.
- The rank-up caption is translated in all seven catalogs. New modules, QML and
  the sound licence are included in the explicit release source inventory.

## Visual review

Private output is confined to ignored `build/shots/vibe`. The review uses fake
adapters and explicitly supplied read-only art caches from the preceding rounds.
It never starts a game, connects a lobby, or loads installed game code.

There are English and German home, dense-lobby, match-found and result captures
for each game, plus one 12-second home → lobby → match-found GIF per game.
The PNGs use 1280×720; the recordings use 768×432 at 10 fps. Captures and reports
are review artifacts and are excluded from the release source payload.

Original audio previews are available in the same ignored folder as
`t4-sound-preview.wav` and `t5dr-sound-preview.wav` (7.18 seconds each, volume 50%).
They sequence navigation ticks, confirm, back, notification, ready, three countdown
ticks, win and loss. Adjacent JSON cue markers identify each sound. These are
offline synth exports; they do not verify physical playback or perceived balance.

| Game | Home | Lobby | Match found | Recording | Original sound preview |
| --- | --- | --- | --- | --- | --- |
| T5DR | [PNG](../build/shots/vibe/t5-en-home.png) | [PNG](../build/shots/vibe/t5-en-lobby_dense.png) | [PNG](../build/shots/vibe/t5-en-matched.png) | [12 s GIF](../build/shots/vibe/t5-navigation.gif) | [WAV](../build/shots/vibe/t5dr-sound-preview.wav) |
| T4 | [PNG](../build/shots/vibe/t4-en-home.png) | [PNG](../build/shots/vibe/t4-en-lobby_dense.png) | [PNG](../build/shots/vibe/t4-en-matched.png) | [12 s GIF](../build/shots/vibe/t4-navigation.gif) | [WAV](../build/shots/vibe/t4-sound-preview.wav) |

Self-review found and corrected small T5DR main art, beige T4 focus colours,
720p/130% summary overflow, a transform precision regression, and GIF palette
banding. The final home screens make the main fighter prominent and the game
themes distinct. The dense lobby keeps its information readable; background art
is deliberately subdued behind text and opaque data panels. T5DR cached faces
remain visibly softer than native large renders on the VS card.

The final capture report records text overflow, elision, QML warnings, active
window state and changing background drift. A synthetic white-art regression
checks primary and secondary text against WCAG AA contrast (at least 4.5:1).

## Measurements and limits

The software renderer originally exceeded the idle budget with a 10 Hz backdrop.
Software ambient updates are now capped at 2 Hz with the same slow drift speed;
GPU ambient updates remain capped at 10 Hz. Input transitions run independently.

The isolated full-scene visual probe measured 1080p ambient CPU of 0.781% of one
core without art and 2.730% with synthetic art. Inactive and reduced-motion
samples produced no redraws. A full-Backend probe separately measured 1.823%
idle CPU, with 375 input ticks in six seconds. These separate samples must not
be presented as a combined active-art measurement.

A separate combined probe then ran the real Backend and Main.qml together at
1920×1080 with active motion, synthetic art and empty controller readers. Each
eight-second sample recorded 500–501 real input ticks and 16 ambient frames.
T4 measured 1.367% of one core without art and 4.492% with art; T5DR measured
1.757% and 3.711%. Those samples meet the approximate 5% idle target on this
machine. They use fake adapter snapshots and do not establish costs for real
installs, physical controllers, desktop GPU drivers or weak hardware.

The 150 ms slide/fade probe measured draw time of 5.995 ms p95 and 6.938 ms maximum.
Active frame intervals were 16.545 ms median and 32.140 ms p95. Drawing fits the
16.7 ms budget in this sample, but sustained 60 fps is not established by the
software offscreen scheduler. GIF playback/readback timings do not prove 60 fps.

The existing full-Backend navigation probe also recorded 481.782 ms for the first
Online page action-to-render interval and 37.482–104.060 ms for other first page
visits. These include model work, asynchronous QML creation and drawing; they
are separate from steady-state frame drawing. First-visit latency on weak PCs
has not been validated.

The final combined Backend/art measurements are in
`build/shots/vibe/backend-perf.json`; the visual probe is in `perf.json` and the
earlier probe is preserved in `perf-before.json`. Physical controllers, desktop
GPU rendering, weak PCs, real matchmaking, game-front focus changes and physical
audio playback have not been checked. Native large T5DR art was not supplied;
the review uses the existing private face cache. No game or build was started.

## Validation

The required complete offscreen unittest run uses the owner's specified bundle
interpreter. Its final result is recorded in `build/vibe-final-tests.txt`.
The frozen-tree full run completed **2,309 tests in 462.870 seconds**, with
**OK (10 skipped)** and process exit 0. The final log has no QML diagnostics.
Focused regressions cover bounded/main-first art, motion gates, finite entry and
countdown animations, sound synthesis/gating/deduplication, account-safe rank and
result cues, translations, large-text geometry, contrast and GIF decoding.
New regressions were run against the previous behavior to confirm failures.
The explicit source inventory scan passes with 208 files; `git diff --check`
is clean. No release archive was assembled.

## Proposed commit message

`UI round 12: add living game themes, original sound cues and responsive menu motion`

## Changed files

- `docs/UI_VIBE_REVIEW.md`
- `openrecomp/app.py`
- `openrecomp/i18n/de.json`
- `openrecomp/i18n/en.json`
- `openrecomp/i18n/es.json`
- `openrecomp/i18n/fr.json`
- `openrecomp/i18n/ja.json`
- `openrecomp/i18n/ko.json`
- `openrecomp/i18n/pt-BR.json`
- `openrecomp/living_background.py`
- `openrecomp/nav.py`
- `openrecomp/nav_feedback.py`
- `openrecomp/nav_main_menu.py`
- `openrecomp/nav_online.py`
- `openrecomp/nav_rank_cue.py`
- `openrecomp/nav_sound.py`
- `openrecomp/ui/CountdownRing.qml`
- `openrecomp/ui/GlobalOffer.qml`
- `openrecomp/ui/Interaction.qml`
- `openrecomp/ui/LivingBackground.qml`
- `openrecomp/ui/Main.qml`
- `openrecomp/ui/MainMenu.qml`
- `openrecomp/ui/OnlineCard.qml`
- `openrecomp/ui/PageLoader.qml`
- `openrecomp/ui/PromotionBanner.qml`
- `openrecomp/ui/Shelf.qml`
- `openrecomp/ui/Theme.qml`
- `openrecomp/ui/sounds/LICENSE.txt`
- `openrecomp/ui_sound.py`
- `tests/test_living_background.py`
- `tests/test_main_menu.py`
- `tests/test_nav_layout.py`
- `tests/test_rank_cue.py`
- `tests/test_ui_living_background.py`
- `tests/test_ui_vibe_sound.py`
- `tests/test_vibe_accessibility.py`
- `tests/test_vibe_catalogs.py`
- `tests/test_vibe_integration.py`
- `tests/test_vibe_motion.py`
- `tests/test_vibe_perf.py`
- `tests/test_vibe_shots.py`
- `tools/online_shots.py`
- `tools/package_release.py`
- `tools/vibe_perf.py`
- `tools/vibe_shots.py`
