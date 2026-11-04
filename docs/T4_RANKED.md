# T4 ranked assets

The owner's decision: Tekken 4 ranked uses T5DR's rank names in T5DR's order.
Accounts can be shared, while ratings and player records remain separate for each game.
The ladder has 37 ranks, indices 0 through 36, from Beginner to Tekken Lord (Kirin).
`openrecomp/vendor/t4lobby/ranks.py` copies the T4 server's names and rating bands
and is the launcher's single source for rank labels and generated badges. A parity
test compares the table with the server source when supplied through
`T4_SERVER_RANKS`, and with the T5DR source through `T5DR_LOBBY_RANKS`; it reads
the tables without importing or running either server.

## Launcher plates

When a T5DR install is known to the launcher, T4 asks the T5DR adapter for the same
rank plate used by the T5DR pages, in the T5DR build output's `cache/ranks` folder.
The T5DR runtime reads the player's own game data and caches plates on that player's
PC. No game pictures belong in this repository,
release package, or generated fallback assets.

When a plate is unavailable, T4 uses our own drawn SVG badge for that tier from
`openrecomp/ui/assets/ranks`. `tools/make_rank_badges.py` generates these badges for
all 37 ranks of the T5DR ladder, retaining their drawn shapes and tier colours.

## Regeneration and game handoff

Run with the launcher's Python environment from the worktree root:

```powershell
python tools/make_rank_badges.py
python tools/make_rank_badges.py --check
python tools/make_rank_badges.py --header build/out_badges/runtime/tekken4_rank_badges.h
```

The T4 game draws its own badges from `runtime/tekken4_rank_badges.h`; it does not
use the T5DR game pictures. The generated header contains the same names, order,
shapes and colours as the launcher's SVG fallback badges. The coordinator must copy
`build/out_badges/runtime/tekken4_rank_badges.h` into the T4 repository's
`runtime/tekken4_rank_badges.h` before testing the updated game. This launcher task
does not write into the game repository or build or start a game.
