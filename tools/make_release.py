"""Make the files of one OpenRecomp-FGC release and of the matching Tekken 4 release, ready to upload.

    python tools\\make_release.py --version v0.1.0 --t4-tag v0.1.0 ^
        --t4-repo <Tekken4Recomp checkout> --t4-ref <T4 commit> ^
        --matrix-report <scratch>\\player-matrix-report.json ^
        --launcher-key <keys>\\openrecomp-release\\openrecomp-fgc-release.key ^
        --t4-key <keys>\\tekken4-release\\tekken4-release.key

From a clean checkout whose HEAD carries the tag `--version` (`--rehearsal` allows an untagged HEAD and marks
the notes). A complete passing player matrix for exactly this launcher source and portable runtime is required
before any packaging; --skip-matrix is restricted to rehearsal tests with OPENRECOMP_RELEASE_TESTS=1.
Nothing is uploaded, pushed or tagged; the output folder (default dist\\release-<version> in
this checkout, ignored by git) gets

    launcher\\  OpenRecomp-<version>.zip, OpenRecomp-FGC-Setup-<X.Y.Z>.exe, SHA256SUMS, SHA256SUMS.sig, NOTES.md
                -> GitHub release <version> of TheWishin/OpenRecomp-FGC (openrecomp/updater.py)
    t4\\        OpenRecomp-Tekken4-<t4-tag>.zip, SHA256SUMS, SHA256SUMS.sig, NOTES.md
                -> GitHub release <t4-tag> of TheWishin/Tekken4Recomp (openrecomp/game_releases.py SOURCES["t4"])
    COMMANDS.txt  the exact gh commands for both releases
    release-facts.json

--full --t5dr-release <folder> [--t4-release <folder>] adds launcher\\OpenRecomp-FGC-Full-Setup-<X.Y.Z>.exe (also in
the launcher's signed SHA256SUMS): the same Setup with T5DR Online's and T4's signed release files inside, which the
installed launcher installs with its own release checks (openrecomp/bundled_games.py, docs/INSTALLER.md).

The launcher zip is the `OpenRecomp-FGC/` folder (launcher source, its portable Python + Qt from the pinned
runtime, release.json) plus START_HERE/START_HIER; Setup.exe is built from exactly that zip
(tools/make_installer.py). The T4 zip is the both-games bundle (the same launcher + `T4/`, the T4 source made with
`git -c core.autocrlf=false archive <t4-ref>`); the launcher's game installer uses only its `T4/`. Both
SHA256SUMS are signed (Ed25519, docs/RELEASE_KEYS.md) and every file is checked again the way a player's launcher
checks it, with the keys built into this launcher, before the tool says OK. Private keys are read from their
files outside every repository and never printed.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from openrecomp import game_releases, updater  # noqa: E402
import make_installer  # noqa: E402
import release_sign  # noqa: E402
import t4_test_bundle as bundle  # noqa: E402

LAUNCHER_ITEMS = ("openrecomp", "games", "docs", "LICENSE", "README.md", "requirements.txt", "run.cmd", "portable",
                  "release.json")
LOOSE = ("START_HERE.txt", "START_HIER.txt", "BUNDLE.txt")
DEFAULT_OUT = ROOT / "dist"
START_HERE = (
    "OpenRecomp-FGC {version}: launcher for Tekken 4 and Tekken 5 Dark Resurrection Online\n"
    "\n"
    "No game data is included. You use your own copies of the games.\n"
    "Easiest: run OpenRecomp-FGC-Setup-{plain}.exe from the same release instead of this zip.\n"
    "\n"
    "With this zip:\n"
    "1. Unpack everything into a new, empty folder such as C:\\Games\\OpenRecomp (not directly on C:\\ or D:\\).\n"
    "2. Double-click OpenRecomp-FGC\\run.cmd. If Windows warns about a downloaded file, choose \"Run anyway\".\n"
    "3. Pick a game on the shelf. Install or choose folder installs Tekken 5 DR Online or Tekken 4 from their own\n"
    "   releases, then you build the game once from your own package or disc image.\n"
    "\n"
    "The launcher checks for its own updates and for game updates when it starts (signed releases only).\n"
    "German: START_HIER.txt\n")
START_HIER = (
    "OpenRecomp-FGC {version}: Launcher fuer Tekken 4 und Tekken 5 Dark Resurrection Online\n"
    "\n"
    "Keine Spieldaten enthalten. Du nutzt deine eigenen Spiele.\n"
    "Am einfachsten: OpenRecomp-FGC-Setup-{plain}.exe aus demselben Release starten statt dieses Zips.\n"
    "\n"
    "Mit diesem Zip:\n"
    "1. Alles in einen neuen, leeren Ordner entpacken, z. B. C:\\Spiele\\OpenRecomp (nicht direkt auf C:\\ oder D:\\).\n"
    "2. OpenRecomp-FGC\\run.cmd doppelklicken (fragt Windows nach: \"Trotzdem ausfuehren\").\n"
    "3. Im Regal ein Spiel waehlen. \"Installieren oder Ordner waehlen\" holt Tekken 5 DR Online oder Tekken 4 aus\n"
    "   ihren eigenen Releases; danach baust du das Spiel einmal aus deinem eigenen Paket bzw. ISO.\n"
    "\n"
    "Der Launcher sucht beim Start nach eigenen Updates und nach Spiel-Updates (nur signierte Releases).\n"
    "Englisch: START_HERE.txt\n")


class ReleaseFailed(Exception):
    pass


def check_player_matrix(args, commit, runtime):
    """A player report is required before creating any release output."""
    if getattr(args, "skip_matrix", False):
        if not args.rehearsal or os.environ.get("OPENRECOMP_RELEASE_TESTS") != "1":
            raise ReleaseFailed("--skip-matrix is only for tests: needs --rehearsal and OPENRECOMP_RELEASE_TESTS=1")
        return dict(status="skipped-for-tests")
    report = getattr(args, "matrix_report", None)
    if not report:
        raise ReleaseFailed("a passing player matrix is required: run tools/player_matrix.py and pass --matrix-report")
    from tools import player_matrix
    try:
        checked = player_matrix.check_matrix_report(Path(report), commit=commit, source_root=ROOT,
                                                   runtime_root=runtime)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ReleaseFailed(f"player matrix refused this release: {error}") from error
    return dict(status="passed", report_sha256=digest(report), evidence=checked)


def git(*args, cwd=ROOT, binary=False):
    result = subprocess.run(["git", "-c", "core.autocrlf=false", *args], cwd=str(cwd), capture_output=True,
                            check=False)
    if result.returncode != 0:
        raise ReleaseFailed(f"git {' '.join(args)}: {result.stderr.decode('utf-8', 'replace').strip()}")
    return result.stdout if binary else result.stdout.decode("utf-8", "replace").strip()


def export(repo, ref, dest):
    """`git archive` of ref (LF bytes as committed) unpacked into dest."""
    data = git("archive", "--format=tar", ref, cwd=repo, binary=True)
    dest.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for member in tar.getmembers():
            if not (member.isfile() or member.isdir()) or member.name.startswith(("/", "..")) or "/../" in member.name:
                raise ReleaseFailed(f"unexpected entry in the archive of {ref}: {member.name}")
        tar.extractall(dest, filter="data")
    return dest


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_sums(folder, names):
    """SHA256SUMS in the form both checkers read: `<sha256>  <name>`, sorted."""
    text = "".join(f"{digest(folder / name)}  {name}\n" for name in sorted(names))
    (folder / "SHA256SUMS").write_bytes(text.encode("ascii"))
    return text.encode("ascii")


def check_tree(version, rehearsal):
    status = git("status", "--porcelain", "--untracked-files=no")
    if status:
        raise ReleaseFailed("the checkout has uncommitted changes:\n" + status)
    head = git("rev-parse", "HEAD")
    try:
        tagged = git("rev-parse", f"{version}^{{commit}}")
    except ReleaseFailed:
        tagged = ""
    if tagged != head and not rehearsal:
        raise ReleaseFailed(f"HEAD {head[:9]} is not the commit of tag {version} (tag it first, or --rehearsal)")
    init = (ROOT / "openrecomp" / "__init__.py").read_text(encoding="utf-8")
    if f'__version__ = "{version[1:]}"' not in init:
        raise ReleaseFailed(f"openrecomp/__init__.py __version__ is not {version[1:]}")
    channel = updater.configured_channel()     # fails when the updater has no channel/key
    return head, channel


def check_environment():
    for name in (updater.TEST_ENV, updater.TEST_KEY_ENV, "OPENRECOMP_HOME"):
        if os.environ.get(name):
            raise ReleaseFailed(f"{name} is set: release files are checked with the launcher's own keys only")


def sign_launcher(folder, version, channel, key_file, sums):
    seed = release_sign._seed(key_file)
    public = release_sign.public_key(seed).hex()
    if public not in channel.public_keys:
        raise ReleaseFailed("the launcher key file does not belong to a public key in openrecomp/updater.py")
    message = updater.signature_message(channel.name, version, sums)
    signature = release_sign.sign(seed, message)
    envelope = dict(algorithm="ed25519", channel=channel.name, version=version,
                    key_id=hashlib.sha256(bytes.fromhex(public)).hexdigest()[:16], signature=signature.hex())
    raw = (json.dumps(envelope, indent=2) + "\n").encode("ascii")
    (folder / "SHA256SUMS.sig").write_bytes(raw)
    return raw


def sign_t4(folder, tag, key_file, sums):
    seed = release_sign._seed(key_file)
    public = release_sign.public_key(seed).hex()
    if public not in game_releases.SOURCES["t4"].keys:
        raise ReleaseFailed("the T4 key file does not belong to SOURCES['t4'].keys in openrecomp/game_releases.py")
    raw = release_sign.game_signature("t4", game_releases.plain(tag), sums, seed)
    (folder / "SHA256SUMS.sig").write_bytes(raw)
    return raw


def verify_launcher(folder, version, channel, zip_name, setup_name, unsigned=False):
    """What a player's launcher does with this release (updater.stage_update's checks, without the download).
    unsigned: everything but the signature (the owner signs SHA256SUMS afterwards, COMMANDS.txt)."""
    sums = (folder / "SHA256SUMS").read_bytes()
    if not unsigned:
        updater.verify_signature((folder / "SHA256SUMS.sig").read_bytes(), sums, dict(version=version), channel)
    if updater._signed_checksum(sums, dict(version=version)) != digest(folder / zip_name):
        raise ReleaseFailed("SHA256SUMS does not match the launcher zip")
    lines = dict(reversed(line.split("  ", 1)) for line in sums.decode("ascii").splitlines())
    if lines.get(setup_name) != digest(folder / setup_name):
        raise ReleaseFailed("SHA256SUMS does not match Setup.exe")
    with tempfile.TemporaryDirectory(prefix="or-verify-", dir=folder.parent) as work:
        staged = Path(work) / "new"
        staged.mkdir()
        with zipfile.ZipFile(folder / zip_name) as archive:
            for info, parts in updater._archive_members(archive, version):
                target = staged.joinpath(*parts)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(info))
        updater._manifest(staged, dict(version=version), channel)
        top = sorted(p.name for p in staged.iterdir())
        if set(top) != set(LAUNCHER_ITEMS):
            raise ReleaseFailed(f"the program folder has {top}, expected {sorted(LAUNCHER_ITEMS)}")
    header, files = make_installer.parse_payload(_setup_payload(folder / setup_name))
    with zipfile.ZipFile(folder / zip_name) as archive:
        wanted = {n: archive.read(n) for n in archive.namelist() if n.startswith(updater.ARCHIVE_TOP + "/")}
    got = {p: d for p, d in files if p.startswith(updater.ARCHIVE_TOP + "/")}
    if wanted != got:
        raise ReleaseFailed("Setup.exe does not carry exactly the launcher zip's OpenRecomp-FGC folder")
    return header


def _setup_payload(setup):
    """The RCDATA payload inside Setup.exe: the occurrence of its magic whose header and file records parse
    (the program's own code holds the magic as a constant too)."""
    import struct
    data = setup.read_bytes()
    start = data.find(make_installer.MAGIC)
    while start >= 0:
        try:
            (length,) = struct.unpack_from("<I", data, start + 8)
            text = data[start + 12:start + 12 + length].decode("utf-8")
            header = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
            if header.get("name") == updater.ARCHIVE_TOP and length < 4096:
                pos = start + 12 + length
                for _ in range(int(header["files"])):
                    (n,) = struct.unpack_from("<I", data, pos)
                    pos += 4 + n
                    _size, stored, _method = struct.unpack_from("<QQI", data, pos)
                    pos += 20 + 32 + stored
                if pos <= len(data):
                    return data[start:pos]
        except (struct.error, UnicodeDecodeError, ValueError, KeyError):
            pass
        start = data.find(make_installer.MAGIC, start + 1)
    raise ReleaseFailed("Setup.exe has no payload")


def verify_t4(folder, tag, zip_name, work, unsigned=False):
    """What a player's launcher does with the T4 release (game_releases.verified_zip + unpack)."""
    src = game_releases.SOURCES["t4"]
    sums = (folder / "SHA256SUMS").read_bytes()
    version = game_releases.plain(tag)
    if not unsigned:
        game_releases.check_signature(src, version, sums, (folder / "SHA256SUMS.sig").read_bytes(), keys=src.keys)
    if game_releases.parse_sums(sums.decode("ascii"), zip_name) != digest(folder / zip_name):
        raise ReleaseFailed("T4 SHA256SUMS does not match its zip")
    offer = dict(version=version, tag=tag)
    root = game_releases.unpack(src, str(folder / zip_name), str(work), offer)
    from openrecomp.adapters.t4_install import source_root
    if not source_root(root):
        raise ReleaseFailed("the T4 zip's T4 folder is not a T4 source tree")
    return sum(len(files) for _d, _s, files in os.walk(root))


GITHUB_ASSET_LIMIT = 2_000_000_000      # GitHub refuses release assets of 2 GiB and more: stay clearly below


def bundled_version(game, folder):
    from openrecomp import bundled_games
    return bundled_games.offer(game, str(folder))["version"]


def full_setup_name(plain):
    return f"OpenRecomp-FGC-Full-Setup-{plain}.exe"


def verify_t5dr(folder, terms):
    """T5DR's release files the way a player's launcher checks them (built-in key, SHA256SUMS, zip layout, no
    private words). Returns (version, zip name)."""
    src = game_releases.SOURCES["t5dr"]
    from openrecomp import bundled_games
    o = bundled_games.offer("t5dr", str(folder))
    sums = (folder / "SHA256SUMS").read_bytes()
    game_releases.check_signature(src, o["version"], sums, (folder / "SHA256SUMS.sig").read_bytes(), keys=src.keys)
    if not o["zip"]["sha256"] or o["zip"]["sha256"] != digest(folder / o["zip"]["name"]):
        raise ReleaseFailed("T5DR SHA256SUMS does not match its zip")
    # T5DR's zip is built by T5DR's own CI, not on this PC. Its Python's standard library credits people by name
    # (pydoc.py: "Tommy Burnette"), so the bare Windows user name is no evidence there; the profile path, the
    # computer name and the e-mail still are.
    user = os.environ.get("USERNAME", "").casefold()
    terms = [t for t in terms if t.casefold() != user]
    with zipfile.ZipFile(folder / o["zip"]["name"]) as archive:
        bundle.scan_private_terms(((i.filename, archive.read(i)) for i in archive.infolist() if not i.is_dir()), terms)
    return o["version"], o["zip"]["name"]


def make_full_setup(args, work, launcher_zip, launcher_dir, t4_dir, t4_zip, plain, terms):
    """OpenRecomp-FGC-Full-Setup-<X.Y.Z>.exe: the launcher Setup + the T5DR and T4 release files, unchanged.
    Before it is kept, both games are installed from exactly these files with the launcher's own code and keys."""
    t5dr_dir = Path(args.t5dr_release)
    t5dr_version, t5dr_zip = verify_t5dr(t5dr_dir, terms)
    print(f"T5DR release {t5dr_version}: {t5dr_zip}, signature + checksum verified, privacy scan clean", flush=True)
    if args.t4_release:                     # an already published T4 release instead of the one made in this run
        t4_dir = Path(args.t4_release)
        from openrecomp import bundled_games
        o = bundled_games.offer("t4", str(t4_dir))
        t4_zip = o["zip"]["name"]
        files = verify_t4(t4_dir, o["tag"], t4_zip, work / "t4-release-check")
        print(f"T4 release {o['tag']} ({t4_zip}): signature, checksum and T4 tree ({files} files) verified", flush=True)
    games = work / "bundled-games"
    for game, source, names in (("t5dr", t5dr_dir, (t5dr_zip,)), ("t4", t4_dir, (t4_zip,))):
        (games / game).mkdir(parents=True)
        for name in (*names, "SHA256SUMS", "SHA256SUMS.sig"):
            shutil.copy2(source / name, games / game / name)
    from openrecomp import bundled_games
    player = work / "player"
    player.mkdir()
    results = bundled_games.install(str(games), str(player))
    if set(results) != {"t5dr", "t4"} or any(r["state"] != "installed" for r in results.values()):
        raise ReleaseFailed(f"installing the bundled games like a player failed: {results}")
    from openrecomp.adapters.t5dr import install_root
    from openrecomp.adapters.t4_install import source_root
    if not install_root(results["t5dr"]["root"]) or not source_root(results["t4"]["root"]):
        raise ReleaseFailed("the bundled games were installed but the launcher does not find them")
    for game in ("t5dr", "t4"):
        if not game_releases.managed(game, results[game]["root"]):
            raise ReleaseFailed(f"the bundled {game} install has no OpenRecomp-FGC marker")
    shutil.rmtree(player, ignore_errors=True)
    print(f"bundled games installed like a player: T5DR {results['t5dr']['version']}, T4 {results['t4']['version']}",
          flush=True)
    name = full_setup_name(plain)
    facts = make_installer.make(launcher_zip, work / "full", version=plain, log=lambda line: None,
                                games={"t5dr": games / "t5dr", "t4": games / "t4"}, name=name)
    if facts["setup_bytes"] >= GITHUB_ASSET_LIMIT:
        raise ReleaseFailed(f"{name} is {facts['setup_bytes']:,} bytes: over GitHub's asset limit")
    shutil.move(facts["setup"], launcher_dir / name)
    print(f"full setup: {name}, {facts['setup_bytes']:,} bytes, games {facts['games']}", flush=True)
    return name


def verify_full_setup(folder, zip_name, full_name, games):
    """The full Setup carries exactly the launcher zip's program folder, the uninstaller and the games' release files."""
    header, files = make_installer.parse_payload(_setup_payload(folder / full_name))
    with zipfile.ZipFile(folder / zip_name) as archive:
        wanted = {n: archive.read(n) for n in archive.namelist() if n.startswith(updater.ARCHIVE_TOP + "/")}
    got = {p: d for p, d in files if p.startswith(updater.ARCHIVE_TOP + "/")}
    if wanted != got:
        raise ReleaseFailed("the full Setup does not carry exactly the launcher zip's OpenRecomp-FGC folder")
    bundled = {p: d for p, d in files if p.startswith(make_installer.BUNDLE_DIR + "/")}
    expected = {}
    for game, source in zip(("t5dr", "t4"), games):
        for path in source.iterdir():
            if path.name.endswith(".zip") or path.name in ("SHA256SUMS", "SHA256SUMS.sig"):
                expected[f"{make_installer.BUNDLE_DIR}/{game}/{path.name}"] = path.read_bytes()
    if bundled != expected:
        raise ReleaseFailed("the full Setup's game files are not exactly the signed release files")
    other = set(p for p, _ in files) - set(got) - set(bundled) - {make_installer.UNINSTALL_EXE}
    if other:
        raise ReleaseFailed(f"the full Setup carries unexpected files: {sorted(other)[:5]}")
    return header


def notes(kind, **facts):
    # --player-notes / --t4-player-notes: a few plain sentences for players, first (a launcher's update dialog shows the
    # start of a release's text).
    intro = (facts.get("intro") or "").strip()
    intro = intro + "\n\n" if intro else ""
    if kind == "launcher":
        return (f"OpenRecomp-FGC {facts['version']}\n\n" + intro +
                "Launcher for Tekken 4 and Tekken 5 Dark Resurrection Online. No game data is included.\n\n"
                f"- Install: `OpenRecomp-FGC-Setup-{facts['plain']}.exe` (per user, no administrator), or unpack "
                f"`OpenRecomp-{facts['version']}.zip` and run `OpenRecomp-FGC\\run.cmd`.\n"
                + (f"- With the games: `{facts['full']}` installs the launcher together with Tekken 5 DR Online "
                   f"{facts['full_games']['t5dr']} and Tekken 4 {facts['full_games']['t4']} (their own signed release files, "
                   "checked by the launcher before they are unpacked). You still build each game once from your own "
                   "package / disc image.\n" if facts.get("full") else "")
                + "- The launcher updates itself from this repository's signed releases and installs/updates the games "
                "from their own releases.\n\n---\n\n"
                f"| | |\n|---|---|\n| Launcher commit | `{facts['commit'][:12]}` |\n"
                f"| Release key | `{facts['key_id']}` (Ed25519, `SHA256SUMS.sig`) |\n"
                + "".join(f"| `{name}` | `{value}` |\n" for name, value in facts["sums"].items())
                + _candidate_line(facts))
    return (f"Tekken 4 recompiled (USA SLUS-20328), {facts['tag']}\n\n" + intro +
            "Beta. Installed and updated by OpenRecomp-FGC (Tekken 4 > Install). No game data: the game is built on your "
            "PC from your own disc image.\n\n"
            "The zip also works alone: unpack it, run `OpenRecomp-FGC\\run.cmd`; the launcher uses the `T4` folder "
            "beside it.\n\n---\n\n"
            f"| | |\n|---|---|\n| T4 source | `{facts['t4_commit'][:12]}` |\n| Launcher commit | `{facts['commit'][:12]}` |\n"
            f"| Release key | `{facts['key_id']}` (Ed25519, `SHA256SUMS.sig`) |\n"
            + "".join(f"| `{name}` | `{value}` |\n" for name, value in facts["sums"].items())
            + _candidate_line(facts))


def _read_notes(path):
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise ReleaseFailed(f"player notes {path}: {error}") from None


def _candidate_line(facts):
    if facts.get("unsigned"):
        return ("\nUNSIGNED CANDIDATE: sign both SHA256SUMS (COMMANDS.txt, step 0) and tag the launcher commit before "
                "publishing; remove this line from the published notes.\n")
    return "\nREHEARSAL BUILD: not from a tagged commit. Do not publish.\n" if facts["rehearsal"] else ""


def commands(out, version, t4_tag, launcher_files, t4_files, commit, t4_commit, t4_prerelease):
    lines = [
        f"# 1. Launcher release (TheWishin/OpenRecomp-FGC). The tag {version} must point at the built commit {commit[:12]}",
        f"#    (git rev-parse {version}^{{commit}}); push the branch that holds it, then the tag.",
        "git -C <OpenRecomp-FGC checkout> push origin main",
        f"git -C <OpenRecomp-FGC checkout> push origin {version}",
        f"gh release create {version} --repo TheWishin/OpenRecomp-FGC --verify-tag --draft --prerelease "
        f"--title \"OpenRecomp-FGC {version}\" --notes-file \"{out / 'launcher' / 'NOTES.md'}\" "
        + " ".join(f"\"{out / 'launcher' / n}\"" for n in launcher_files),
        "#    Owner's rule: pre-release first. VirusTotal check of the Setup.exe, then publish the draft AS A PRE-RELEASE",
        "#    (installed launchers do not offer a pre-release to everyone; testers download it from the release page).",
        f"gh release edit {version} --repo TheWishin/OpenRecomp-FGC --draft=false --prerelease",
        "#    After the owner's test is OK: the owner marks it the latest release (then every launcher offers it).",
        f"gh release edit {version} --repo TheWishin/OpenRecomp-FGC --prerelease=false --latest",
        "",
        f"# 2. Tekken 4 release (TheWishin/Tekken4Recomp), T4 source {t4_commit[:12]} (inside the zip).",
        "#    The release repository needs at least one commit on main (a README, like T5DR's public release",
        "#    repository); gh then creates the tag on main. Players get the T4 source from the zip, not from the tag.",
        f"gh release create {t4_tag} --repo TheWishin/Tekken4Recomp --target main --draft "
        + ("--prerelease " if t4_prerelease else "")
        + f"--title \"Tekken 4 {t4_tag} (beta)\" --notes-file \"{out / 't4' / 'NOTES.md'}\" "
        + " ".join(f"\"{out / 't4' / n}\"" for n in t4_files),
        "#    Pre-release first (owner's rule): published as a pre-release; Tekken 4 is a beta, so launchers already offer",
        "#    its published pre-releases to everyone -- publish it only together with the launcher's pre-release.",
        f"gh release edit {t4_tag} --repo TheWishin/Tekken4Recomp --draft=false"
        + (" --prerelease" if t4_prerelease else ""),
        "",
        "# Check (read only): what a launcher sees",
        "gh api repos/TheWishin/OpenRecomp-FGC/releases/latest --jq \".tag_name, [.assets[].name]\"",
        "gh api repos/TheWishin/Tekken4Recomp/releases --jq \".[0].tag_name, .[0].prerelease, [.[0].assets[].name]\"",
    ]
    return "\n".join(lines) + "\n"


def sign_commands(out, version, t4_tag, channel):
    """--unsigned: the owner's two signing commands (keys stay on the owner's PC), then the checks."""
    plain = game_releases.plain(t4_tag)
    return "\n".join([
        "# 0. UNSIGNED build: sign both SHA256SUMS with the owner's keys first (never copy a key into a repository).",
        f"python tools\\release_sign.py sign --key-file <keys>\\openrecomp-release\\openrecomp-fgc-release.key "
        f"--channel {channel} --version {version} --sums \"{out / 'launcher' / 'SHA256SUMS'}\" "
        f"--out \"{out / 'launcher' / 'SHA256SUMS.sig'}\"",
        f"python tools\\release_sign.py sign-t4 --key-file <keys>\\tekken4-release\\tekken4-release.key "
        f"--version {plain} --sums \"{out / 't4' / 'SHA256SUMS'}\" --out \"{out / 't4' / 'SHA256SUMS.sig'}\"",
        "#    then upload SHA256SUMS.sig with the other files of each release.",
    ]) + "\n"


def make(args):
    check_environment()
    version, t4_tag = args.version, args.t4_tag
    if not updater.version_key(version) or not game_releases.version_key(t4_tag) or not t4_tag.startswith("v"):
        raise ReleaseFailed("--version and --t4-tag must look like v0.1.0 (or v0.2.0-beta.1)")
    commit, channel = check_tree(version, args.rehearsal)
    t4_commit = git("rev-parse", f"{args.t4_ref}^{{commit}}", cwd=args.t4_repo)
    unsigned = bool(getattr(args, "unsigned", False))
    stage = Path(args.t4_stage).absolute() if getattr(args, "t4_stage", None) else None
    if stage is not None and not bundle.portable_t4(stage):
        raise ReleaseFailed(f"--t4-stage {stage} is not a T4 release stage (toolchain/toolchain.json, release.json)")
    out = Path(args.out or DEFAULT_OUT / f"release-{version}").absolute()
    if out.exists() and any(out.iterdir()):
        raise ReleaseFailed(f"{out} exists and is not empty (nothing is overwritten)")
    runtime = Path(args.runtime or ROOT / "dist" / "portable-runtime")
    cache = Path(args.runtime_cache or ROOT / "dist" / "portable-cache")
    if not (runtime / "pythonw.exe").is_file():
        raise ReleaseFailed(f"no portable runtime in {runtime}: run tools\\fetch_portable_runtime.ps1 first "
                            "(or pass --runtime/--runtime-cache of a verified one)")
    matrix = check_player_matrix(args, commit, runtime)
    plain = version[1:]
    launcher_dir, t4_dir = out / "launcher", out / "t4"
    launcher_dir.mkdir(parents=True)
    t4_dir.mkdir()
    work = Path(tempfile.mkdtemp(prefix=".work-", dir=out))
    try:
        print(f"launcher {version} from {commit[:12]}, T4 {t4_tag} from {t4_commit[:12]} ({args.t4_ref})", flush=True)
        tree = export(ROOT, commit, work / "launcher-src")
        # 0.1.3: the T4 folder is T4's portable release stage (bundled compiler; T4's tools/package_release.py
        # made and scanned it from t4_commit), not a git archive of its sources.
        t4_src = stage if stage is not None else export(args.t4_repo, t4_commit, work / "t4-src")
        release = bundle.release_manifest(version, channel.name)
        start = (START_HERE.format(version=version, plain=plain).encode("utf-8"),
                 START_HIER.format(version=version, plain=plain).encode("utf-8"))
        note = [f"OpenRecomp-FGC {version} ({commit[:12]})", f"T4 source {t4_commit[:12]} (USA SLUS-20328)"]
        terms = bundle.local_terms(ROOT, args.forbid)

        # 1. the launcher zip, then Setup.exe from exactly that zip
        zip_name = f"OpenRecomp-{version}.zip"
        archive, count = bundle.create_bundle(tree, None, archive=launcher_dir / zip_name, runtime_root=runtime,
                                              runtime_cache=cache, dist=launcher_dir, note=note, terms=terms,
                                              release=release, start=start)
        print(f"launcher zip: {archive.name}, {count} files, {archive.stat().st_size:,} bytes", flush=True)
        launcher_zip = archive
        facts = make_installer.make(archive, work / "setup", version=plain, log=lambda line: None)
        setup_name = Path(facts["setup"]).name
        shutil.move(facts["setup"], launcher_dir / setup_name)
        print(f"setup: {setup_name}, {facts['setup_bytes']:,} bytes, {facts['files']} files"
              + (f", {len(facts['warnings'])} compiler warnings" if facts["warnings"] else ""), flush=True)

        # 2. the T4 zip (the same launcher + T4/)
        t4_zip = f"OpenRecomp-Tekken4-{t4_tag}.zip"
        archive, count = bundle.create_bundle(tree, t4_src, archive=t4_dir / t4_zip, runtime_root=runtime,
                                              runtime_cache=cache, dist=t4_dir, note=note + [f"T4 release tag: {t4_tag}"],
                                              terms=terms, release=release)
        print(f"T4 zip: {archive.name}, {count} files, {archive.stat().st_size:,} bytes", flush=True)
        t4_sums = write_sums(t4_dir, [t4_zip])
        if not unsigned:
            sign_t4(t4_dir, t4_tag, args.t4_key, t4_sums)
        t4_files = verify_t4(t4_dir, t4_tag, t4_zip, work / "t4-check", unsigned=unsigned)
        print(f"T4 release: signature, checksum and T4 source tree ({t4_files} files) verified", flush=True)

        # 3. (--full) the full Setup: the launcher Setup + T5DR's and T4's signed release files, installed by the
        # launcher's own checks (openrecomp/bundled_games.py). Then the launcher's SHA256SUMS covers all its files.
        full_name = None
        launcher_names = [zip_name, setup_name]
        if args.full:
            full_name = make_full_setup(args, work, launcher_zip, launcher_dir, t4_dir, t4_zip, plain, terms)
            launcher_names.append(full_name)
        sums = write_sums(launcher_dir, launcher_names)
        if not unsigned:
            sign_launcher(launcher_dir, version, channel, args.launcher_key, sums)
        verify_launcher(launcher_dir, version, channel, zip_name, setup_name, unsigned=unsigned)
        if full_name:
            verify_full_setup(launcher_dir, zip_name, full_name,
                              games=(Path(args.t5dr_release), Path(args.t4_release) if args.t4_release else t4_dir))
        print("launcher release: signature, checksums, program folder and Setup payload verified", flush=True)

        launcher_key = hashlib.sha256(bytes.fromhex(channel.public_keys[0])).hexdigest()[:16]
        t4_key = hashlib.sha256(bytes.fromhex(game_releases.SOURCES["t4"].keys[0])).hexdigest()[:16]
        signature = () if unsigned else ("SHA256SUMS.sig",)
        launcher_sums = {n: digest(launcher_dir / n) for n in (*launcher_names, "SHA256SUMS", *signature)}
        t4_all = {n: digest(t4_dir / n) for n in (t4_zip, "SHA256SUMS", *signature)}
        full_games = (dict(t5dr=bundled_version("t5dr", Path(args.t5dr_release)),
                           t4=bundled_version("t4", Path(args.t4_release) if args.t4_release else t4_dir)) if full_name else None)
        (launcher_dir / "NOTES.md").write_text(notes("launcher", version=version, plain=plain, commit=commit,
                                                     key_id=launcher_key, sums=launcher_sums, rehearsal=args.rehearsal,
                                                     full=full_name, full_games=full_games, unsigned=unsigned,
                                                     intro=_read_notes(getattr(args, "player_notes", None))),
                                               encoding="utf-8")
        (t4_dir / "NOTES.md").write_text(notes("t4", tag=t4_tag, commit=commit, t4_commit=t4_commit, key_id=t4_key,
                                               sums=t4_all, rehearsal=args.rehearsal, unsigned=unsigned,
                                               intro=_read_notes(getattr(args, "t4_player_notes", None))), encoding="utf-8")
        launcher_files = [*launcher_names, "SHA256SUMS", "SHA256SUMS.sig"]
        t4_assets = [t4_zip, "SHA256SUMS", "SHA256SUMS.sig"]
        text = commands(out, version, t4_tag, launcher_files, t4_assets, commit, t4_commit, not args.t4_stable)
        if unsigned:
            text = sign_commands(out, version, t4_tag, channel.name) + "\n" + text
        (out / "COMMANDS.txt").write_text(text, encoding="utf-8")
        if unsigned:            # the facts name what the owner's signature will add
            launcher_files = [n for n in launcher_files if n != "SHA256SUMS.sig"]
            t4_assets = [n for n in t4_assets if n != "SHA256SUMS.sig"]
        result = dict(version=version, commit=commit, rehearsal=args.rehearsal, t4_tag=t4_tag, t4_ref=args.t4_ref,
                      unsigned=unsigned, t4_stage=str(stage) if stage is not None else None,
                      t4_commit=t4_commit, t4_prerelease=not args.t4_stable,
                      launcher={n: dict(sha256=launcher_sums[n], bytes=(launcher_dir / n).stat().st_size) for n in launcher_files},
                      t4={n: dict(sha256=t4_all[n], bytes=(t4_dir / n).stat().st_size) for n in t4_assets},
                      launcher_key_id=launcher_key, t4_key_id=t4_key, full_setup=full_name, full_games=full_games,
                      player_matrix=matrix)
        (out / "release-facts.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"OK: {out}", flush=True)
        return result
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        for leftover in (launcher_dir, t4_dir):
            shutil.rmtree(leftover, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--version", required=True, help="launcher tag, e.g. v0.1.0")
    parser.add_argument("--t4-tag", required=True, help="T4 release tag, e.g. v0.1.0")
    parser.add_argument("--t4-repo", type=Path, required=True, help="the Tekken 4 source checkout (git)")
    parser.add_argument("--t4-ref", required=True, help="T4 source commit or branch (exported with git archive)")
    parser.add_argument("--t4-stable", action="store_true", help="the T4 release is a full release, not a pre-release")
    parser.add_argument("--launcher-key", help="private launcher key file (outside every repository)")
    parser.add_argument("--t4-key", help="private T4 key file (outside every repository)")
    parser.add_argument("--unsigned", action="store_true",
                        help="build and check everything but the signatures; COMMANDS.txt names the owner's signing steps")
    parser.add_argument("--player-notes", type=Path, help="text file: player notes at the top of the launcher's NOTES.md")
    parser.add_argument("--t4-player-notes", type=Path, help="text file: player notes at the top of the T4 NOTES.md")
    parser.add_argument("--t4-stage", type=Path,
                        help="T4's portable release stage (T4 tools/package_release.py --stage): the T4 folder of the zip")
    parser.add_argument("--out", help=r"default dist\release-<version> in this checkout")
    parser.add_argument("--runtime", help="verified portable runtime (default dist\\portable-runtime)")
    parser.add_argument("--runtime-cache", help="its pinned archive cache (default dist\\portable-cache)")
    parser.add_argument("--matrix-report", type=Path, help="passing player_matrix.py JSON report for this source and runtime")
    parser.add_argument("--skip-matrix", action="store_true",
                        help="tests only: requires --rehearsal and OPENRECOMP_RELEASE_TESTS=1; recorded in release facts")
    parser.add_argument("--forbid", action="append", default=[], help="one more private word no file may contain")
    parser.add_argument("--rehearsal", action="store_true", help="allow an untagged HEAD (notes say: do not publish)")
    parser.add_argument("--full", action="store_true",
                        help="also OpenRecomp-FGC-Full-Setup-<X.Y.Z>.exe with T5DR Online and T4 inside (needs --t5dr-release)")
    parser.add_argument("--t5dr-release", type=Path,
                        help="folder with T5DR's published release files: T5DR-Online-<v>.zip, SHA256SUMS, SHA256SUMS.sig")
    parser.add_argument("--t4-release", type=Path,
                        help="with --full: carry exactly this T4 release (zip, SHA256SUMS, .sig) instead of this run's")
    args = parser.parse_args(argv)
    if args.full and not args.t5dr_release:
        parser.error("--full needs --t5dr-release")
    if not args.unsigned and not (args.launcher_key and args.t4_key):
        parser.error("--launcher-key and --t4-key are required (or --unsigned)")
    try:
        make(args)
    except (ReleaseFailed, ValueError, OSError, updater.UpdateError, game_releases.ReleaseError,
            make_installer.InstallerError, zipfile.BadZipFile) as error:
        print(f"make_release: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
