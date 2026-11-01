"""Signed, channel-bound launcher updates. Also runs alone from a private helper Python.

No game files or player settings are part of a transaction. Trust is deliberately empty
until the owner chooses this project's release repository, channel and public key.
"""
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import stat
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass


RELEASE_REPOSITORY = ""
RELEASE_REPOSITORY_ID = ""
RELEASE_CHANNEL = ""
RELEASE_PUBLIC_KEYS = ()
PROJECT = "openrecomp-fgc"
CONFIRM_AFTER_MS = 15000
CONFIRM_WAIT = 120
CONFIRM_ENV = "OPENRECOMP_UPDATE_CONFIRM"
MAX_ZIP = 1024 * 1024 * 1024
MAX_UNPACKED = 3 * MAX_ZIP
PROGRAM_ITEMS = ("OpenRecomp.exe", "openrecomp_boot.py", "python", "openrecomp", "games",
                 "LICENSES", "docs", "LICENSE", "release.json")
REQUIRED_ITEMS = ("OpenRecomp.exe", "openrecomp_boot.py", "python/pythonw.exe", "openrecomp/app.py", "release.json")
_VERSION = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
_CHANNEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{2,100}\Z")
_DEVICES = ({"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
            | {f"{p}{n}" for p in ("COM", "LPT") for n in "0123456789¹²³"})


class UpdateError(Exception):
    def __init__(self, detail, key="update_failed", *, safe_to_unlock=False):
        super().__init__(detail)
        self.key = key
        self.safe_to_unlock = safe_to_unlock


@dataclass(frozen=True)
class Channel:
    repository: str
    repository_id: str
    name: str
    public_keys: tuple

    def validate(self):
        if (not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repository)
                or not str(self.repository_id).isdigit() or not _CHANNEL.fullmatch(self.name)
                or not self.public_keys or any(not re.fullmatch(r"[0-9a-f]{64}", k) for k in self.public_keys)):
            raise UpdateError("The owner must configure this project's release channel and signing public key.",
                              "updates_unconfigured")
        return self


def configured_channel():
    return Channel(RELEASE_REPOSITORY, RELEASE_REPOSITORY_ID, RELEASE_CHANNEL, RELEASE_PUBLIC_KEYS).validate()


def version_key(version):
    match = _VERSION.fullmatch(str(version))
    return tuple(map(int, match.groups())) if match else None


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def local_version(root):
    try:
        return _json(Path(root) / "release.json").get("version", "dev")
    except (OSError, ValueError, AttributeError):
        return "dev"


def url_allowed(url, channel, kind="download"):
    try:
        value = urllib.parse.urlsplit(url)
        path = urllib.parse.unquote(value.path)
        if (value.scheme != "https" or value.username or value.password or value.port not in (None, 443)
                or "\\" in path or any(p in (".", "..") for p in path.split("/")) or value.fragment):
            return False
        host = (value.hostname or "").lower()
        if kind == "api":
            return host == "api.github.com" and path == f"/repos/{channel.repository}/releases/latest"
        if host == "github.com":
            return path.startswith(f"/{channel.repository}/releases/download/")
        return host in ("objects.githubusercontent.com", "release-assets.githubusercontent.com") and bool(
            re.fullmatch(r"/github-production-release-asset(?:-[0-9a-z]+)?/" + re.escape(str(channel.repository_id)) + r"/[^/]+", path))
    except (ValueError, TypeError):
        return False


class _Redirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, channel, kind):
        self.channel, self.kind = channel, kind

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urljoin(req.full_url, newurl)
        if not url_allowed(target, self.channel, self.kind):
            raise UpdateError("An update redirect left this project's release channel.")
        return super().redirect_request(req, fp, code, msg, headers, target)


def _open(url, channel, kind="download"):
    if not url_allowed(url, channel, kind):
        raise UpdateError("Refused a URL outside this project's release channel.")
    request = urllib.request.Request(url, headers={"User-Agent": "OpenRecomp-FGC-updater", "Accept": "application/vnd.github+json"})
    response = urllib.request.build_opener(_Redirects(channel, kind)).open(request, timeout=20)
    if not url_allowed(response.geturl(), channel, kind):
        response.close()
        raise UpdateError("The update response left this project's release channel.")
    return response


def _download(url, channel, limit, destination=None):
    size, chunks = 0, []
    with _open(url, channel) as response:
        output = open(destination, "wb") if destination else None
        try:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise UpdateError("The update exceeds its allowed size.")
                output.write(chunk) if output else chunks.append(chunk)
        finally:
            if output:
                output.close()
    return size if destination else b"".join(chunks)


def parse_release(data, channel):
    channel.validate()
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease") or not version_key(data.get("tag_name")):
        raise UpdateError("Only published plain vX.Y.Z releases are accepted.")
    version = data["tag_name"]
    wanted = (f"OpenRecomp-{version}.zip", "SHA256SUMS", "SHA256SUMS.sig")
    assets = data.get("assets")
    if not isinstance(assets, list):
        raise UpdateError("The release has no signed assets.")
    selected = {}
    for name in wanted:
        matches = [a for a in assets if isinstance(a, dict) and a.get("name") == name]
        if len(matches) != 1 or not url_allowed(matches[0].get("browser_download_url"), channel):
            raise UpdateError("The release has missing, duplicate or foreign assets.")
        selected[name] = matches[0]
        expected_path = f"/{channel.repository}/releases/download/{version}/{name}"
        asset_url = urllib.parse.urlsplit(matches[0]["browser_download_url"])
        if asset_url.hostname != "github.com" or urllib.parse.unquote(asset_url.path) != expected_path:
            raise UpdateError("An asset does not belong to the offered release.")
    archive = selected[wanted[0]]
    digest = archive.get("digest", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest) or type(archive.get("size")) is not int or not 0 < archive["size"] <= MAX_ZIP:
        raise UpdateError("The release has no valid size and SHA-256 digest.")
    return dict(version=version, notes=str(data.get("body") or "")[:6000], size=archive["size"],
                zip_url=archive["browser_download_url"], sums_url=selected["SHA256SUMS"]["browser_download_url"],
                sig_url=selected["SHA256SUMS.sig"]["browser_download_url"], digest=digest[7:])


def check_release(root, channel=None):
    channel = (channel or configured_channel()).validate()
    current = version_key(local_version(root))
    if current is None:
        return None
    url = f"https://api.github.com/repos/{channel.repository}/releases/latest"
    with _open(url, channel, "api") as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise UpdateError("The release response is too large.")
    release = parse_release(json.loads(raw), channel)
    return release if version_key(release["version"]) > current else None


# RFC 8032 Ed25519 verification, strict encodings and prime-order points. Verification
# uses public data only; signing/private-key handling is deliberately outside this app.
_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)
_IDENTITY = (0, 1)


def _point(raw):
    if len(raw) != 32:
        raise ValueError("point length")
    encoded = int.from_bytes(raw, "little")
    y, sign = encoded & ((1 << 255) - 1), encoded >> 255
    if y >= _P:
        raise ValueError("noncanonical point")
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    x = pow(x2, (_P + 3) // 8, _P)
    if x * x % _P != x2:
        x = x * _I % _P
    if x * x % _P != x2 or (x == 0 and sign):
        raise ValueError("invalid point")
    return (_P - x if (x & 1) != sign else x), y


def _add(p, q):
    x, y = p
    u, v = q
    z = _D * x * u * y * v % _P
    return ((x * v + u * y) * pow(1 + z, _P - 2, _P) % _P,
            (y * v + x * u) * pow(1 - z, _P - 2, _P) % _P)


def _mul(point, scalar):
    result = _IDENTITY
    while scalar:
        if scalar & 1:
            result = _add(result, point)
        point = _add(point, point)
        scalar >>= 1
    return result


def verify_ed25519(public, message, signature):
    try:
        if len(public) != 32 or len(signature) != 64:
            return False
        a, r = _point(public), _point(signature[:32])
        s = int.from_bytes(signature[32:], "little")
        if s >= _L or a == _IDENTITY or r == _IDENTITY or _mul(a, _L) != _IDENTITY or _mul(r, _L) != _IDENTITY:
            return False
        base = _point(bytes.fromhex("58" + "66" * 31))
        challenge = int.from_bytes(hashlib.sha512(signature[:32] + public + message).digest(), "little") % _L
        return _mul(base, s) == _add(r, _mul(a, challenge))
    except (ValueError, TypeError):
        return False


def signature_message(channel, version, sums):
    return b"OpenRecomp-FGC release signature v1\n" + channel.encode("ascii") + b"\n" + version.encode("ascii") + b"\n" + sums


def verify_signature(raw, sums, release, channel):
    try:
        envelope = json.loads(raw)
        if (envelope.get("algorithm") != "ed25519" or envelope.get("channel") != channel.name
                or envelope.get("version") != release["version"]):
            raise ValueError("wrong signature context")
        signature = bytes.fromhex(envelope["signature"])
        for public_hex in channel.public_keys:
            public = bytes.fromhex(public_hex)
            if (envelope.get("key_id") == hashlib.sha256(public).hexdigest()[:16]
                    and verify_ed25519(public, signature_message(channel.name, release["version"], sums), signature)):
                return
    except (ValueError, TypeError, KeyError, AttributeError):
        pass
    raise UpdateError("The update is not signed by this project's release key.")


def _manifest(root, release, channel):
    info = _json(Path(root) / "release.json")
    if info.get("project") != PROJECT or info.get("channel") != channel.name or info.get("version") != release["version"]:
        raise UpdateError("The archive belongs to another project, channel or version.")
    if any(not (Path(root) / item).is_file() for item in REQUIRED_ITEMS):
        raise UpdateError("The update is missing required launcher files.")


def _archive_members(archive, version):
    members, seen, total = [], set(), 0
    expected = "OpenRecomp-" + version
    for info in archive.infolist():
        name = info.filename
        path = PurePosixPath(name)
        parts = path.parts
        raw_parts = name.rstrip("/").split("/")
        if (not name or info.orig_filename != name or "\\" in name or path.is_absolute() or len(parts) < 1 or parts[0] != expected
                or any(p in (".", "..") or p.endswith((".", " ")) or re.search(r'[<>:"|?*\x00-\x1f]', p)
                       or p.split(".")[0].upper() in _DEVICES for p in parts)
                or any(p in ("", ".", "..") for p in raw_parts)):
            raise UpdateError("The archive has an unsafe path.")
        if len(parts) == 1:
            if not info.is_dir():
                raise UpdateError("The archive has no program folder.")
            continue
        if parts[1] not in PROGRAM_ITEMS:
            raise UpdateError("The archive contains files outside the launcher program.")
        mode = info.external_attr >> 16
        if (stat.S_ISLNK(mode) or info.external_attr & 0x400
                or (stat.S_IFMT(mode) and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)))):
            raise UpdateError("The archive contains a link or special file.")
        folded = "/".join(parts).casefold()
        if folded in seen or info.flag_bits & 1:
            raise UpdateError("The archive has duplicate or encrypted entries.")
        seen.add(folded)
        total += info.file_size
        if len(seen) > 100000 or total > MAX_UNPACKED or info.file_size > MAX_ZIP:
            raise UpdateError("The unpacked update is too large.")
        members.append((info, parts[1:]))
    return members


def _work_root(root):
    root = Path(root).resolve()
    work = root.with_name(root.name + ".update")
    if work.is_symlink() or work.is_junction():
        raise UpdateError("The update workspace must not be a link.")
    return work


def _check_user_home(root):
    home = os.environ.get("OPENRECOMP_HOME") or os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "OpenRecomp")
    home = Path(os.path.expandvars(os.path.expanduser(home))).resolve()
    targets = [(Path(root).resolve() / item).resolve() for item in PROGRAM_ITEMS]
    targets.append(_work_root(root).resolve())
    for target in targets:
        if home == target or target in home.parents or home in target.parents:
            raise UpdateError("The player data folder overlaps program files or the update workspace; move player data before updating.")


def _require_upgrade(root, release):
    current, offered = version_key(local_version(root)), version_key(release.get("version"))
    if current is None or offered is None or offered <= current:
        raise UpdateError("The offered update is no longer newer than this installation.")


def _signed_checksum(sums, release):
    filename = f"OpenRecomp-{release['version']}.zip"
    expected = None
    for line in sums.decode("ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([^/\\]+)", line)
        if not match:
            raise UpdateError("Malformed SHA256SUMS.")
        if match[2] == filename:
            if expected is not None:
                raise UpdateError("Duplicate archive checksum.")
            expected = match[1]
    if expected is None:
        raise UpdateError("The signed archive checksum is missing.")
    return expected


def _proof_bytes(path, limit):
    with Path(path).open("rb") as source:
        raw = source.read(limit + 1)
    if len(raw) > limit:
        raise UpdateError("The retained update proof exceeds its allowed size.")
    return raw


def _verify_staged(staged, release, channel):
    """Authenticate retained release bytes and every staged file before executing or moving them."""
    staged = Path(staged)
    transaction = staged.parent
    sums = _proof_bytes(transaction / "SHA256SUMS", 65536)
    verify_signature(_proof_bytes(transaction / "SHA256SUMS.sig", 4096), sums, release, channel)
    expected = _signed_checksum(sums, release)
    archive_path = transaction / "release.zip"
    expected_files, expected_dirs = {}, set()
    with archive_path.open("rb") as source:
        if os.fstat(source.fileno()).st_size > MAX_ZIP:
            raise UpdateError("The retained update archive exceeds its allowed size.")
        if hashlib.file_digest(source, "sha256").hexdigest() != expected:
            raise UpdateError("The retained update archive failed authentication.")
        source.seek(0)
        with zipfile.ZipFile(source) as archive:
            for info, parts in _archive_members(archive, release["version"]):
                expected_dirs.update("/".join(parts[:n]) for n in range(1, len(parts)))
                name = "/".join(parts)
                if info.is_dir():
                    expected_dirs.add(name)
                else:
                    with archive.open(info) as original:
                        expected_files[name] = (info.file_size, hashlib.file_digest(original, "sha256").digest())
    actual, actual_dirs = {}, set()
    if staged.is_symlink() or staged.is_junction():
        raise UpdateError("The staged program contains a link.")
    for current, dirs, files in os.walk(staged, followlinks=False):
        for name in dirs + files:
            path = Path(current) / name
            if path.is_symlink() or path.is_junction():
                raise UpdateError("The staged program contains a link.")
        actual_dirs.update((Path(current) / name).relative_to(staged).as_posix() for name in dirs)
        for name in files:
            path = Path(current) / name
            if not stat.S_ISREG(path.stat().st_mode):
                raise UpdateError("The staged program contains a special file.")
            actual[path.relative_to(staged).as_posix()] = path
    if set(actual) != set(expected_files) or actual_dirs != expected_dirs:
        raise UpdateError("The staged program differs from the signed archive.")
    for name, (size, digest) in expected_files.items():
        if actual[name].stat().st_size != size:
            raise UpdateError("A staged file differs from the signed archive.")
        with actual[name].open("rb") as target:
            if hashlib.file_digest(target, "sha256").digest() != digest:
                raise UpdateError("A staged file differs from the signed archive.")
    _manifest(staged, release, channel)


def stage_update(root, release, channel=None):
    channel = (channel or configured_channel()).validate()
    _check_user_home(root)
    if not version_key(release.get("version")):
        raise UpdateError("Invalid release version.")
    work = _work_root(root)
    work.mkdir(exist_ok=True)
    transaction = work / secrets.token_hex(12)
    transaction.mkdir()
    try:
        sums = _download(release["sums_url"], channel, 65536)
        signature = _download(release["sig_url"], channel, 4096)
        verify_signature(signature, sums, release, channel)
        expected = _signed_checksum(sums, release)
        if expected != release["digest"]:
            raise UpdateError("Signed checksum and GitHub digest disagree.")
        archive_path = transaction / "release.zip"
        count = _download(release["zip_url"], channel, min(MAX_ZIP, release["size"]), archive_path)
        with open(archive_path, "rb") as downloaded:
            digest = hashlib.file_digest(downloaded, "sha256").hexdigest()
        if count != release["size"] or digest != expected:
            raise UpdateError("The update archive failed its size or SHA-256 check.")
        staged = transaction / "new"
        staged.mkdir()
        with zipfile.ZipFile(archive_path) as archive:
            for info, parts in _archive_members(archive, release["version"]):
                target = staged.joinpath(*parts)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, open(target, "xb") as output:
                        shutil.copyfileobj(source, output)
        _manifest(staged, release, channel)
        (transaction / "SHA256SUMS").write_bytes(sums)
        (transaction / "SHA256SUMS.sig").write_bytes(signature)
        (transaction / "verified.json").write_text(json.dumps(dict(version=release["version"], channel=channel.name)), encoding="utf-8")
        return staged
    except Exception:
        shutil.rmtree(transaction)
        raise


def prepare_update(root, staged, channel=None):
    """Authenticate the stage and copy the helper runtime on the update worker."""
    channel = (channel or configured_channel()).validate()
    root, staged = Path(root).resolve(), Path(staged).resolve()
    _check_user_home(root)
    if staged.name != "new" or staged.parent.parent != _work_root(root) or not staged.is_dir():
        raise UpdateError("The update was not staged beside this installation.")
    release = _json(staged.parent / "verified.json")
    _verify_staged(staged, release, channel)
    runner = staged.parent / "runner"
    shutil.copytree(root / "python", runner / "python")
    shutil.copy2(__file__, runner / "updater.py")
    token = secrets.token_hex(32)
    plan = dict(root=str(root), staged=str(staged), pid=os.getpid(), version=release["version"], channel=channel.name, token=token)
    plan_path = staged.parent / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    return plan_path


def launch_update(root, prepared, channel=None):
    """Start the prepared helper after the UI thread's final busy check."""
    channel = (channel or configured_channel()).validate()
    root = Path(root).resolve()
    plan_path, _plan, plan_root, _staged, transaction = _validated_plan(prepared, channel)
    if plan_root != root or plan_path.name != "plan.json":
        raise UpdateError("The update helper was prepared for another installation.")
    _check_user_home(root)
    runner = transaction / "runner"
    flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0
    return subprocess.Popen([str(runner / "python" / "pythonw.exe"), "-I", "-B", str(runner / "updater.py"), "--apply", str(plan_path)],
                            cwd=runner, creationflags=flags, close_fds=True)


def _pid_alive(pid):
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def _install_processes(root):
    """Check visible Windows processes; locked program files also make the swap roll back."""
    if os.name != "nt":
        return []
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    pids = (ctypes.c_ulong * 65536)()
    size = ctypes.c_ulong()
    if not psapi.EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(size)) or size.value == ctypes.sizeof(pids):
        raise UpdateError("Cannot inspect running program files.")
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
    found = []
    root = str(Path(root).resolve()).casefold() + os.sep
    for pid in pids[:size.value // ctypes.sizeof(ctypes.c_ulong)]:
        if pid in (0, os.getpid()):
            continue
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            continue  # Protected OS processes cannot be files from a user-writable install.
        try:
            buffer, count = ctypes.create_unicode_buffer(32768), ctypes.c_ulong(32768)
            if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(count)):
                raise UpdateError("Cannot inspect a running program file.")
            if buffer.value.casefold().startswith(root):
                found.append(pid)
        finally:
            kernel.CloseHandle(handle)
    return found


def _restart(root, marker=None):
    env = dict(os.environ)
    env.pop(CONFIRM_ENV, None)
    if marker:
        env[CONFIRM_ENV] = json.dumps(marker)
    return subprocess.Popen([str(Path(root) / "python" / "pythonw.exe"), "-I", "-B",
                             str(Path(root) / "openrecomp_boot.py")], cwd=root, env=env, close_fds=True)


def _validated_plan(plan_path, channel=None):
    plan_path = Path(plan_path).resolve()
    plan = _json(plan_path)
    root, staged = Path(plan["root"]).resolve(), Path(plan["staged"]).resolve()
    transaction = plan_path.parent
    if (transaction.parent != _work_root(root) or staged != transaction / "new"
            or not version_key(plan.get("version")) or plan.get("channel") != (channel or configured_channel()).name
            or not re.fullmatch(r"[0-9a-f]{64}", plan.get("token", ""))):
        raise UpdateError("Invalid update transaction.")
    return plan_path, plan, root, staged, transaction


def apply_plan(plan_path, *, wait=CONFIRM_WAIT, alive=_pid_alive, processes=_install_processes, restart=_restart, move=os.replace, sleep=time.sleep):
    """Serialize helpers before any swap, including the complete rollback on failure."""
    plan_path, _plan, _root, _staged, transaction = _validated_plan(plan_path)
    lock = transaction.parent / "apply.lock"
    try:
        lock.mkdir()
    except FileExistsError:
        raise UpdateError("Another update or an interrupted recovery owns this installation.") from None
    release_lock = False
    try:
        result = _apply_plan(plan_path, wait=wait, alive=alive, processes=processes,
                             restart=restart, move=move, sleep=sleep)
        release_lock = True
        return result
    except Exception as error:
        release_lock = getattr(error, "safe_to_unlock", False)
        raise
    finally:
        if release_lock:
            lock.rmdir()


def _apply_plan(plan_path, *, wait, alive, processes, restart, move, sleep):
    """Run only in the copied helper. Every failed move/start/confirmation restores the old files."""
    plan_path, plan, root, staged, transaction = _validated_plan(plan_path)
    backup = transaction / "backup"
    try:
        _check_user_home(root)
        _manifest(staged, plan, configured_channel())
        end = time.monotonic() + wait
        while alive(plan["pid"]) or processes(root):
            if time.monotonic() >= end:
                raise UpdateError("The launcher installation is still in use.")
            sleep(0.1)
        _require_upgrade(root, plan)
        _verify_staged(staged, plan, configured_channel())
        if processes(root):
            raise UpdateError("The launcher installation became busy during update verification.")
        backup.mkdir()
    except Exception as failure:
        (transaction / "result.json").write_text(json.dumps(dict(status="unchanged", version=plan["version"])), encoding="utf-8")
        if not alive(plan["pid"]):
            restart(root)
        raise UpdateError("The update could not start; the previous launcher is unchanged.", safe_to_unlock=True) from failure
    old, new = [], []
    marker = transaction / "confirmed.json"
    proc = None
    try:
        for item in PROGRAM_ITEMS:
            if (root / item).exists():
                move(root / item, backup / item)
                old.append(item)
        for item in PROGRAM_ITEMS:
            if (staged / item).exists():
                move(staged / item, root / item)
                new.append(item)
        _manifest(root, plan, configured_channel())
        proc = restart(root, dict(path=str(marker), token=plan["token"]))
        end = time.monotonic() + wait
        while time.monotonic() < end:
            if marker.exists() and _json(marker).get("token") == plan["token"]:
                (transaction / "result.json").write_text(json.dumps(dict(status="updated", version=plan["version"])), encoding="utf-8")
                return True
            if proc.poll() is not None:
                break
            sleep(0.1)
        raise UpdateError("The new launcher did not confirm a healthy start.")
    except Exception as failure:
        problems = []
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=15)
            except Exception as error:
                problems.append(error)
        # Keep a backup on any restoration failure; never destroy the only old copy.
        for item in reversed(new):
            try:
                move(root / item, staged / item)
            except OSError as error:
                problems.append(error)
        for item in reversed(old):
            try:
                move(backup / item, root / item)
            except OSError as error:
                problems.append(error)
        status = "recovery_required" if problems else "rolled_back"
        (transaction / "result.json").write_text(json.dumps(dict(status=status, version=plan["version"])), encoding="utf-8")
        if problems:
            raise UpdateError("The update failed. Recovery copies were kept beside the installation; close programs using it before restoring the backup.") from failure
        restart(root)
        raise UpdateError("The update failed and the previous launcher was restored.", safe_to_unlock=True) from failure


def confirm_startup(root):
    raw = os.environ.get(CONFIRM_ENV)
    if not raw:
        return False
    try:
        value = json.loads(raw)
        marker = Path(value["path"]).resolve()
        if marker.name != "confirmed.json" or marker.parent.parent != _work_root(root) or not re.fullmatch(r"[0-9a-f]{64}", value["token"]):
            return False
        marker.write_text(json.dumps(dict(token=value["token"])), encoding="utf-8")
        os.environ.pop(CONFIRM_ENV, None)
        return True
    except (OSError, ValueError, KeyError, TypeError, UpdateError):
        return False


def update_result(root):
    """Consume the last helper result once; contains status/version, never player paths."""
    try:
        work = _work_root(root)
        if not work.is_dir():
            return None
        transactions = list(work.iterdir())
    except (OSError, UpdateError):
        return None
    candidates = []
    for transaction in transactions:
        try:
            if transaction.is_symlink() or transaction.is_junction() or not transaction.is_dir():
                continue
            result = transaction / "result.json"
            if result.is_symlink() or result.is_junction():
                continue
            candidates.append((result.stat().st_mtime, result))
        except OSError:
            continue
    for _modified, result in sorted(candidates, reverse=True):
        try:
            value = _json(result)
            if not isinstance(value, dict):
                continue
            result.unlink()
        except (OSError, ValueError):
            continue
        if value.get("status") in ("updated", "rolled_back", "recovery_required", "unchanged"):
            return value
    return None


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--apply":
        try:
            apply_plan(sys.argv[2])
        except Exception:
            sys.exit(1)
    else:
        sys.exit(2)
