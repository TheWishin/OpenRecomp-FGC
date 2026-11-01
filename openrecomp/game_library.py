"""Review and register an author's manifest; game files always remain the author's."""
import copy
import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.request
import uuid
from urllib.parse import urlsplit

from . import manifest as mf

MANIFEST_NAME = "openrecomp-game.json"
MAX_RELEASE_METADATA = 256 * 1024


class LibraryError(mf.ManifestError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _asset_redirect(url):
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and parsed.netloc == "release-assets.githubusercontent.com"
                and parsed.path.startswith("/github-production-release-asset/")
                and not parsed.fragment and len(url) <= 8192
                and not any(ord(c) < 33 for c in url) and "\\" not in url)
    except (TypeError, ValueError):
        return False


class _AssetRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _asset_redirect(newurl):
            raise LibraryError("@library.invalid_manifest")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_manifest(url, maximum):
    """Read bounded GitHub metadata without forwarding requests to another host."""
    parsed = urlsplit(url)
    api = parsed.netloc == "api.github.com"
    api_path = re.fullmatch(r"/repos/([A-Za-z0-9-]+/[A-Za-z0-9_.-]+)/(?:contents/openrecomp-game\.json|releases/latest)", parsed.path)
    asset_path = re.fullmatch(r"/([A-Za-z0-9-]+/[A-Za-z0-9_.-]+)/releases/download/([A-Za-z0-9][A-Za-z0-9._-]{0,99})/openrecomp-game\.json", parsed.path)
    if (parsed.scheme != "https" or parsed.query or parsed.fragment
            or not ((api and api_path) or (parsed.netloc == "github.com" and asset_path))):
        raise LibraryError("@library.invalid_source")
    try:
        mf.repository((api_path if api else asset_path).group(1))
    except mf.ManifestError as e:
        raise LibraryError("@library.invalid_source") from e
    accept = "application/vnd.github.raw+json" if "/contents/" in parsed.path else "application/vnd.github+json"
    request = urllib.request.Request(url, headers={
        "Accept": accept, "User-Agent": "OpenRecomp-game-manifest",
    })
    opener = urllib.request.build_opener(_NoRedirect() if api else _AssetRedirect())
    with opener.open(request, timeout=15) as response:
        size = response.headers.get("Content-Length")
        if size is not None and (not size.isdecimal() or int(size) > maximum):
            raise LibraryError("@library.invalid_manifest")
        data = response.read(maximum + 1)
    if len(data) > maximum:
        raise LibraryError("@library.invalid_manifest")
    return data


class Library:
    def __init__(self, config, fetch=None):
        self.config = config
        self.fetch = fetch or fetch_manifest
        self._previews = {}

    def _protected(self, game_id):
        manifests, _ = mf.load_all([mf.BUILTIN_DIR])
        return game_id.casefold() in {m["id"].casefold() for m in manifests}

    def _parse(self, data):
        if not isinstance(data, bytes) or len(data) > mf.MAX_MANIFEST_BYTES:
            raise LibraryError("@library.invalid_manifest")
        try:
            return mf.validate_external(mf.parse_bytes(data))
        except (mf.ManifestError, ValueError, TypeError, UnicodeError, RecursionError) as e:
            raise LibraryError("@library.invalid_manifest") from e

    def _release_manifest(self, source):
        """A release-only author can publish the same small JSON as a release asset."""
        data = self.fetch(f"https://api.github.com/repos/{source}/releases/latest", MAX_RELEASE_METADATA)
        if not isinstance(data, bytes) or len(data) > MAX_RELEASE_METADATA:
            raise LibraryError("@library.invalid_manifest")
        def pairs(items):
            out = {}
            for key, value in items:
                if key in out:
                    raise ValueError("duplicate field")
                out[key] = value
            return out
        try:
            release = json.loads(data, object_pairs_hook=pairs)
            if (not isinstance(release, dict) or release.get("draft") is not False
                    or release.get("prerelease") is not False):
                raise ValueError("not a public stable release")
            tag = release.get("tag_name")
            if not isinstance(tag, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", tag):
                raise ValueError("invalid tag")
            assets = release.get("assets")
            if not isinstance(assets, list) or len(assets) > 1024:
                raise ValueError("invalid assets")
            matches = [a for a in assets if isinstance(a, dict) and a.get("name") == MANIFEST_NAME]
            if len(matches) != 1:
                raise ValueError("missing unique manifest")
            asset = matches[0]
            url = f"https://github.com/{source}/releases/download/{tag}/{MANIFEST_NAME}"
            if (asset.get("browser_download_url") != url or type(asset.get("size")) is not int
                    or not 0 < asset["size"] <= mf.MAX_MANIFEST_BYTES):
                raise ValueError("invalid manifest asset")
            data = self.fetch(url, asset["size"])
            if not isinstance(data, bytes) or len(data) != asset["size"]:
                raise ValueError("incorrect manifest size")
            digest = asset.get("digest")
            if digest is not None and (not isinstance(digest, str)
                    or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
                    or hashlib.sha256(data).hexdigest() != digest[7:]):
                raise ValueError("incorrect manifest digest")
            return data
        except (ValueError, TypeError, RecursionError, UnicodeError) as e:
            raise LibraryError("@library.invalid_manifest") from e

    def preview(self, source):
        """Only the manifest is read; acceptance never downloads or runs a release."""
        if not isinstance(source, str) or not source.strip() or len(source) > 4096:
            raise LibraryError("@library.invalid_source")
        source = source.strip()
        root = ""
        try:
            repository = mf.repository(source)
        except mf.ManifestError:
            repository = None
        if repository:
            kind = "github"
            url = f"https://api.github.com/repos/{source}/contents/{MANIFEST_NAME}"
            try:
                try:
                    data = self.fetch(url, mf.MAX_MANIFEST_BYTES)
                except urllib.error.HTTPError as e:
                    if e.code != 404:
                        raise
                    data = self._release_manifest(source)
            except LibraryError:
                raise
            except (OSError, ValueError, urllib.error.URLError) as e:
                raise LibraryError("@library.manifest_unavailable") from e
        elif os.path.isdir(source):
            kind = "local"
            root = os.path.realpath(os.path.abspath(source))
            source = root
            try:
                path = mf.resolve_path(root, MANIFEST_NAME)
                if not os.path.isfile(path) or os.path.getsize(path) > mf.MAX_MANIFEST_BYTES:
                    raise LibraryError("@library.invalid_manifest")
                with open(path, "rb") as stream:
                    data = stream.read(mf.MAX_MANIFEST_BYTES + 1)
            except LibraryError:
                raise
            except (OSError, mf.ManifestError) as e:
                raise LibraryError("@library.manifest_unavailable") from e
        else:
            raise LibraryError("@library.invalid_source")
        manifest = self._parse(data)
        if kind == "github" and manifest["repository"].casefold() != source.casefold():
            raise LibraryError("@library.invalid_manifest")
        if self._protected(manifest["id"]):
            raise LibraryError("@library.invalid_manifest")
        token = uuid.uuid4().hex
        preview = dict(manifest=manifest, source=source, root=root, author=manifest["author"],
                       requirements=copy.deepcopy(manifest.get("requirements", [])),
                       warning="@library.third_party", token=token)
        self._previews[token] = (copy.deepcopy(preview), kind)
        while len(self._previews) > 4:
            del self._previews[next(iter(self._previews))]
        return preview

    def accept(self, preview):
        """Persist exactly the review, with its author's release source pinned per game."""
        token = preview.get("token") if isinstance(preview, dict) else None
        stored = self._previews.get(token) if isinstance(token, str) else None
        if stored is None or stored[0] != preview:
            raise LibraryError("@library.preview_expired")
        reviewed, kind = stored
        manifest = mf.validate_external(copy.deepcopy(reviewed["manifest"]))
        game_id = manifest["id"]
        if self._protected(game_id):
            raise LibraryError("@library.invalid_manifest")
        old_pin = self.config.get("game_sources", {}).get(game_id)
        pin = dict(repository=manifest["repository"], author=manifest["author"],
                   source=reviewed["source"], kind=kind)
        folder = mf.user_games_dir()
        destination = os.path.join(folder, game_id + ".json")
        if os.path.islink(destination):
            raise LibraryError("@library.invalid_manifest")
        if old_pin:
            if (old_pin.get("repository", "").casefold() != pin["repository"].casefold()
                    or old_pin.get("author") != pin["author"]
                    or old_pin.get("kind") != kind
                    or (kind == "local" and os.path.normcase(os.path.realpath(old_pin.get("source", "")))
                        != os.path.normcase(reviewed["root"]))):
                raise LibraryError("@library.source_changed")
        elif os.path.lexists(destination):
            raise LibraryError("@library.source_changed")
        previous = None
        if os.path.exists(destination):
            with open(destination, "rb") as stream:
                previous = stream.read(mf.MAX_MANIFEST_BYTES + 1)
            if len(previous) > mf.MAX_MANIFEST_BYTES:
                raise LibraryError("@library.invalid_manifest")
        previous_config = copy.deepcopy(self.config)
        os.makedirs(mf.user_dir(), exist_ok=True)
        temporary = None
        installed = False
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=mf.user_dir(),
                                             prefix=".game-review-", suffix=".json", delete=False) as stream:
                temporary = stream.name
                json.dump(manifest, stream, ensure_ascii=False, separators=(",", ":"))
            mf.install(temporary)
            installed = True
            self.config.setdefault("roots", {}).setdefault(game_id, reviewed["root"] or os.path.join(
                mf.user_dir(), "installs", game_id))
            self.config.setdefault("game_sources", {})[game_id] = pin
            if kind == "local" and "version" in manifest:
                from .game_updates import GameUpdateError, version_key
                try:
                    version_key(manifest["version"])
                    if os.path.isfile(mf.resolve_path(reviewed["root"], manifest["exe"])):
                        self.config.setdefault("game_versions", {}).setdefault(game_id, manifest["version"])
                except (GameUpdateError, mf.ManifestError):
                    pass
            mf.save_config(self.config)
        except Exception:
            self.config.clear()
            self.config.update(previous_config)
            if installed:
                if previous is None:
                    os.unlink(destination)
                else:
                    with open(destination, "wb") as stream:
                        stream.write(previous)
            raise
        finally:
            if temporary is not None and os.path.exists(temporary):
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
        del self._previews[token]
        return manifest

    def remove(self, game_id):
        """Forget the registration, leaving installs, settings, replays and saves alone."""
        if (not isinstance(game_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", game_id)
                or self._protected(game_id)):
            raise LibraryError("@library.remove_failed")
        try:
            mf.safe_relative_path(game_id + ".json")
        except mf.ManifestError as e:
            raise LibraryError("@library.remove_failed") from e
        destination = os.path.join(mf.user_games_dir(), game_id + ".json")
        if not os.path.lexists(destination):
            return False
        if os.path.islink(destination):
            raise LibraryError("@library.remove_failed")
        try:
            manifest = mf.load_file(destination)
            if manifest.get("adapter") != "generic":
                raise LibraryError("@library.remove_failed")
            previous_config = copy.deepcopy(self.config)
            self.config.get("roots", {}).pop(game_id, None)
            self.config.get("game_sources", {}).pop(game_id, None)
            self.config.get("game_versions", {}).pop(game_id, None)
            self.config.get("generic_sources", {}).pop(game_id, None)
            if self.config.get("last_game") == game_id:
                self.config.pop("last_game")
            try:
                mf.save_config(self.config)
                os.unlink(destination)
            except Exception:
                self.config.clear()
                self.config.update(previous_config)
                mf.save_config(self.config)
                raise
        except (OSError, mf.ManifestError, ValueError) as e:
            raise LibraryError("@library.remove_failed") from e
        return True
