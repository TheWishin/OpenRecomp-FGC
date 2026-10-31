# T5DR Online in OpenRecomp

The Online section uses the player's installed T5DR lobby client. It connects to
the same lobby and uses the same build as the old T5DR Online launcher. The old
launcher remains available during the transition. No client, server, game code,
game data or game pictures are bundled here. Settings and locally saved replays
continue to belong to the selected install.

For the gradual move from 1.1.9, see [Keep both launchers](T5DR_COEXISTENCE.md).
It describes existing settings, saved login, controls and replay reuse, the
private settings-copy drill, the shared build rule and returning to the old
launcher. Opening OpenRecomp does not authorize a migration or a rebuild.

The controller actions go through the adapter interface. Opening a page or
reading its state never logs in, joins a queue, starts a match or fetches a server
list. A login, refresh, invitation, ready check or Watch action must be selected
explicitly. Auto-spectate is a separate saved opt-in preference. A disconnected
or replaced session cannot finish a stale request against its replacement.

## Screen comparison

This table describes the adapter's intended counterparts to the native
`launcher/` and `lobby/t5lobby/tk_*.py` screens. It is not a fresh verification
against either external source checkout or an installed 1.2.0 runtime. Optional features require both
the selected install's client methods and the lobby server's advertised support.
Older installs keep their supported behavior; hidden controls do not claim
capabilities that their client or server lacks.

| Old screen or control | OpenRecomp status and behavior |
| --- | --- |
| Login and account (`tk_views`, `tk_tab`) | Guest, account, saved login and registration use the installed client. Password change, forgotten-password recovery, new recovery codes and certificate fingerprint entry are controller-selectable. One-time recovery codes stay visible only until acknowledged; fingerprint edits apply to this session. |
| Lobby and challenges (`tk_challenges`) | Player list, challenge accept/decline, chat, refresh and explicit match ready checks use adapter actions. Negotiated challenge delay is separate from the local input-delay setting. |
| Tournaments (`tk_tour`, `tour_client`) | Tournament list and details, sign-up, check-in, withdrawal, organizer actions, called-set acceptance, results and bracket sets are controller-selectable. Creation exposes format, set length, schedule, entry limit, check-in and seeding. The bracket is presented as selectable round/set rows. |
| Spectating (`tk_spectate`) | Friend, room and tournament watching uses the installed spectator client. Stop affects the spectator's owned process. Spectating yields to the player's own match. Auto-spectate remains opt-in and requires the install's runtime support. |
| Profile and history (`tk_views`, `tk_ranked_chars`, `tk_history`) | Own and named profiles expose server statistics and history. Ranked-by-character records use the server's games, wins, losses, draws and win rate; rating and rank remain account-level. Own-profile history offers Watch only when the installed replay matcher finds a recording on this PC. Older servers that omit character records do not get invented totals. |
| Leaderboard (`tk_views`, `tk_challenges`) | Server standings, ranked/casual wins and losses, profile lookup, sorting and pagination use the installed client. |
| Stats (`tk_stats`) | Server-wide counts and fighter statistics support all/ranked/casual views and sorting. A missing stats capability leaves the page unavailable rather than fabricating data. |
| Ranked sets and character selection (`tk_tab`, `tk_charsel`) | Set progress, continuation and leaving a set use the native match driver. The character stays locked while the ranked set requires it; controller actions and direct adapter writes both enforce the lock. |
| Friends (`tk_views`, `tk_tab`) | Requests in both directions, add/remove/cancel, presence, invitations, invitation cooldown and answering invitations use the existing friend client. |
| Blocked players (`tk_tab`) | Per-player blocking, listing and unblocking use the installed client and appear only when the server advertises blocks. |
| Mutes (`tk_tab`, `tk_rooms`) | Each listed player has a pad-selectable mute toggle. The personal mute list supports refresh and unmute, including players who have left the lobby. Controls require negotiated mute support. |
| Private chat (`tk_private_chat`) | Conversations show unread counts and session-only history. Compose and report-reason fields use the on-screen keyboard. Reports send only one to five explicitly selected original server messages; signed receipts remain inside the adapter. Controls require negotiated private-chat support. |
| Chat filter notices | Known server refusals are translated into notices. The 1.2.0 protocol has no separate filter capability, so notices appear after the server supplies them. |
| Private rooms (`tk_rooms`) | Named rooms, passwords and invitation codes use the native room methods. Passwords and session tokens stay out of public snapshots. An invitation code is shown only to its room's member. |
| Community rooms (`tk_rooms`) | Size, rotation, sit-out/return, owner settings and player controls are available where supported. Simultaneous tables expose player pairing, watching and their match/set progress. |
| FT sets and in-game rematch rules (`tk_casual`, `tk_rooms`) | Casual FT preferences and room FT/rematch policies follow the install's supported client fields. Room-specific policy is kept with the room; it is not replaced with a global launcher setting. |
| Health handicap and training (`tk_rules`, `tk_rooms`) | Casual health choices follow both server and built-game support, including the older 100% ceiling. Ready and match details show the agreed health and training rules. Training room creation stays with the native room client. |
| Delay up to 8 (`tk_challenges`) | Challenge delay offers Auto and supported frame counts, capped by the selected opponent's negotiated maximum. The supplied native cores intentionally keep their separate local input-delay preference at Auto/0/1/2. |
| Screen side (`launcher/core`, `tk_casual`) | Assigned-side preferences and the local Always see me on the left setting retain their native scopes. Mirroring applies to supported casual matches; it does not change ranked rules. |
| Replay folder (`launcher/core`, `launcher/replays`) | Settings offers controller folder selection and reset to the native default. Recording, browsing and playback use the selected install's folder policy. No replay contents enter this repository. |
| Auto-spectate and spectator permissions (`tk_spectate`, `launcher/core`) | Auto-spectate, spectator permission and ranked spectator permission are offered only when supported by the selected install. |
| Developer badge and mentions (`tk_tab`) | Developer marks come from authoritative lobby data. Mention insertion is controller-selectable, and incoming mention highlighting uses the server's mention metadata. A name or chat message cannot grant a developer badge. |

## Remaining differences and limits

The native launcher's optional local-server hosting, firewall helper,
Discord Rich Presence and desktop notification/foreground-window utilities have
not been recreated in this online screen work. They depend on desktop or hosting
integration beyond the adapter's controller screens. Use the installed native
launcher for those utilities during the transition. OpenRecomp does not change
system or security settings.

A server history row is not a downloadable replay. Replay playback requires a
matching replay saved on this PC by the player's own install. Another player's
profile does not grant access to their replay files. Missing recordings cannot
be restored from leaderboard or profile statistics.

The row-based bracket exposes tournament information and actions to the pad;
the old launcher's mouse-driven bracket canvas is not reproduced pixel for
pixel. Unsupported optional client or server features remain unavailable,
including on older installations.

## Verification and release checks

Regression tests cover adapter delegation, controller navigation, catalog
structure in all seven languages and session safety with synthetic data.
Mute, private-chat, unread, explicit-report, block and filter-notice loopback
cases are included where the optional local server supports them. The current
chat-controls implementation has not been executed here: the repository's
virtual environment cannot start its configured Python 3.12 interpreter.
The optional local lobby test is designed to use literal loopback addresses,
temporary server state and a stub game handle, with guards against external
network access, published server lists, subprocess launches and changes to its
optional source checkouts. It needs external native sources; unavailable or
disallowed sources must be reported as skips. External native integration is
opt-in; the repository-only test run must leave it disabled. Its presence is not evidence that
protocol integration passed in this repository-only audit. Catalog structure
tests do not establish translation quality or readable layout.

Run the complete repository test command before handover:

```text
.venv\Scripts\python.exe -m unittest discover -s tests
```

No launcher window, game, build, published lobby server or matchmaking search was
started for this implementation. Still required before release: check actual
pad focus and text layout in all seven languages, two-PC interoperability with
the old launcher on the same lobby/build, real match and ranked-set continuation,
spectator startup/yield/stop, room-table concurrency, and replay recording and
playback in the chosen folder. These checks need the maintainer's own installs
and game data; unit and loopback tests cannot establish them.
For a short initial review without login, search or game launch, use the German
[20-minute pad check](HAND_CHECK.md). The checks above remain separate release gates.
