"""Install and update T5DR Online and T4 from their GitHub releases. No Qt; the launcher runs this on a worker.

Only our programs are downloaded, never game data: T5DR Online's release zip (TheWishin/T5DROnline) and T4's
(TheWishin/Tekken4Recomp, whose zip is the launcher bundle with the T4 source in `T4/`). The rules are T5DR's own
updater's (launcher/updater.py): https only, the API of that repository and its release files on github.com or
GitHub's storage for that repository's ID; SHA256SUMS must name the zip and agree with GitHub's digest; T5DR's
release signature (SHA256SUMS.sig, Ed25519) is required when its public key is known; every path in the zip is
checked before anything is written; a staging folder beside the target, then renames.

Channels: "stable" = published plain vX.Y.Z releases only (what T5DR's updater accepts); "prerelease" = also
published pre-releases (testers; T4's first beta and T5DR 1.2.0's test build). Drafts never.

Updating in place keeps the player's files: only the release's own top-level names are exchanged (the old ones
go to a backup until the new ones are in), never T5DR's protected names (native, launcher.json, logs, ...) or
T4's build output (deps, game, generated, out, logs). When the game's code changed, the result says so and the
launcher asks for a new build (T5DR: release.json code_id against the build stamp, docs/T5DR_COEXISTENCE.md).

Test hook (never for players): OPENRECOMP_RELEASES_TEST=http://127.0.0.1:<port> serves the API and the files
from a local fake GitHub; OPENRECOMP_RELEASES_TEST_KEY=<64 hex> adds a test signing key for it. Both are ignored
unless the address is this PC (127.0.0.1 / localhost / [::1]).
"""
import hashlib
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field

from . import updater as _sig   # verify_ed25519 (RFC 8032), the same arithmetic the launcher updater uses

MAX_META = 4_000_000
MAX_SUMS = 64 * 1024
MAX_SIG = 4096
MAX_ZIP = 1_000_000_000
MAX_UNPACKED = 3_000_000_000
MAX_FILES = 100_000
TIMEOUT = 20
MARKER = "openrecomp-release.json"          # written into an install this launcher made or updated
RE_VERSION = re.compile(r"^[vV]?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*))?$")
RE_BAD = re.compile(r'[<>:"|?*\x00-\x1f\\]')
_DEVICES = frozenset(["CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"] + [f"COM{i}" for i in range(10)]
                     + [f"LPT{i}" for i in range(10)])
TEST_ENV, TEST_KEY_ENV = "OPENRECOMP_RELEASES_TEST", "OPENRECOMP_RELEASES_TEST_KEY"
NO_CHECK_ENV = "OPENRECOMP_NO_GAME_CHECKS"


class ReleaseError(Exception):
    """key: an i18n message id for the player; the text stays in English for logs."""

    def __init__(self, key, detail=""):
        super().__init__(detail or key)
        self.key = key


@dataclass(frozen=True)
class Source:
    id: str
    title: str
    repository: str
    repository_id: str
    asset: str                       # zip name; {version} = without v, {tag} = the tag
    top: str                         # folder inside the zip that is the game
    folder: str                      # the install folder's name
    sums: tuple                      # checksum assets, first found is used; {asset} = the zip's name
    signature: str = ""              # signature asset ("" = none for this game)
    keys: tuple = ()                 # Ed25519 public keys (hex) of the release signature
    statement: str = ""
    protected: tuple = ()            # never exchanged by an update
    build_bytes: int = 0             # what the build needs later, for the free-space check
    unpack_factor: int = 3
    markers: tuple = field(default=())   # files that must exist in the unpacked game
    asset_pattern: str = ""          # when the release has no `asset`: the one zip whose name matches this
    sig_format: str = "t5dr-release-sig/1"
    beta: bool = False               # no stable release yet: its published pre-releases are offered to everyone


SOURCES = {
    "t5dr": Source(
        id="t5dr", title="Tekken 5 DR Online", repository="TheWishin/T5DROnline", repository_id="1423117739",
        asset="T5DR-Online-{version}.zip", top="T5DR-Online-{version}", folder="T5DR-Online-{version}",
        sums=("SHA256SUMS",), signature="SHA256SUMS.sig",
        # T5DR's release key (launcher/updater.py RELEASE_PUBLIC_KEYS, key id c2acdfbc80f3c4c2). An installed
        # T5DR's own key list wins for its updates (the owner may add a new key there first).
        keys=("b47cc1692fbdb91cb7e13a98edd56e99ceea307e693a151b05688ca8f9e67425",),
        statement="T5DR-Online-release-signature-v1",
        protected=("native", "launcher.json", "launcher.log", "launcher.log.1", "update-check.json", ".update",
                   "keys", "game", "build", "gamedata", "logs", "scratch", MARKER),
        build_bytes=2_000_000_000, markers=("launcher/core.py", "release.json")),
    "t4": Source(
        id="t4", title="Tekken 4", repository="TheWishin/Tekken4Recomp", repository_id="1435747302",
        asset="OpenRecomp-Tekken4-{tag}.zip", top="T4", folder="T4",
        sums=("SHA256SUMS", "{asset}.sha256"),
        # T4's own release key (tools/release_sign.py sign-t4, key id 6c690283a70408ad; docs/RELEASE_KEYS.md): the
        # T4 source's build scripts run on the player's PC, so its release is signed like T5DR's.
        signature="SHA256SUMS.sig", sig_format="tekken4-release-sig/1", statement="Tekken4Recomp-release-signature-v1",
        keys=("19f5844ad99435605c4fc6585dbb87a5e620b672c81537830878ed3f2da4a79f",),
        # 0.1.3: deps/ is part of the release (vendored PS2Recomp + libraries, the build output under it is
        # redone after an update anyway); save/ holds a release folder's memory cards.
        protected=("game", "generated", "out", "logs", "build", "save", "settings.json", MARKER),
        build_bytes=6_000_000_000, markers=("tools/build_game.ps1",),
        # The release asset is OpenRecomp-Tekken4-<tag>.zip (tools/make_release.py); one zip named like the launcher
        # bundle is also taken.
        asset_pattern=r"(?i)(?:openrecomp|tekken4|t4)[-_.a-z0-9]*\.zip",
        beta=True),
}


# ------------------------------------------------------------------------------------------------ versions
def version_key(v):
    m = RE_VERSION.match(str(v or "").strip())
    if not m:
        return None
    core = tuple(int(x) for x in m.group(1, 2, 3))
    if m.group(4) is None:
        return core, (1,)
    ids = tuple((0, int(p), "") if p.isdigit() else (1, 0, p.lower()) for p in m.group(4).split("."))
    return core, (0, ids)


def is_newer(remote, local):
    r, l_ = version_key(remote), version_key(local)
    return bool(r and l_ and r > l_)


def plain(tag):
    return tag[1:] if tag[:1] in ("v", "V") else tag


# ------------------------------------------------------------------------------------------------ URLs
def test_base():
    base = os.environ.get(TEST_ENV, "").rstrip("/")
    m = re.fullmatch(r"http://(127\.0\.0\.1|localhost|\[::1\]):(\d{1,5})", base)
    return base if m else ""


def api_root():
    return test_base() or "https://api.github.com"


def files_root():
    return test_base() or "https://github.com"


def url_allowed(src, url, kind):
    """kind 'api' or 'download' (T5DR updater.url_allowed's rules, per game)."""
    try:
        u = urllib.parse.urlsplit(str(url))
        port = u.port
    except ValueError:
        return False
    path = urllib.parse.unquote(u.path)
    if u.username is not None or u.password is not None or "\\" in path or any(p in (".", "..") for p in path.split("/")):
        return False
    repo = f"/{src.repository}/".lower()
    base = test_base()
    if base:
        if f"{u.scheme}://{u.netloc}".lower() != base.lower():
            return False
        if kind == "api":
            return path.lower().startswith("/repos" + repo)
        return path.lower().startswith(repo + "releases/download/") or path.startswith("/storage/" + src.repository_id + "/")
    if u.scheme != "https" or port not in (None, 443):
        return False
    host = (u.hostname or "").lower().rstrip(".")
    if kind == "api":
        return host == "api.github.com" and path.lower().startswith("/repos" + repo)
    if host == "github.com":
        return path.lower().startswith(repo + "releases/download/")
    if host in ("objects.githubusercontent.com", "release-assets.githubusercontent.com"):
        m = re.match(r"^/github-production-release-asset(?:-[0-9a-z]+)?/(\d+)/[^/]+$", path)
        return bool(m and m.group(1) == src.repository_id)
    return False


class _Redirects(urllib.request.HTTPRedirectHandler):
    max_redirections = 5

    def __init__(self, src, kind):
        super().__init__()
        self.src, self.kind = src, kind

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        newurl = urllib.parse.urljoin(req.full_url, newurl)
        if not url_allowed(self.src, newurl, self.kind):
            raise ReleaseError("@setup.err_foreign", f"redirect to {urllib.parse.urlsplit(newurl).hostname}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_url(src, url, kind="download", headers=None, timeout=TIMEOUT):
    if not url_allowed(src, url, kind):
        raise ReleaseError("@setup.err_foreign", f"refused {url}")
    from . import __version__
    request = urllib.request.Request(url, headers={"User-Agent": f"OpenRecomp-FGC/{__version__}",
                                                   "Accept": "application/vnd.github+json", **(headers or {})})
    response = urllib.request.build_opener(_Redirects(src, kind)).open(request, timeout=timeout)
    if not url_allowed(src, response.geturl(), kind):
        response.close()
        raise ReleaseError("@setup.err_foreign", f"came from {response.geturl()}")
    return response


# ------------------------------------------------------------------------------------------------ releases
def parse_release(src, data, channel="stable"):
    """The offer (a plain dict) for one GitHub release, or ReleaseError. T5DR's parse_release, per game."""
    if not isinstance(data, dict) or data.get("draft"):
        raise ReleaseError("@setup.err_release", "not a published release")
    tag = str(data.get("tag_name") or "")
    m = RE_VERSION.match(tag)
    if not m or "+" in tag:
        raise ReleaseError("@setup.err_release", f"unexpected version {tag!r}")
    prerelease = bool(data.get("prerelease")) or m.group(4) is not None
    if prerelease and channel != "prerelease":
        raise ReleaseError("@setup.err_release", f"{tag} is a test version")
    version = plain(tag)
    asset = src.asset.format(version=version, tag=tag)
    assets = {}
    for a in data.get("assets") or []:
        if isinstance(a, dict) and isinstance(a.get("name"), str):
            if a["name"] in assets:
                raise ReleaseError("@setup.err_release", f"duplicate asset {a['name']}")
            assets[a["name"]] = a
    z = assets.get(asset)
    if z is None and src.asset_pattern:
        found = [n for n in assets if re.fullmatch(src.asset_pattern, n)]
        if len(found) == 1:
            asset, z = found[0], assets[found[0]]
    sums = next((assets[n.format(asset=asset)] for n in src.sums if n.format(asset=asset) in assets), None)
    sig = assets.get(src.signature) if src.signature else None
    if not z or (src.sums and not sums):
        raise ReleaseError("@setup.err_release", f"{tag} has no {asset} with a checksum")
    for a in (z,) + ((sums,) if sums else ()) + ((sig,) if sig else ()):
        expected = f"{files_root()}/{src.repository}/releases/download/{tag}/{a['name']}"
        if a.get("browser_download_url") != expected or not url_allowed(src, expected, "download"):
            raise ReleaseError("@setup.err_release", f"{a['name']} is not this project's release file")
        if a.get("state", "uploaded") != "uploaded":
            raise ReleaseError("@setup.err_release", f"{a['name']} is still being uploaded")
    size = z.get("size")
    if type(size) is not int or not 0 < size <= MAX_ZIP:
        raise ReleaseError("@setup.err_release", "the zip has no plausible size")
    digest = re.fullmatch(r"sha256:([0-9a-fA-F]{64})", str(z.get("digest") or ""))
    body = str(data.get("body") or "")
    code = re.search(r"Code ID\s*\|\s*`?([0-9a-f]{16})`?", body)
    needs = RE_MIN_LAUNCHER.search(body)
    return dict(game=src.id, tag=tag, version=version, prerelease=prerelease, name=str(data.get("name") or tag)[:200],
                published=str(data.get("published_at") or "")[:10], notes=release_notes(body),
                code_id=code.group(1) if code else None,
                # 0.1.4: the oldest launcher that can install and build this release (release notes' marker line)
                min_launcher=needs.group(1) if needs else "",
                zip=dict(name=asset, url=z["browser_download_url"], size=size,
                         sha256=digest.group(1).lower() if digest else None),
                # sums None: a manifest game whose releases carry none (its check needs GitHub's digest only)
                sums=dict(name=sums["name"], url=sums["browser_download_url"]) if sums else None,
                sig=dict(url=sig["browser_download_url"]) if sig else None)


# "Needs OpenRecomp-FGC 0.1.4" in a game release's notes (tools/make_release.py writes it; an HTML comment
# <!-- min_launcher: 0.1.4 --> works too): the oldest launcher that installs and builds that release.
RE_MIN_LAUNCHER = re.compile(r"(?i)(?:needs\s+openrecomp-fgc|min[_ -]launcher\s*[:=])\s*v?(\d{1,3}\.\d{1,3}\.\d{1,3})\b")


def own_launcher_version():
    """This launcher's version from its release.json ("" in a source checkout)."""
    info = _read_json(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "release.json")) or {}
    version = str(info.get("version") or "")
    return version.lstrip("v") if version and version != "dev" else ""


def launcher_too_old(offer, launcher_version):
    """The launcher version a game offer needs when this launcher is older ("" when it is new enough or unknown)."""
    need = (offer or {}).get("min_launcher") or ""
    if not need or not launcher_version or not version_key("v" + str(launcher_version).lstrip("v")):
        return ""
    return need if is_newer("v" + need, "v" + str(launcher_version).lstrip("v")) else ""


def release_notes(body):
    """The release text's first part as plain sentences: no tables (T5DR's Code ID / file rows), no markup."""
    lines = []
    for line in str(body or "").split("\n---")[0].splitlines():
        line = line.strip().lstrip("#>*- ").strip()
        if line and not line.startswith("|") and not line.startswith("```") and not line.startswith("<!--"):
            lines.append(line)
    return " ".join(" ".join(lines).split())[:600]


def latest(src, channel="stable", opener=None):
    """The newest release of the channel (offer dict) or None when there is none yet."""
    opener = opener or open_url
    endpoint = "/releases/latest" if channel == "stable" else "/releases?per_page=30"
    url = f"{api_root()}/repos/{src.repository}{endpoint}"
    try:
        with opener(src, url, "api", {"X-GitHub-Api-Version": "2022-11-28"}) as r:
            raw = r.read(MAX_META + 1)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        if e.code in (403, 429):
            raise ReleaseError("@setup.err_rate", f"GitHub {e.code}") from None
        raise ReleaseError("@setup.err_network", f"GitHub {e.code}") from None
    except (OSError, ValueError) as e:
        raise ReleaseError("@setup.err_network", str(e)) from None
    if len(raw) > MAX_META:
        raise ReleaseError("@setup.err_release", "answer too large")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise ReleaseError("@setup.err_release", "not JSON") from None
    if channel == "stable":
        return parse_release(src, data, "stable")
    if not isinstance(data, list):
        raise ReleaseError("@setup.err_release", "not a list")
    offers = []
    for item in data:
        try:
            offers.append(parse_release(src, item, "prerelease"))
        except ReleaseError:
            continue                     # drafts, foreign assets, half-uploaded releases: skipped
    return max(offers, key=lambda o: version_key(o["version"])) if offers else None


def offer_from_lobby(src, data):
    """A lobby's latest_release (GitHub's release JSON, passed on by the T5DR server) as an offer, or None."""
    try:
        return parse_release(src, data, "stable") if data else None
    except ReleaseError:
        return None


# ------------------------------------------------------------------------------------------------ download
def download(src, url, dest, *, limit, expect=None, opener=None, progress=None, cancel=None):
    """Stream url to dest; returns its SHA-256."""
    opener = opener or open_url
    h, n, tmp = hashlib.sha256(), 0, dest + ".part"
    try:
        with opener(src, url, "download", {"Accept": "application/octet-stream"}, 60) as r, open(tmp, "wb") as f:
            total = expect or int(r.headers.get("Content-Length") or 0)
            while True:
                if cancel is not None and cancel.is_set():
                    raise ReleaseError("@setup.cancelled")
                block = r.read(1 << 18)
                if not block:
                    break
                n += len(block)
                if n > limit:
                    raise ReleaseError("@setup.err_size", "larger than a release")
                h.update(block)
                f.write(block)
                if progress:
                    progress(n, total)
        if expect and n != expect:
            raise ReleaseError("@setup.err_network", f"stopped at {n} of {expect} bytes")
        os.replace(tmp, dest)
    except ReleaseError:
        _remove(tmp)
        raise
    except (OSError, ValueError) as e:
        _remove(tmp)
        raise ReleaseError("@setup.err_network", str(e)) from None
    return h.hexdigest()


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def parse_sums(text, name):
    for line in str(text).splitlines():
        m = re.match(r"^([0-9a-fA-F]{64})\s+\*?(.+?)\s*$", line)
        if m and m.group(2) == name:
            return m.group(1).lower()
    return None


def signing_keys(src):
    keys = list(src.keys)
    test = os.environ.get(TEST_KEY_ENV, "").strip().lower()
    if test_base() and re.fullmatch(r"[0-9a-f]{64}", test):
        keys.append(test)
    return tuple(keys)


def install_keys(game, root):
    """An installed T5DR's own release keys (launcher/updater.py RELEASE_PUBLIC_KEYS), read as text: the owner may
    add a new key there before this launcher knows it."""
    if game != "t5dr" or not root:
        return ()
    try:
        with open(os.path.join(root, "launcher", "updater.py"), encoding="utf-8") as f:
            text = f.read(400_000)
    except OSError:
        return ()
    m = re.search(r"^RELEASE_PUBLIC_KEYS\s*=\s*\((.*?)\)", text, re.S | re.M)
    return tuple(k.lower() for k in re.findall(r"[\"']([0-9a-fA-F]{64})[\"']", m.group(1))) if m else ()


def check_signature(src, version, sums_bytes, sig_bytes, keys=None):
    """T5DR's release_sig.check_sig_file: the signature covers SHA256SUMS and the version."""
    keys = signing_keys(src) if keys is None else keys
    try:
        sig = json.loads(sig_bytes.decode("utf-8"))
        if not isinstance(sig, dict) or sig.get("format") != src.sig_format or sig.get("version") != version:
            raise ValueError
        signature = bytes.fromhex(sig["signature"])
        statement = (f"{src.statement}\nversion={version}\n"
                     f"sums-sha256={hashlib.sha256(sums_bytes).hexdigest()}\n").encode("utf-8")
        for key in keys:
            public = bytes.fromhex(key)
            if sig.get("key") == hashlib.sha256(public).hexdigest()[:16] and _sig.verify_ed25519(public, statement, signature):
                return sig["key"]
    except (ValueError, KeyError, TypeError, AttributeError, UnicodeError):
        pass
    raise ReleaseError("@setup.err_signature", f"{version}: no valid release signature")


def verified_zip(src, offer, work, *, keys=None, opener=None, progress=None, cancel=None):
    """Download SHA256SUMS (+ signature) and the zip into work; returns the zip's path once it matches."""
    progress = progress or (lambda *_: None)
    os.makedirs(work, exist_ok=True)
    sums_path = os.path.join(work, "SHA256SUMS")
    download(src, offer["sums"]["url"], sums_path, limit=MAX_SUMS, opener=opener, cancel=cancel)
    with open(sums_path, "rb") as f:
        sums_bytes = f.read()
    keys = signing_keys(src) if keys is None else keys
    if src.signature and keys:
        if not offer.get("sig"):
            raise ReleaseError("@setup.err_signature", f"{offer['version']} is not signed")
        sig_path = os.path.join(work, src.signature)
        download(src, offer["sig"]["url"], sig_path, limit=MAX_SIG, opener=opener, cancel=cancel)
        with open(sig_path, "rb") as f:
            check_signature(src, offer["version"], sums_bytes, f.read(), keys)
    want = parse_sums(sums_bytes.decode("utf-8", "replace"), offer["zip"]["name"])
    if not want:
        raise ReleaseError("@setup.err_checksum", "SHA256SUMS has no line for the zip")
    if offer["zip"].get("sha256") and offer["zip"]["sha256"] != want:
        raise ReleaseError("@setup.err_checksum", "SHA256SUMS and GitHub disagree")
    zpath = os.path.join(work, offer["zip"]["name"])
    got = download(src, offer["zip"]["url"], zpath, limit=MAX_ZIP, expect=offer["zip"]["size"], opener=opener,
                   cancel=cancel, progress=lambda n, t: progress("download", n, t))
    if progress:
        progress("check", 0, 0)
    if got != want:
        _remove(zpath)
        raise ReleaseError("@setup.err_checksum", f"sha256 {got[:16]} != {want[:16]}")
    return zpath


# ------------------------------------------------------------------------------------------------ unpacking
def _member_problem(src, name, top):
    if not name or "\\" in name or name.startswith("/") or RE_BAD.search(name.replace("/", "")):
        return "not a plain relative path"
    parts = name.rstrip("/").split("/")
    if any(p in ("", ".", "..") for p in parts):
        return "'.', '..' or an empty part"
    for p in parts:
        if p != p.rstrip(". ") or p.split(".", 1)[0].rstrip(" ").upper() in _DEVICES:
            return "a name Windows does not keep as written"
    if parts[0] == top and len(parts) > 1 and parts[1].lower() in {n.lower() for n in src.protected}:
        return "named like the player's own files"
    return None


def unpack(src, zip_path, dest, offer, progress=None, cancel=None):
    """The zip's game folder (`top`) unpacked into dest/<top>; everything else in the zip is skipped (T4's zip
    also carries a launcher). Returns that folder."""
    top = src.top.format(version=offer["version"], tag=offer["tag"])
    dest = os.path.abspath(dest)
    try:
        zf = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as e:
        raise ReleaseError("@setup.err_zip", str(e)) from None
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_FILES:
            raise ReleaseError("@setup.err_zip", "too many files")
        mine, total, seen = [], 0, set()
        for i in infos:
            why = _member_problem(src, i.filename, top)
            if why is None and (i.external_attr >> 16) & 0o170000 == 0o120000:
                why = "a symbolic link"
            if why is None and i.flag_bits & 1:
                why = "encrypted"
            if why:
                raise ReleaseError("@setup.err_zip", f"{i.filename!r}: {why}")
            key = i.filename.rstrip("/").casefold()
            if key in seen:
                raise ReleaseError("@setup.err_zip", f"{i.filename!r}: twice")
            seen.add(key)
            if i.filename.split("/", 1)[0] == top:
                mine.append(i)
                total += i.file_size
        if not mine:
            raise ReleaseError("@setup.err_zip", f"no {top} folder")
        if total > MAX_UNPACKED:
            raise ReleaseError("@setup.err_size", "unpacks to too much")
        done = 0
        for i in mine:
            if cancel is not None and cancel.is_set():
                raise ReleaseError("@setup.cancelled")
            target = os.path.abspath(os.path.join(dest, *i.filename.rstrip("/").split("/")))
            if not target.startswith(dest + os.sep):
                raise ReleaseError("@setup.err_zip", i.filename)
            if i.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            try:
                with zf.open(i) as s, open(target, "xb") as d:
                    shutil.copyfileobj(s, d, 1 << 20)
            except (zipfile.BadZipFile, EOFError) as e:
                raise ReleaseError("@setup.err_zip", str(e)) from None
            done += i.file_size
            if progress:
                progress(done, total)
    root = os.path.join(dest, top)
    for marker in src.markers:
        if not os.path.isfile(os.path.join(root, *marker.split("/"))):
            raise ReleaseError("@setup.err_zip", f"no {marker}")
    if src.id == "t4":
        from .adapters.t4_install import source_root
        if not source_root(root):
            raise ReleaseError("@setup.err_zip", "not a T4 source tree")
    # 0.1.4: the release says which launcher it needs (also checked before the download, from the notes)
    info = _read_json(os.path.join(root, "release.json")) or {}
    need = launcher_too_old(dict(min_launcher=str(info.get("min_launcher") or "")), own_launcher_version())
    if need:
        raise ReleaseError("@setup.needs_launcher", need)
    if src.id == "t5dr":
        info = _read_json(os.path.join(root, "release.json"))
        if not info or info.get("version") != offer["version"]:
            raise ReleaseError("@setup.err_zip", "release.json names another version")
    return root


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


# ------------------------------------------------------------------------------------------------ installs
def installed_version(game, root):
    """The version of an install: T5DR's release.json, else our marker (T4 sources have no release.json)."""
    if not root:
        return ""
    if game == "t5dr":
        info = _read_json(os.path.join(root, "release.json"))
        if info and version_key(info.get("version")):
            return str(info["version"])
    marker = _read_json(os.path.join(root, MARKER))
    return str(marker.get("version") or "") if marker and marker.get("game") == game else ""


def unknown_version_updatable(game, root):
    """A T4 tree without a version (a bundle's or Setup's T4/, or one the player chose) may still take a release:
    the exchange keeps every player file (SOURCES protected) and writes the marker, so the version is known after.
    Never a git checkout (a developer's tree: its own files would be replaced)."""
    if game != "t4" or not root or installed_version(game, root):
        return False
    if os.path.exists(os.path.join(root, ".git")):
        return False
    return all(os.path.isfile(os.path.join(root, *m.split("/"))) for m in SOURCES[game].markers)


def managed(game, root):
    """True for an install this launcher put there (it may build in it: nobody else's build is shared)."""
    marker = _read_json(os.path.join(root, MARKER)) if root else None
    return bool(marker and marker.get("game") == game and marker.get("installed_by") == "OpenRecomp-FGC")


def rebuild_required(game, root):
    marker = _read_json(os.path.join(root, MARKER)) if root else None
    return bool(marker and marker.get("game") == game and marker.get("rebuild_required"))


def clear_rebuild(game, root):
    marker = _read_json(os.path.join(root, MARKER)) if root else None
    if marker and marker.get("game") == game and marker.pop("rebuild_required", None):
        try:
            _write_json(os.path.join(root, MARKER), marker)
        except OSError:
            pass


def space_needed(src, offer, update=False):
    size = int(offer["zip"]["size"])
    return size + size * src.unpack_factor + (0 if update else src.build_bytes) + 100_000_000


def free_space(path):
    p = os.path.abspath(path)
    while p and not os.path.isdir(p):
        parent = os.path.dirname(p)
        if parent == p:
            return 0
        p = parent
    try:
        return shutil.disk_usage(p).free
    except OSError:
        return 0


def target_folder(src, offer, parent):
    return os.path.join(os.path.abspath(parent), src.folder.format(version=offer["version"], tag=offer["tag"]))


def check_target(src, offer, parent):
    """"" when the game can be installed under parent, else an i18n key."""
    target = target_folder(src, offer, parent)
    if len(os.path.abspath(parent)) < 3:
        return "@setup.err_folder"
    if os.path.exists(target) and (not os.path.isdir(target) or os.listdir(target)):
        return "@setup.err_exists"
    if free_space(parent) < space_needed(src, offer):
        return "@setup.err_space"
    try:
        os.makedirs(parent, exist_ok=True)
        probe = os.path.join(parent, f".openrecomp-probe-{os.getpid()}")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
    except OSError:
        return "@setup.err_write"
    return ""


def install_fresh(game, offer, parent, *, opener=None, progress=None, cancel=None, keys=None):
    """Download, verify, unpack into parent/<folder>. Returns the new install's root."""
    src = SOURCES[game]
    problem = check_target(src, offer, parent)
    if problem:
        raise ReleaseError(problem)
    target = target_folder(src, offer, parent)
    stage = os.path.join(os.path.abspath(parent), f".openrecomp-setup-{game}-{os.getpid()}-{int(time.time())}")
    os.makedirs(stage)
    try:
        zpath = verified_zip(src, offer, os.path.join(stage, "download"), keys=keys, opener=opener,
                             progress=progress, cancel=cancel)
        if progress:
            progress("unpack", 0, 0)
        new = unpack(src, zpath, os.path.join(stage, "new"), offer, cancel=cancel,
                     progress=lambda n, t: progress and progress("unpack", n, t))
        _write_json(os.path.join(new, MARKER), dict(game=game, version=offer["version"], tag=offer["tag"],
                                                    installed_by="OpenRecomp-FGC", sha256=offer["zip"].get("sha256"),
                                                    prerelease=bool(offer.get("prerelease"))))
        if os.path.isdir(target):
            os.rmdir(target)            # empty (checked above)
        os.rename(new, target)
        return target
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def processes_under(folder):
    """Programs running from folder (Windows); [] elsewhere."""
    if os.name != "nt":
        return []
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class PE(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("pid", wintypes.DWORD),
                    ("heap", ctypes.c_size_t), ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
                    ("ppid", wintypes.DWORD), ("prio", ctypes.c_long), ("flags", wintypes.DWORD),
                    ("exe", ctypes.c_wchar * 260)]
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.Process32FirstW.argtypes = k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PE)]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    prefix = os.path.normcase(os.path.abspath(folder)).rstrip("\\/") + os.sep
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    found = []
    if not snap or snap == ctypes.c_void_p(-1).value:
        return found
    try:
        pe = PE()
        pe.dwSize = ctypes.sizeof(PE)
        ok = k32.Process32FirstW(snap, ctypes.byref(pe))
        while ok:
            if pe.pid and pe.pid != os.getpid():
                h = k32.OpenProcess(0x1000, False, pe.pid)
                if h:
                    buf = ctypes.create_unicode_buffer(32768)
                    n = wintypes.DWORD(32768)
                    if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) and os.path.normcase(buf.value).startswith(prefix):
                        found.append(buf.value)
                    k32.CloseHandle(h)
            ok = k32.Process32NextW(snap, ctypes.byref(pe))
    finally:
        k32.CloseHandle(snap)
    return found


def _move(a, b, timeout=20.0):
    end, delay = time.time() + timeout, 0.1
    while True:
        try:
            os.rename(a, b)
            return
        except (FileExistsError, FileNotFoundError):
            raise
        except OSError as e:
            if time.time() >= end or getattr(e, "winerror", 5) not in (5, 32, 33, 145):
                raise
        time.sleep(delay)
        delay = min(delay * 2, 1.0)


def swap(src, root, new, backup):
    """Exchange the release's top-level items; the old ones wait in backup until the new ones are in, and come
    back on any failure (T5DR updater.swap's way). Player files are never named or moved.

    A journal beside backup (backup + ".json") names what moves: when the old files cannot all be put back
    (a file locked by another program), the backup stays and recover_update() finishes the rollback later."""
    protected = {n.lower() for n in src.protected}
    names = sorted(os.listdir(new))
    if any(n.lower() in protected for n in names):
        raise ReleaseError("@setup.err_zip", "the release carries a player's file name")
    olds = [n for n in sorted(os.listdir(root)) if n.lower() in {x.lower() for x in names}]
    moved_old, moved_new = [], []
    os.makedirs(backup, exist_ok=True)
    journal = backup + ".json"
    _write_json(journal, dict(state="swapping", old=olds, new=names))
    try:
        for n in olds:
            _move(os.path.join(root, n), os.path.join(backup, n))
            moved_old.append(n)
        for n in names:
            _move(os.path.join(new, n), os.path.join(root, n))
            moved_new.append(n)
    except OSError as e:
        left = []
        for n in reversed(moved_new):
            try:
                _move(os.path.join(root, n), os.path.join(new, n))
            except OSError:
                left.append(n)
        for n in reversed(moved_old):
            if os.path.lexists(os.path.join(root, n)):
                left.append(n)              # its new copy is still in the way: the old one stays in backup
                continue
            try:
                _move(os.path.join(backup, n), os.path.join(root, n))
            except OSError:
                left.append(n)
        if left:
            raise ReleaseError("@setup.err_restore", f"{e}; not put back: {', '.join(sorted(set(left)))}") from None
        _remove(journal)
        raise ReleaseError("@setup.err_busy", str(e)) from None
    _write_json(journal, dict(state="swapped", old=olds, new=names))
    return moved_old, moved_new


def update_stage(root):
    """The folder an update of root works in (beside root, so every move stays on one drive)."""
    root = os.path.abspath(root)
    return os.path.join(os.path.dirname(root), f".{os.path.basename(root)}.openrecomp-update")


def interrupted_update(root):
    """True when an earlier update of root left its backup (rollback unfinished, or the launcher was stopped)."""
    backup = os.path.join(update_stage(root), "backup")
    return bool(root) and os.path.isdir(backup) and bool(os.listdir(backup))


def recover_update(game, root):
    """Finish what an interrupted update left: put the old files back unless the exchange was complete.
    Raises @setup.err_restore while a file is still locked (the backup stays for the next try)."""
    stage = update_stage(root)
    backup = os.path.join(stage, "backup")
    if not interrupted_update(root):
        return False
    root = os.path.abspath(root)
    journal = _read_json(backup + ".json") or {}
    if journal.get("state") != "swapped":
        protected = {n.lower() for n in SOURCES[game].protected}
        discard = os.path.join(stage, "discard")
        os.makedirs(discard, exist_ok=True)
        olds = {str(n) for n in journal.get("old") or []}
        names = [str(n) for n in journal.get("new") or []]
        try:
            for n in sorted(os.listdir(backup)):
                if n.lower() in protected or n != os.path.basename(n):
                    continue
                if os.path.lexists(os.path.join(root, n)):
                    _move(os.path.join(root, n), os.path.join(discard, n))
                _move(os.path.join(backup, n), os.path.join(root, n))
            for n in names:                 # items only the new release has (the old one had none of that name)
                if (n not in olds and n.lower() not in protected and n == os.path.basename(n)
                        and os.path.lexists(os.path.join(root, n))):
                    _move(os.path.join(root, n), os.path.join(discard, n))
        except OSError as e:
            raise ReleaseError("@setup.err_restore", str(e)) from None
        if any(n.lower() not in protected for n in os.listdir(backup)):
            raise ReleaseError("@setup.err_restore", "the backup still holds files")
    shutil.rmtree(stage, ignore_errors=True)
    return True


def tree_digest(root, names):
    """One hash over the given top-level items (paths and bytes): T4 has no code id, its sources are its code."""
    h = hashlib.sha256()
    for name in sorted(names):
        base = os.path.join(root, name)
        paths = [base] if os.path.isfile(base) else [os.path.join(d, f) for d, _, fs in os.walk(base) for f in fs]
        for p in sorted(paths):
            h.update(os.path.relpath(p, root).replace("\\", "/").encode("utf-8") + b"\0")
            with open(p, "rb") as f:
                h.update(hashlib.sha256(f.read()).digest())
    return h.hexdigest()


def t5dr_build_code(root):
    """The code id of the built game (build stamp in the selected output folder), or None."""
    out_dir = os.path.join(root, "native")
    settings = _read_json(os.path.join(root, "launcher.json")) or {}
    chosen = settings.get("out_dir") or settings.get("out")
    if isinstance(chosen, str) and chosen:
        out_dir = chosen if os.path.isabs(chosen) else os.path.join(root, chosen)
    stamp = _read_json(os.path.join(out_dir, "build", "t5dr_build.json"))
    return stamp.get("code_id") if stamp else None


def update_in_place(game, offer, root, *, opener=None, progress=None, cancel=None, keys=None, reinstall=False):
    """Download, verify and exchange the program files of root. Returns dict(version, rebuild: True/False/None)."""
    src = SOURCES[game]
    root = os.path.abspath(root)
    current = installed_version(game, root)
    current_key = version_key(current)
    same_release = current_key is not None and version_key(offer["version"]) == current_key
    if current and not is_newer(offer["version"], current) and not (reinstall and same_release):
        raise ReleaseError("@setup.err_not_newer")
    if keys is None:
        keys = tuple(dict.fromkeys(signing_keys(src) + install_keys(game, root)))
    running = processes_under(root)
    if running:
        raise ReleaseError("@setup.err_running", ", ".join(sorted({os.path.basename(p) for p in running})))
    parent = os.path.dirname(root)
    if free_space(parent) < space_needed(src, offer, update=True):
        raise ReleaseError("@setup.err_space")
    stage = update_stage(root)
    recover_update(game, root)            # an earlier update that could not finish its rollback: finish it first
    if interrupted_update(root):
        raise ReleaseError("@setup.err_restore", "an earlier update left its backup")
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    keep = False
    try:
        zpath = verified_zip(src, offer, os.path.join(stage, "download"), keys=keys, opener=opener,
                             progress=progress, cancel=cancel)
        new = unpack(src, zpath, os.path.join(stage, "new"), offer, cancel=cancel,
                     progress=lambda n, t: progress and progress("unpack", n, t))
        _remove(zpath)
        names = os.listdir(new)
        before_code = t5dr_build_code(root) if game == "t5dr" else None
        old_digest = tree_digest(root, [n for n in names if os.path.exists(os.path.join(root, n))]) if game == "t4" else None
        new_digest = tree_digest(new, names) if game == "t4" else None
        if cancel is not None and cancel.is_set():
            raise ReleaseError("@setup.cancelled")      # last moment to stop: nothing of root has moved yet
        if progress:
            progress("swap", 0, 0)
        try:
            swap(src, root, new, os.path.join(stage, "backup"))
        except ReleaseError as e:
            keep = e.key == "@setup.err_restore"         # the old files wait in the backup: never delete them
            raise
        marker = _read_json(os.path.join(root, MARKER)) or dict(game=game)
        marker.update(game=game, version=offer["version"], tag=offer["tag"], sha256=offer["zip"].get("sha256"),
                      prerelease=bool(offer.get("prerelease")))
        _write_json(os.path.join(root, MARKER), marker)
        if game == "t5dr":
            info = _read_json(os.path.join(root, "release.json")) or {}
            rebuild = None if not (before_code and info.get("code_id")) else before_code != info["code_id"]
        else:
            rebuild = old_digest != new_digest
            if rebuild:
                marker["rebuild_required"] = True     # T4 has no build stamp to compare: until the next build
                _write_json(os.path.join(root, MARKER), marker)
        return dict(version=offer["version"], rebuild=rebuild, restart=game == "t5dr")
    finally:
        if not keep:
            shutil.rmtree(stage, ignore_errors=True)


def on_test_track(game, root):
    """An install of a pre-release (our marker says so, or its version has a test suffix) keeps getting the
    newer test versions: a tester who installed v0.2.0-beta.1 is not stranded until v0.2.0."""
    if not root:
        return False
    marker = _read_json(os.path.join(root, MARKER))
    if marker and marker.get("game") == game and marker.get("prerelease"):
        return True
    key = version_key(installed_version(game, root))
    return bool(key and key[1] != (1,))


def channel(config, game=None, root=None):
    """'prerelease' when the player turned on Test versions, for a game still in beta (no stable release: T4),
    or for an install that already is a test version; else 'stable' (published plain vX.Y.Z only)."""
    if (config or {}).get("game_prereleases"):
        return "prerelease"
    src = SOURCES.get(game)
    if src is not None and (src.beta or on_test_track(game, root)):
        return "prerelease"
    return "stable"
