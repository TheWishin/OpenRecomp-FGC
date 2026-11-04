# Tekken 4 fighter portraits

The launcher reads character-select portraits from the player's own USA
SLUS-20328 v1.00 data. No portrait, extracted file, ISO or game executable is
distributed with this repository.

`openrecomp/t4_art.py` reads `TEKKEN/DATA.BIN` using the file table in
`SLUS_203.28` at virtual address `0x313380`. Each 16-byte row gives the sector,
packed size, checksum, row index and decoding key. The decoder verifies the
USA ELF SHA-1, row index, size and DATA.BIN bounds, decodes the first 4 KB when
required, and checks the decoded word sum before unpacking the TIM2 image.
The DATA.BIN format follows the extractor introduced in the T4 project's
commit `c522b15`.

## Verified portrait entries

Every portrait below was decoded and visually checked. These are DATA.BIN row
numbers associated with symbolic fighter keys; they are not game character ID
numbers. The portraits are 248 by 307 pixels with a 256-colour palette.

| Fighter key | DATA.BIN row |
| --- | ---: |
| `paul` | 244 |
| `law` | 245 |
| `lei` | 246 |
| `king` | 247 |
| `yoshimitsu` | 248 |
| `nina` | 249 |
| `hwoarang` | 250 |
| `xiaoyu` | 251 |
| `christie` | 252 |
| `jin` | 253 |
| `julia` | 254 |
| `kuma` | 255 |
| `bryan` | 256 |
| `heihachi` | 257 |
| `kazuya` | 258 |
| `lee` | 259 |
| `steve` | 260 |
| `marduk` | 261 |
| `combot` | 262 |
| `panda` | 263 |
| `violet` | 264 |
| `eddy` | 265 |
| `miharu` | 266 |

Rows 267–270 contain alternate Paul, Kazuya, Combot and Bryan renders;
row 271 is a blank UI panel. They are not additional roster entries.

## Local cache and UI

After a finished build, the first request for a known fighter starts background
decoding. The adapter prefers the extracted `game/disc` directory and otherwise
uses the configured ISO. Source files stay read-only. A changed source stamp
permits another attempt after a decoding failure; missing art leaves the normal
portrait fallback.

The decoder takes the top 248 by 248 pixel head crop and writes a PNG under
`OPENRECOMP_HOME/art/t4/fighters/<fighter-key>.png`. The crop retains its alpha;
the softened Jin tile image is a separate asset. The existing `FighterPortrait`
component displays these cached images in the lobby, VS card and profile.
The existing most-played fighter selection rule still chooses identity portraits.

## Validation and local review captures

Tests use synthetic ISO, ELF, DATA.BIN and TIM2 data. Run the required suite:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests
```

With the existing PySide6 dependency installed and at least two known square
portrait PNGs cached, the offline review tool renders lobby, VS and profile
fixtures at 1920×1080 and 1280×720:

```powershell
.venv\Scripts\python.exe tools/t4_art_shots.py --cache <OPENRECOMP_HOME>/art/t4/fighters
```

The tool uses synthetic players and an offscreen UI. It does not discover an
installed game, start a game or build, or contact the network. Captures and the
geometry/QML report stay under ignored `build/shots/t4art`; they contain private
game art and must never be committed.
