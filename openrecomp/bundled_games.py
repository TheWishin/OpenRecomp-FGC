"""Install the games a full Setup carries (Tekken 5 DR Online, Tekken 4) with the checks a game update makes.

The full Setup (tools/make_installer.py --games) carries each game's GitHub release files untouched:
`<from>/<game>/<zip>`, `SHA256SUMS` and `SHA256SUMS.sig`, exactly as they are published (T5DR's own release on
TheWishin/T5DROnline, T4's on TheWishin/Tekken4Recomp). After Setup has put the launcher in place it runs

    portable\\pythonw.exe -B -m openrecomp.bundled_games --from <staging> --parent <install folder>
        --games t5dr,t4 --lang de --summary <file> [--result <file>] [--status <file>]

and every game goes through game_releases.install_fresh(): the same release signature (the keys built into this
launcher), the same SHA256SUMS line for the zip, the same unpack rules and the same marker as Install from the
launcher. Only the transport differs: a local "opener" serves the files from the staging folder instead of
GitHub. A game that is already beside the launcher is left alone (the launcher offers its updates). Nothing here
downloads anything; game data never passes through it (the zips are our programs only).
"""
import argparse
import glob
import json
import os
import re
import sys

from . import game_releases as gr, i18n

GAMES = ("t5dr", "t4")
NAMES = {"t5dr": "Tekken 5 DR Online", "t4": "Tekken 4"}
SIG = "SHA256SUMS.sig"
SUMS = "SHA256SUMS"
BUNDLE_URL = "bundle:///"


class _Local:
    """A response-like object for game_releases.download over a local file."""

    def __init__(self, path):
        self._f = open(path, "rb")
        self.headers = {"Content-Length": str(os.path.getsize(path))}

    def read(self, n=-1):
        return self._f.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._f.close()


def opener(folder):
    """game_releases' opener for the files of one bundled release; any other address is refused."""
    names = set(os.listdir(folder))

    def open_local(_src, url, _kind="download", _headers=None, _timeout=None):
        name = str(url)[len(BUNDLE_URL):] if str(url).startswith(BUNDLE_URL) else ""
        if not name or name not in names or "/" in name or "\\" in name:
            raise gr.ReleaseError("@setup.err_foreign", f"refused {url}")
        return _Local(os.path.join(folder, name))
    return open_local


def _version_of(game, name):
    """(tag, version) from the zip's release name (the signature covers the version, so a renamed zip fails)."""
    src = gr.SOURCES[game]
    if game == "t5dr":
        m = re.fullmatch(r"T5DR-Online-(\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?)\.zip", name)
        return (f"v{m.group(1)}", m.group(1)) if m else None
    m = re.fullmatch(r"OpenRecomp-Tekken4-(v\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?)\.zip", name)
    if m and src.asset.format(tag=m.group(1), version=gr.plain(m.group(1))) == name:
        return m.group(1), gr.plain(m.group(1))
    return None


def offer(game, folder):
    """The offer dict install_fresh takes, for the release files in folder; ReleaseError when they are not one."""
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        raise gr.ReleaseError("@setup.err_release", f"no {game} release files") from None
    zips = [n for n in names if n.lower().endswith(".zip")]
    if len(zips) != 1 or SUMS not in names or SIG not in names or set(names) - {SUMS, SIG, zips[0]}:
        raise gr.ReleaseError("@setup.err_release", f"{game}: expected one zip, {SUMS} and {SIG}")
    found = _version_of(game, zips[0])
    if not found:
        raise gr.ReleaseError("@setup.err_release", f"{game}: unexpected zip name {zips[0]}")
    tag, version = found
    with open(os.path.join(folder, SUMS), "rb") as f:
        sums = f.read(gr.MAX_SUMS + 1)
    want = gr.parse_sums(sums.decode("utf-8", "replace"), zips[0])
    size = os.path.getsize(os.path.join(folder, zips[0]))
    return dict(game=game, tag=tag, version=version, prerelease=gr.version_key(version)[1] != (1,),
                name=f"{NAMES[game]} {tag}", published="", notes="", code_id=None,
                zip=dict(name=zips[0], url=BUNDLE_URL + zips[0], size=size, sha256=want),
                sums=dict(name=SUMS, url=BUNDLE_URL + SUMS), sig=dict(url=BUNDLE_URL + SIG))


def present(game, parent):
    """The install of game already beside the launcher in parent, else None (that one is never replaced)."""
    if game == "t5dr":
        from .adapters.t5dr import install_root
        for path in sorted(glob.glob(os.path.join(glob.escape(parent), "T5DR-Online-*"))):
            root = install_root(path)
            if root:
                return root
        return None
    path = os.path.join(parent, "T4")
    try:
        return path if os.path.isdir(path) and os.listdir(path) else None
    except OSError:
        return path


def install(source, parent, games=GAMES, progress=None):
    """{game: dict(state=installed|present|failed, version, root, key)} for each wanted game found in source."""
    results = {}
    for game in games:
        folder = os.path.join(source, game)
        if game not in GAMES or not os.path.isdir(folder):
            continue
        try:
            o = offer(game, folder)
            have = present(game, parent)
            if have:
                results[game] = dict(state="present", version=gr.installed_version(game, have) or "", root=have,
                                     key="", bundled=o["version"])
                continue
            report = (lambda step, n, t, g=game: progress(g, step, n, t)) if progress else None
            root = gr.install_fresh(game, o, parent, opener=opener(folder), progress=report)
            results[game] = dict(state="installed", version=o["version"], root=root, key="")
        except gr.ReleaseError as e:
            results[game] = dict(state="failed", version="", root="", key=e.key, detail=str(e))
        except OSError as e:
            results[game] = dict(state="failed", version="", root="", key="@setup.err_write", detail=str(e))
    return results


def summary(results, lang):
    """The result as plain lines in the player's language (Setup shows them as they are)."""
    lines = []
    for game in GAMES:
        r = results.get(game)
        if not r:
            continue
        name = NAMES[game]
        if r["state"] == "installed":
            lines.append(i18n.text(lang, "bundle.installed", name=name, version=r["version"]))
        elif r["state"] == "present":
            lines.append(i18n.text(lang, "bundle.present", name=name, version=r["version"] or "?"))
        else:
            reason = i18n.text(lang, (r["key"] or "@setup.err_unknown").lstrip("@"))
            lines.append(i18n.text(lang, "bundle.failed", name=name, reason=reason))
    if any(r["state"] == "installed" for r in results.values()):
        lines.append(i18n.text(lang, "bundle.next"))
    return "\n".join(lines)


def _write(path, text):
    if not path:
        return
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--from", dest="source", required=True, help="folder with <game>/<release files>")
    p.add_argument("--parent", required=True, help="the install folder (the launcher is in its OpenRecomp-FGC)")
    p.add_argument("--games", default=",".join(GAMES))
    p.add_argument("--lang", default="")
    p.add_argument("--result", default="", help="the result as JSON (UTF-8)")
    p.add_argument("--summary", default="", help="the result as plain lines in the player's language (UTF-8)")
    p.add_argument("--status", default="", help="progress lines '<game> <percent>' for Setup's window")
    a = p.parse_args(argv)
    lang = i18n.normalize({"pt": "pt-BR"}.get(a.lang, a.lang))
    games = [g for g in a.games.split(",") if g in GAMES]
    wanted = [g for g in games if os.path.isdir(os.path.join(a.source, g))]

    def progress(game, step, n, total):
        if step == "unpack" and total:
            share = 100 // max(1, len(wanted))
            done = wanted.index(game) * share + (n * share // total if total else 0)
            try:
                _write(a.status, f"{game} {min(100, done)}\n")
            except OSError:
                pass

    results = install(a.source, os.path.abspath(a.parent), games, progress)
    text = summary(results, lang)
    _write(a.result, json.dumps(dict(results=results, summary=text), indent=1, ensure_ascii=False))
    _write(a.summary, text)
    if not (a.result or a.summary):
        print(text)
    return 0 if all(r["state"] != "failed" for r in results.values()) else 4


if __name__ == "__main__":
    sys.exit(main())
