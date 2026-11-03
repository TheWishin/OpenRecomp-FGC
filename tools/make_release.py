"""Make the files of one OpenRecomp-FGC release and of the matching Tekken 4 release, ready to upload.

    python tools\\make_release.py --version v0.1.0 --t4-tag v0.1.0 ^
        --t4-repo <Tekken4Recomp checkout> --t4-ref <T4 commit> ^
        --launcher-key <keys>\\openrecomp-release\\openrecomp-fgc-release.key ^
        --t4-key <keys>\\tekken4-release\\tekken4-release.key

From a clean checkout whose HEAD carries the tag `--version` (`--rehearsal` allows an untagged HEAD and marks
the notes). Nothing is uploaded, pushed or tagged; the output folder (default dist\\release-<version> in
this checkout, ignored by git) gets

    launcher\\  OpenRecomp-<version>.zip, OpenRecomp-FGC-Setup-<X.Y.Z>.exe, SHA256SUMS, SHA256SUMS.sig, NOTES.md
                -> GitHub release <version> of TheWishin/OpenRecomp-FGC (openrecomp/updater.py)
    t4\\        OpenRecomp-Tekken4-<t4-tag>.zip, SHA256SUMS, SHA256SUMS.sig, NOTES.md
                -> GitHub release <t4-tag> of TheWishin/Tekken4Recomp (openrecomp/game_releases.py SOURCES["t4"])
    COMMANDS.txt  the exact gh commands for both releases
    release-facts.json

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


def verify_launcher(folder, version, channel, zip_name, setup_name):
    """What a player's launcher does with this release (updater.stage_update's checks, without the download)."""
    sums = (folder / "SHA256SUMS").read_bytes()
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


def verify_t4(folder, tag, zip_name, work):
    """What a player's launcher does with the T4 release (game_releases.verified_zip + unpack)."""
    src = game_releases.SOURCES["t4"]
    sums = (folder / "SHA256SUMS").read_bytes()
    version = game_releases.plain(tag)
    game_releases.check_signature(src, version, sums, (folder / "SHA256SUMS.sig").read_bytes(), keys=src.keys)
    if game_releases.parse_sums(sums.decode("ascii"), zip_name) != digest(folder / zip_name):
        raise ReleaseFailed("T4 SHA256SUMS does not match its zip")
    offer = dict(version=version, tag=tag)
    root = game_releases.unpack(src, str(folder / zip_name), str(work), offer)
    from openrecomp.adapters.t4_install import source_root
    if not source_root(root):
        raise ReleaseFailed("the T4 zip's T4 folder is not a T4 source tree")
    return sum(len(files) for _d, _s, files in os.walk(root))


def notes(kind, **facts):
    if kind == "launcher":
        return (f"OpenRecomp-FGC {facts['version']}\n\n"
                "Launcher for Tekken 4 and Tekken 5 Dark Resurrection Online. No game data is included.\n\n"
                f"- Install: `OpenRecomp-FGC-Setup-{facts['plain']}.exe` (per user, no administrator), or unpack "
                f"`OpenRecomp-{facts['version']}.zip` and run `OpenRecomp-FGC\\run.cmd`.\n"
                "- The launcher updates itself from this repository's signed releases and installs/updates the games "
                "from their own releases.\n\n---\n\n"
                f"| | |\n|---|---|\n| Launcher commit | `{facts['commit'][:12]}` |\n"
                f"| Release key | `{facts['key_id']}` (Ed25519, `SHA256SUMS.sig`) |\n"
                + "".join(f"| `{name}` | `{value}` |\n" for name, value in facts["sums"].items())
                + ("\nREHEARSAL BUILD: not from a tagged commit. Do not publish.\n" if facts["rehearsal"] else ""))
    return (f"Tekken 4 recompiled (USA SLUS-20328), {facts['tag']}\n\n"
            "Beta. Installed and updated by OpenRecomp-FGC (Tekken 4 > Install). No game data: the game is built on your "
            "PC from your own disc image.\n\n"
            "The zip also works alone: unpack it, run `OpenRecomp-FGC\\run.cmd`; the launcher uses the `T4` folder "
            "beside it.\n\n---\n\n"
            f"| | |\n|---|---|\n| T4 source | `{facts['t4_commit'][:12]}` |\n| Launcher commit | `{facts['commit'][:12]}` |\n"
            f"| Release key | `{facts['key_id']}` (Ed25519, `SHA256SUMS.sig`) |\n"
            + "".join(f"| `{name}` | `{value}` |\n" for name, value in facts["sums"].items())
            + ("\nREHEARSAL BUILD: not from a tagged commit. Do not publish.\n" if facts["rehearsal"] else ""))


def commands(out, version, t4_tag, launcher_files, t4_files, commit, t4_commit, t4_prerelease):
    lines = [
        f"# 1. Launcher release (TheWishin/OpenRecomp-FGC). The tag {version} must point at the built commit {commit[:12]}",
        f"#    (git rev-parse {version}^{{commit}}); push the branch that holds it, then the tag.",
        "git -C <OpenRecomp-FGC checkout> push origin main",
        f"git -C <OpenRecomp-FGC checkout> push origin {version}",
        f"gh release create {version} --repo TheWishin/OpenRecomp-FGC --verify-tag --draft "
        f"--title \"OpenRecomp-FGC {version}\" --notes-file \"{out / 'launcher' / 'NOTES.md'}\" "
        + " ".join(f"\"{out / 'launcher' / n}\"" for n in launcher_files),
        "#    Owner: VirusTotal check of the Setup.exe, then publish the draft (not as a pre-release: the launcher",
        "#    offers only published plain vX.Y.Z to everyone; vX.Y.Z-<test> tags marked pre-release reach testers).",
        f"gh release edit {version} --repo TheWishin/OpenRecomp-FGC --draft=false",
        "",
        f"# 2. Tekken 4 release (TheWishin/Tekken4Recomp), T4 source {t4_commit[:12]} (inside the zip).",
        "#    The release repository needs at least one commit on main (a README, like T5DR's public release",
        "#    repository); gh then creates the tag on main. Players get the T4 source from the zip, not from the tag.",
        f"gh release create {t4_tag} --repo TheWishin/Tekken4Recomp --target main --draft "
        + ("--prerelease " if t4_prerelease else "")
        + f"--title \"Tekken 4 {t4_tag} (beta)\" --notes-file \"{out / 't4' / 'NOTES.md'}\" "
        + " ".join(f"\"{out / 't4' / n}\"" for n in t4_files),
        f"gh release edit {t4_tag} --repo TheWishin/Tekken4Recomp --draft=false",
        "",
        "# Check (read only): what a launcher sees",
        "gh api repos/TheWishin/OpenRecomp-FGC/releases/latest --jq \".tag_name, [.assets[].name]\"",
        "gh api repos/TheWishin/Tekken4Recomp/releases --jq \".[0].tag_name, .[0].prerelease, [.[0].assets[].name]\"",
    ]
    return "\n".join(lines) + "\n"


def make(args):
    check_environment()
    version, t4_tag = args.version, args.t4_tag
    if not updater.version_key(version) or not game_releases.version_key(t4_tag) or not t4_tag.startswith("v"):
        raise ReleaseFailed("--version and --t4-tag must look like v0.1.0 (or v0.2.0-beta.1)")
    commit, channel = check_tree(version, args.rehearsal)
    t4_commit = git("rev-parse", f"{args.t4_ref}^{{commit}}", cwd=args.t4_repo)
    out = Path(args.out or DEFAULT_OUT / f"release-{version}").absolute()
    if out.exists() and any(out.iterdir()):
        raise ReleaseFailed(f"{out} exists and is not empty (nothing is overwritten)")
    runtime = Path(args.runtime or ROOT / "dist" / "portable-runtime")
    cache = Path(args.runtime_cache or ROOT / "dist" / "portable-cache")
    if not (runtime / "pythonw.exe").is_file():
        raise ReleaseFailed(f"no portable runtime in {runtime}: run tools\\fetch_portable_runtime.ps1 first "
                            "(or pass --runtime/--runtime-cache of a verified one)")
    plain = version[1:]
    launcher_dir, t4_dir = out / "launcher", out / "t4"
    launcher_dir.mkdir(parents=True)
    t4_dir.mkdir()
    work = Path(tempfile.mkdtemp(prefix=".work-", dir=out))
    try:
        print(f"launcher {version} from {commit[:12]}, T4 {t4_tag} from {t4_commit[:12]} ({args.t4_ref})", flush=True)
        tree = export(ROOT, commit, work / "launcher-src")
        t4_src = export(args.t4_repo, t4_commit, work / "t4-src")
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
        facts = make_installer.make(archive, work / "setup", version=plain, log=lambda line: None)
        setup_name = Path(facts["setup"]).name
        shutil.move(facts["setup"], launcher_dir / setup_name)
        print(f"setup: {setup_name}, {facts['setup_bytes']:,} bytes, {facts['files']} files"
              + (f", {len(facts['warnings'])} compiler warnings" if facts["warnings"] else ""), flush=True)
        sums = write_sums(launcher_dir, [zip_name, setup_name])
        sign_launcher(launcher_dir, version, channel, args.launcher_key, sums)
        verify_launcher(launcher_dir, version, channel, zip_name, setup_name)
        print("launcher release: signature, checksums, program folder and Setup payload verified", flush=True)

        # 2. the T4 zip (the same launcher + T4/)
        t4_zip = f"OpenRecomp-Tekken4-{t4_tag}.zip"
        archive, count = bundle.create_bundle(tree, t4_src, archive=t4_dir / t4_zip, runtime_root=runtime,
                                              runtime_cache=cache, dist=t4_dir, note=note + [f"T4 release tag: {t4_tag}"],
                                              terms=terms, release=release)
        print(f"T4 zip: {archive.name}, {count} files, {archive.stat().st_size:,} bytes", flush=True)
        t4_sums = write_sums(t4_dir, [t4_zip])
        sign_t4(t4_dir, t4_tag, args.t4_key, t4_sums)
        t4_files = verify_t4(t4_dir, t4_tag, t4_zip, work / "t4-check")
        print(f"T4 release: signature, checksum and T4 source tree ({t4_files} files) verified", flush=True)

        launcher_key = hashlib.sha256(bytes.fromhex(channel.public_keys[0])).hexdigest()[:16]
        t4_key = hashlib.sha256(bytes.fromhex(game_releases.SOURCES["t4"].keys[0])).hexdigest()[:16]
        launcher_sums = {n: digest(launcher_dir / n) for n in (zip_name, setup_name, "SHA256SUMS", "SHA256SUMS.sig")}
        t4_all = {n: digest(t4_dir / n) for n in (t4_zip, "SHA256SUMS", "SHA256SUMS.sig")}
        (launcher_dir / "NOTES.md").write_text(notes("launcher", version=version, plain=plain, commit=commit,
                                                     key_id=launcher_key, sums=launcher_sums, rehearsal=args.rehearsal),
                                               encoding="utf-8")
        (t4_dir / "NOTES.md").write_text(notes("t4", tag=t4_tag, commit=commit, t4_commit=t4_commit, key_id=t4_key,
                                               sums=t4_all, rehearsal=args.rehearsal), encoding="utf-8")
        launcher_files = [zip_name, setup_name, "SHA256SUMS", "SHA256SUMS.sig"]
        t4_assets = [t4_zip, "SHA256SUMS", "SHA256SUMS.sig"]
        (out / "COMMANDS.txt").write_text(commands(out, version, t4_tag, launcher_files, t4_assets, commit, t4_commit,
                                                   not args.t4_stable), encoding="utf-8")
        result = dict(version=version, commit=commit, rehearsal=args.rehearsal, t4_tag=t4_tag, t4_ref=args.t4_ref,
                      t4_commit=t4_commit, t4_prerelease=not args.t4_stable,
                      launcher={n: dict(sha256=launcher_sums[n], bytes=(launcher_dir / n).stat().st_size) for n in launcher_files},
                      t4={n: dict(sha256=t4_all[n], bytes=(t4_dir / n).stat().st_size) for n in t4_assets},
                      launcher_key_id=launcher_key, t4_key_id=t4_key)
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
    parser.add_argument("--launcher-key", required=True, help="private launcher key file (outside every repository)")
    parser.add_argument("--t4-key", required=True, help="private T4 key file (outside every repository)")
    parser.add_argument("--out", help=r"default dist\release-<version> in this checkout")
    parser.add_argument("--runtime", help="verified portable runtime (default dist\\portable-runtime)")
    parser.add_argument("--runtime-cache", help="its pinned archive cache (default dist\\portable-cache)")
    parser.add_argument("--forbid", action="append", default=[], help="one more private word no file may contain")
    parser.add_argument("--rehearsal", action="store_true", help="allow an untagged HEAD (notes say: do not publish)")
    args = parser.parse_args(argv)
    try:
        make(args)
    except (ReleaseFailed, ValueError, OSError, updater.UpdateError, game_releases.ReleaseError,
            make_installer.InstallerError, zipfile.BadZipFile) as error:
        print(f"make_release: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
