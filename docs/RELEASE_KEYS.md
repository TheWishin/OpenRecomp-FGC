# Release keys

Two Ed25519 keys sign what OpenRecomp-FGC downloads and installs. T5DR Online signs its own releases with
its own key (T5DR's `docs/RELEASING.md`); the launcher only checks that one.

| Key | Signs | Public key in | Key id |
| --- | --- | --- | --- |
| launcher | `SHA256SUMS` of TheWishin/OpenRecomp-FGC releases | `openrecomp/updater.py` `RELEASE_PUBLIC_KEYS` | `240b33a1229ca79b` |
| Tekken 4 | `SHA256SUMS` of TheWishin/Tekken4Recomp releases | `openrecomp/game_releases.py` `SOURCES["t4"].keys` | `6c690283a70408ad` |

The key ids are the first 16 hex digits of SHA-256 of the public key; `SHA256SUMS.sig` names the key id it
was made with.

## The private keys

* Each private key is one line of 64 hex digits (a 32-byte Ed25519 seed) in its own file, outside every
  repository and every release folder (for example `<keys>\openrecomp-release\openrecomp-fgc-release.key` and
  `<keys>\tekken4-release\tekken4-release.key`, where `<keys>` is a git-ignored folder on the release PC).
  `tools/release_sign.py` refuses a key file inside this checkout and never prints a private key.
* **Back them up now**: copy both files to two places that are not this PC (for example an encrypted USB stick
  and a password manager's secure note). Never into a repository, a chat, an issue, an e-mail or a cloud
  folder shared with others.
* Anyone with a private key can publish an update that every launcher installs. If a key may have leaked,
  replace it at once (below) and tell the players.

## Losing a key

* Launcher key lost: the installed launchers cannot be updated automatically any more. Make a new key, put
  its public key in `RELEASE_PUBLIC_KEYS`, and every player installs that release by hand once (Setup.exe or the
  zip; settings are kept). After that, updates work again.
* T4 key lost: make a new key and ship a launcher update with the new public key in `SOURCES["t4"].keys`;
  T4 releases signed with the new key install once players have that launcher.

## Replacing a key in a planned way (no manual step for players)

1. `python tools\release_sign.py keygen --out <keys>\...\new.key` (prints the new public key and key id).
2. Add the new public key next to the old one (`RELEASE_PUBLIC_KEYS` or `SOURCES["t4"].keys`) and release a
   launcher update signed with the OLD key.
3. When most players have it: sign the next releases with the NEW key, then remove the old public key in a
   later launcher release.

## Commands

```
python tools\release_sign.py keygen --out <file>                     # once; refuses to overwrite
python tools\release_sign.py public-key --key-file <file>            # public key + key id
python tools\release_sign.py sign --key-file <launcher key> --channel openrecomp-fgc --version vX.Y.Z --sums SHA256SUMS --out SHA256SUMS.sig
python tools\release_sign.py sign-t4 --key-file <T4 key> --version X.Y.Z --sums SHA256SUMS --out SHA256SUMS.sig
```

`tools/make_release.py` does the signing itself and checks every signature again with the public keys built
into the launcher ([RELEASING.md](RELEASING.md)).
