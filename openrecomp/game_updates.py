"""Explicit author release checks and isolated, hash-verified game installs."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import urllib.parse
import urllib.request
import uuid
import zipfile

from . import manifest as mf

MAX_METADATA = 1024 * 1024
MAX_ARCHIVE = 512 * 1024 * 1024
MAX_UNPACKED = 2 * MAX_ARCHIVE
MAX_FILES = 10000
_VERSION = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*))?\Z")


class GameUpdateError(Exception):
    def __init__(self):
        super().__init__("@games.update_failed")


def version_key(value):
    match = _VERSION.fullmatch(value) if isinstance(value, str) else None
    if not match or len(value) > 100:
        raise GameUpdateError()
    if any(part.isdigit() and len(part) > 1 and part.startswith("0") for part in (match.group(4) or "").split(".")):
        raise GameUpdateError()
    return tuple(map(int, match.groups()[:3])), match.group(4) or ""


def _order(version):
    number, suffix = version_key(version)
    identifiers = tuple((0, int(part)) if part.isdigit() else (1, part) for part in suffix.split("."))
    return number, not suffix, identifiers


def _url(url, repository, *, api=False, redirected=False):
    try:
        parts = urllib.parse.urlsplit(url)
        if (parts.scheme != "https" or parts.username or parts.password or parts.fragment
                or parts.port is not None or "\\" in url or any(ord(c) < 33 for c in url)):
            return False
        if "%" in parts.path or any(part in (".", "..") for part in parts.path.split("/")):
            return False
        if api:
            return (parts.netloc == "api.github.com" and not parts.query
                    and parts.path in (f"/repos/{repository}/releases/latest", f"/repos/{repository}/releases"))
        if parts.netloc == "github.com":
            return not parts.query and parts.path.startswith(f"/{repository}/releases/download/")
        return (redirected and parts.netloc == "release-assets.githubusercontent.com"
                and parts.path.startswith("/github-production-release-asset"))
    except (ValueError, TypeError):
        return False


class _Redirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, repository, api):
        self.repository, self.api = repository, api

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urljoin(req.full_url, newurl)
        if self.api or not _url(target, self.repository, redirected=True):
            raise GameUpdateError()
        return super().redirect_request(req, fp, code, msg, headers, target)


def _fetch(url, limit):
    parts = urllib.parse.urlsplit(url)
    api = parts.hostname == "api.github.com"
    segments = parts.path.split("/")
    repository = "/".join(segments[2:4] if api else segments[1:3])
    if not _url(url, repository, api=api):
        raise GameUpdateError()
    request = urllib.request.Request(url, headers={"User-Agent": "OpenRecomp-author-games", "Accept": "application/vnd.github+json"})
    with urllib.request.build_opener(_Redirects(repository, api)).open(request, timeout=20) as response:
        if not _url(response.geturl(), repository, api=api, redirected=not api):
            raise GameUpdateError()
        raw = response.read(limit + 1)
    if len(raw) > limit:
        raise GameUpdateError()
    return raw


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise GameUpdateError()
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs)
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise GameUpdateError() from exc


def _newer(version, current):
    key = _order(version)
    if not current:
        return True
    return key > _order(current)


class GameUpdates:
    def __init__(self, config, fetch=None):
        self.config = config
        self.fetch = fetch or _fetch
        self.offers = {}

    def _read(self, url, limit):
        raw = self.fetch(url, limit)
        if not isinstance(raw, bytes) or len(raw) > limit:
            raise GameUpdateError()
        return raw

    def _manifest(self, manifest):
        m = mf.validate_external(manifest)
        source = self.config.get("game_sources", {}).get(m["id"])
        if (not source or source.get("repository") != m["repository"]
                or source.get("author") != m["author"] or not m.get("releases")):
            raise GameUpdateError()
        return m

    def _current(self, m):
        current = self.config.get("game_versions", {}).get(m["id"], "")
        root = self.config.get("roots", {}).get(m["id"])
        if not current and root and os.path.isfile(mf.resolve_path(root, m["exe"])):
            current = m.get("version", "")
        return current

    def _release(self, m, release):
        if not isinstance(release, dict) or release.get("draft") is not False:
            raise GameUpdateError()
        version = release.get("tag_name")
        _, suffix = version_key(version)
        channel = m["releases"]["channel"]
        if type(release.get("prerelease")) is not bool:
            raise GameUpdateError()
        if channel == "stable" and (release["prerelease"] or suffix):
            raise GameUpdateError()
        if release["prerelease"] != bool(suffix):
            raise GameUpdateError()
        assets = release.get("assets")
        if not isinstance(assets, list) or len(assets) > 1000:
            raise GameUpdateError()
        selected = [a for a in assets if isinstance(a, dict) and a.get("name") == m["releases"]["asset"]]
        if len(selected) != 1:
            raise GameUpdateError()
        asset = selected[0]
        expected_url = f"https://github.com/{m['repository']}/releases/download/{version}/{m['releases']['asset']}"
        size = asset.get("size")
        if (asset.get("browser_download_url") != expected_url or type(size) is not int
                or not 0 < size <= MAX_ARCHIVE):
            raise GameUpdateError()
        verification = m["releases"]["verification"]
        if verification["method"] == "sha256":
            digest = verification["sha256"].lower()
        else:
            value = asset.get("digest")
            if not isinstance(value, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", value):
                raise GameUpdateError()
            digest = value[7:]
        return dict(id=m["id"], repository=m["repository"], channel=channel, version=version,
                    url=expected_url, sha256=digest, size=size, notes=str(release.get("body") or "")[:2000])

    def check(self, manifest):
        m = self._manifest(manifest)
        self.offers.pop(m["id"], None)
        endpoint = "latest" if m["releases"]["channel"] == "stable" else ""
        url = f"https://api.github.com/repos/{m['repository']}/releases" + ("/" + endpoint if endpoint else "")
        raw = _json(self._read(url, MAX_METADATA))
        if endpoint:
            offer = self._release(m, raw)
        else:
            if not isinstance(raw, list) or len(raw) > 100:
                raise GameUpdateError()
            candidates = []
            for release in raw:
                if isinstance(release, dict) and release.get("draft") is False:
                    assets = release.get("assets")
                    if isinstance(assets, list) and not any(
                            isinstance(asset, dict) and asset.get("name") == m["releases"]["asset"]
                            for asset in assets):
                        continue
                    candidates.append(self._release(m, release))
            if not candidates:
                return None
            offer = max(candidates, key=lambda item: _order(item["version"]))
        if not _newer(offer["version"], self._current(m)):
            return None
        self.offers[m["id"]] = (copy.deepcopy(m), copy.deepcopy(offer))
        return copy.deepcopy(offer)

    def install(self, manifest, offer):
        m = self._manifest(manifest)
        if self.offers.get(m["id"]) != (m, offer):
            raise GameUpdateError()
        if not _newer(offer["version"], self._current(m)):
            raise GameUpdateError()
        raw = self._read(offer["url"], min(MAX_ARCHIVE, offer["size"]))
        if len(raw) != offer["size"] or hashlib.sha256(raw).hexdigest() != offer["sha256"]:
            raise GameUpdateError()
        base = Path(mf.user_dir()) / "installs" / m["id"]
        # Refuse an existing link before placing a transaction below a managed folder.
        expected = Path(mf.user_dir()).absolute() / "installs" / m["id"]
        if base.resolve() != expected:
            raise GameUpdateError()
        base.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".update-", dir=base))
        try:
            self._extract(raw, stage)
            if not Path(mf.resolve_path(str(stage), m["exe"])).is_file():
                raise GameUpdateError()
            self._preserve_data(m, stage)
            name = offer["version"] + "-" + offer["sha256"][:16]
            destination = base / name
            while destination.exists() or destination.is_symlink() or os.path.isjunction(destination):
                destination = base / (name + "-" + uuid.uuid4().hex)
            stage.rename(destination)
        except (OSError, ValueError, zipfile.BadZipFile, RuntimeError, mf.ManifestError) as exc:
            raise GameUpdateError() from exc
        finally:
            if stage.exists():
                shutil.rmtree(stage)
        self.config.setdefault("roots", {})[m["id"]] = str(destination)
        self.config.setdefault("game_versions", {})[m["id"]] = offer["version"]
        self.offers.pop(m["id"], None)
        return str(destination)

    def _preserve_data(self, m, stage):
        previous = self.config.get("roots", {}).get(m["id"])
        if not previous or not os.path.isdir(previous):
            return
        paths = [m[key]["file"] for key in ("settings", "controls") if key in m]
        if m.get("replays"):
            paths.append(m["replays"])
        copied, total = 0, 0
        for relative in paths:
            source = Path(mf.resolve_path(previous, relative))
            if not source.exists():
                continue
            target = Path(mf.resolve_path(str(stage), relative))
            entries = [(source, target)]
            while entries:
                old, new = entries.pop()
                copied += 1
                if copied > MAX_FILES:
                    raise GameUpdateError()
                if old.is_symlink() or os.path.isjunction(old):
                    raise GameUpdateError()
                if old.is_dir():
                    if new.exists() and not new.is_dir():
                        raise GameUpdateError()
                    new.mkdir(parents=True, exist_ok=True)
                    for child in old.iterdir():
                        mf.safe_relative_path(child.relative_to(Path(previous)).as_posix())
                        entries.append((child, new / child.name))
                        if copied + len(entries) > MAX_FILES:
                            raise GameUpdateError()
                    continue
                if not old.is_file() or (new.exists() and not new.is_file()):
                    raise GameUpdateError()
                if total + old.stat().st_size > MAX_UNPACKED:
                    raise GameUpdateError()
                new.parent.mkdir(parents=True, exist_ok=True)
                with old.open("rb") as input_file, new.open("wb") as output_file:
                    while chunk := input_file.read(1024 * 1024):
                        total += len(chunk)
                        if total > MAX_UNPACKED:
                            raise GameUpdateError()
                        output_file.write(chunk)

    @staticmethod
    def _extract(raw, stage):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if not entries or len(entries) > MAX_FILES:
                raise GameUpdateError()
            paths, files, spellings, total = {}, set(), {}, 0
            for entry in entries:
                if entry.orig_filename != entry.filename:
                    raise GameUpdateError()
                name = entry.filename[:-1] if entry.is_dir() else entry.filename
                mf.safe_relative_path(name)
                key = name.casefold()
                parts = name.split("/")
                for index in range(1, len(parts) + 1):
                    spelling = "/".join(parts[:index])
                    folded = spelling.casefold()
                    if folded in spellings and spellings[folded] != spelling:
                        raise GameUpdateError()
                    spellings[folded] = spelling
                mode = entry.external_attr >> 16
                if (key in paths or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR))
                        or entry.flag_bits & 1 or entry.file_size < 0):
                    raise GameUpdateError()
                paths[key] = entry
                if not entry.is_dir():
                    files.add(key)
                total += entry.file_size
                if total > MAX_UNPACKED:
                    raise GameUpdateError()
            for key in paths:
                parts = key.split("/")
                if any("/".join(parts[:i]) in files for i in range(1, len(parts))):
                    raise GameUpdateError()
            for key, entry in paths.items():
                target = Path(mf.resolve_path(str(stage), entry.filename.rstrip("/")))
                if entry.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                written = 0
                with archive.open(entry) as source, target.open("xb") as output:
                    while chunk := source.read(1024 * 1024):
                        written += len(chunk)
                        if written > entry.file_size:
                            raise GameUpdateError()
                        output.write(chunk)
