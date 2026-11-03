"""Test helpers: a fake GitHub on 127.0.0.1, release zips for T5DR / T4 and an Ed25519 signer.

Nothing here is game data: the "games" are a few text files with the names the launcher checks for.
"""
import hashlib
import http.server
import io
import json
import threading
import urllib.parse
import zipfile

from openrecomp import updater as _ed

T5DR_REPO, T5DR_ID = "TheWishin/T5DROnline", "1423117739"
T4_REPO, T4_ID = "TheWishin/Tekken4Recomp", "1435747302"
TEST_SEED = bytes(range(32))


# ------------------------------------------------------------------------------------------------ Ed25519 (RFC 8032)
def _encode(point):
    x, y = point
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _base():
    return _ed._point(bytes.fromhex("58" + "66" * 31))


def _secret(seed):
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(seed=TEST_SEED):
    return _encode(_ed._mul(_base(), _secret(seed)[0]))


def sign(message, seed=TEST_SEED):
    a, prefix = _secret(seed)
    public = public_key(seed)
    r = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little") % _ed._L
    big_r = _encode(_ed._mul(_base(), r))
    k = int.from_bytes(hashlib.sha512(big_r + public + message).digest(), "little") % _ed._L
    return big_r + ((r + k * a) % _ed._L).to_bytes(32, "little")


def t5dr_signature(version, sums_bytes, seed=TEST_SEED):
    """SHA256SUMS.sig as T5DR's release_sig.py writes it."""
    public = public_key(seed)
    statement = (f"T5DR-Online-release-signature-v1\nversion={version}\n"
                 f"sums-sha256={hashlib.sha256(sums_bytes).hexdigest()}\n").encode("utf-8")
    return json.dumps(dict(format="t5dr-release-sig/1", version=version, key=hashlib.sha256(public).hexdigest()[:16],
                           signature=sign(statement, seed).hex())).encode("utf-8")


# ------------------------------------------------------------------------------------------------ zips
def zip_bytes(entries):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries:
            entry = zipfile.ZipInfo(name)
            entry.filename = name            # ZipInfo turns \ into /: keep a bad name under test
            entry.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(entry, data)
    return out.getvalue()


def t5dr_entries(version, code_id="0123456789abcdef", extra=()):
    top = f"T5DR-Online-{version}"
    return [(f"{top}/release.json", json.dumps(dict(version=version, code_id=code_id))),
            (f"{top}/launcher/core.py", f"VERSION = {version!r}\n"),
            (f"{top}/launcher/updater.py", "# test\n"),
            (f"{top}/README.md", f"T5DR test release {version}\n"),
            *extra]


def t4_entries(tag, marker="", extra=()):
    entries = [("OpenRecomp-FGC/openrecomp/__init__.py", '__version__ = "0.0.1"\n'),
               ("START_HERE.txt", "test\n")]
    for name in ("tools/build_game.ps1", "tools/iso_extract.py", "tools/net_preflight.ps1",
                 "config/game.toml", "runtime/main.cpp", "patches/README.txt"):
        entries.append((f"T4/{name}", f"# {tag} {marker}\n"))
    return entries + list(extra)


# ------------------------------------------------------------------------------------------------ fake GitHub
class FakeGitHub:
    """GitHub's release API and download URLs for the two repositories, on 127.0.0.1."""

    def __init__(self, redirect=True):
        self.releases = {T5DR_REPO: [], T4_REPO: []}
        self.files = {}
        self.redirect = redirect
        self.requests = []
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                fake.requests.append(self.path)
                path = urllib.parse.urlsplit(self.path).path
                for repo in fake.releases:
                    if path == f"/repos/{repo}/releases/latest":
                        stable = [r for r in fake.releases[repo] if not r["draft"] and not r["prerelease"]]
                        return self._json(stable[-1]) if stable else self._send(404, b"{}")
                    if path == f"/repos/{repo}/releases":
                        return self._json(list(reversed(fake.releases[repo])))
                if path in fake.files:
                    if fake.redirect and "/releases/download/" in path:
                        repo = "/".join(path.split("/")[1:3])
                        rid = T5DR_ID if repo == T5DR_REPO else T4_ID
                        self.send_response(302)
                        tag, name = path.split("/")[-2:]
                        self.send_header("Location", f"/storage/{rid}/{tag}/{name}?k={len(fake.requests)}")
                        self.end_headers()
                        return None
                    return self._send(200, fake.files[path])
                if path.startswith("/storage/"):
                    _, _, rid, tag, name = path.split("/")
                    repo = rf_repo(rid)
                    data = fake.files.get(f"/{repo}/releases/download/{tag}/{name}")
                    if data is not None:
                        return self._send(200, data)
                return self._send(404, b"not found")

            def _json(self, data):
                self._send(200, json.dumps(data).encode("utf-8"), "application/json")

            def _send(self, code, body, kind="application/octet-stream"):
                self.send_response(code)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        def rf_repo(rid):
            return T5DR_REPO if rid == T5DR_ID else T4_REPO

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    def add(self, repo, tag, assets, prerelease=False, draft=False, body=""):
        """assets: {name: bytes}. Returns the release JSON (as GitHub's API gives it)."""
        listed = []
        for name, data in assets.items():
            path = f"/{repo}/releases/download/{tag}/{name}"
            self.files[path] = data
            listed.append(dict(name=name, size=len(data), state="uploaded",
                               digest="sha256:" + hashlib.sha256(data).hexdigest(),
                               browser_download_url=self.base + path))
        release = dict(tag_name=tag, name=tag, draft=draft, prerelease=prerelease, body=body,
                       published_at="2026-11-03T10:00:00Z", assets=listed)
        self.releases[repo].append(release)
        return release

    def add_t5dr(self, version, code_id="0123456789abcdef", prerelease=False, signed=True, seed=TEST_SEED, zip_data=None,
                 sums_for=None):
        name = f"T5DR-Online-{version}.zip"
        data = zip_data if zip_data is not None else zip_bytes(t5dr_entries(version, code_id))
        sums = f"{hashlib.sha256(sums_for if sums_for is not None else data).hexdigest()}  {name}\n".encode()
        assets = {name: data, "SHA256SUMS": sums}
        if signed:
            assets["SHA256SUMS.sig"] = t5dr_signature(version, sums, seed)
        body = f"Test release {version}\n\n| Code ID | `{code_id}` |\n"
        return self.add(T5DR_REPO, "v" + version, assets, prerelease=prerelease, body=body)

    def add_t4(self, tag, marker="", prerelease=True, name=None):
        name = name or f"OpenRecomp-Tekken4-{tag}.zip"
        data = zip_bytes(t4_entries(tag, marker))
        return self.add(T4_REPO, tag, {name: data, name + ".sha256": f"{hashlib.sha256(data).hexdigest()}  {name}\n".encode()},
                        prerelease=prerelease)
