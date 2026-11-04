"""Verified official installers for PCs without a working Windows Package Manager.

No installer is executed until the complete missing-tool batch has been downloaded
and verified. One elevated worker copies it into an administrator-owned directory,
verifies the copies again, and runs the fixed silent commands.
"""
import base64
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile
import threading
from urllib import request, parse
import uuid

from .base import NO_WINDOW

VS_URL = "https://aka.ms/vs/17/release/vs_BuildTools.exe"
SPECS = {
    "vs2022": dict(filename="vs_BuildTools.exe", url=VS_URL, signer=["Microsoft Corporation"],
                   args=["--quiet", "--wait", "--norestart", "--add",
                         "Microsoft.VisualStudio.Workload.VCTools", "--includeRecommended"]),
    "git": dict(repo="git-for-windows/git", asset=r"Git-[\d.]+-64-bit\.exe",
                signer=["Open Source Developer, Johannes Schindelin", "Johannes Schindelin"],
                args=["/VERYSILENT", "/NORESTART", "/SUPPRESSMSGBOXES", "/SP-"]),
    "cmake": dict(repo="Kitware/CMake", asset=r"cmake-[\d.]+-windows-x86_64\.msi",
                  signer=["Kitware, Inc.", "Kitware Inc.", "Kitware Inc"],
                  args=["/qn", "/norestart", "ALLUSERS=1", "ADD_CMAKE_TO_PATH=System"]),
    "ninja": dict(repo="ninja-build/ninja", asset=r"ninja-win\.zip", signer=[], args=[]),
}
HOSTS = {"aka.ms", "download.visualstudio.microsoft.com", "github.com", "api.github.com",
         "release-assets.githubusercontent.com", "objects.githubusercontent.com"}


def _https(url):
    parts = parse.urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in HOSTS or parts.username or parts.password:
        raise RuntimeError("@t4.tools.download_failed")
    return url


class _Redirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, _https(newurl))


def download(url, path, limit=256 * 1024 * 1024):
    """HTTPS only, including redirects; bounded disk use and no partially trusted cache."""
    opener = request.build_opener(_Redirect())
    req = request.Request(_https(url), headers={"User-Agent": "OpenRecomp-build-tools",
                                               "Accept": "application/vnd.github+json"})
    try:
        with opener.open(req, timeout=60) as response, Path(path).open("wb") as output:
            _https(response.geturl())
            size = 0
            while block := response.read(1024 * 1024):
                size += len(block)
                if size > limit:
                    raise ValueError("download too large")
                output.write(block)
    except Exception as error:
        Path(path).unlink(missing_ok=True)
        raise RuntimeError("@t4.tools.download_failed") from error


def _sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _powershell(script):
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    # An absolute system executable prevents PATH substitution before elevation.
    if os.name == "nt":
        buffer = ctypes.create_unicode_buffer(32768)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        if not kernel.GetSystemDirectoryW(buffer, len(buffer)):
            raise ctypes.WinError(ctypes.get_last_error())
        executable = Path(buffer.value) / "WindowsPowerShell/v1.0/powershell.exe"
    else:
        executable = Path("C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
    return [str(executable), "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]


def _trust(path):
    """WinVerifyTrust's generic Authenticode policy, with no UI and state cleanup."""
    class GUID(ctypes.Structure):
        _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD),
                    ("d", ctypes.c_ubyte * 8)]

    class FILE(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("path", wintypes.LPCWSTR),
                    ("handle", wintypes.HANDLE), ("subject", ctypes.c_void_p)]

    class DATA(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("policy", ctypes.c_void_p), ("sip", ctypes.c_void_p),
                    ("ui", wintypes.DWORD), ("revocation", wintypes.DWORD), ("choice", wintypes.DWORD),
                    ("file", ctypes.POINTER(FILE)), ("action", wintypes.DWORD), ("state", wintypes.HANDLE),
                    ("url", wintypes.LPCWSTR), ("flags", wintypes.DWORD), ("context", wintypes.DWORD)]

    policy = GUID.from_buffer_copy(uuid.UUID("00aac56b-cd44-11d0-8cc2-00c04fc295ee").bytes_le)
    file = FILE(ctypes.sizeof(FILE), str(Path(path).resolve()), None, None)
    data = DATA()
    data.size, data.ui, data.choice, data.file, data.action = ctypes.sizeof(DATA), 2, 1, ctypes.pointer(file), 1
    wintrust = ctypes.WinDLL("wintrust", use_last_error=True).WinVerifyTrust
    wintrust.argtypes = [wintypes.HWND, ctypes.POINTER(GUID), ctypes.POINTER(DATA)]
    wintrust.restype = ctypes.c_long
    try:
        return wintrust(None, ctypes.byref(policy), ctypes.byref(data)) == 0
    finally:
        data.action = 2
        wintrust(None, ctypes.byref(policy), ctypes.byref(data))


def verify(path, signers, digest="", run=None):
    """A digest is pinned to the selected release asset before its bytes are fetched.

    Signed installers additionally require Windows trust and the vendor's exact
    certificate name. Ninja has no publisher signature and requires an API digest.
    """
    try:
        actual = _sha256(path)
        if digest and actual != digest:
            raise ValueError("checksum")
        if signers:
            if os.name != "nt" or not _trust(path):
                raise ValueError("trust")
            literal = str(Path(path).resolve()).replace("'", "''")
            AUTHENTICODE_SCRIPT = (f"$s=Get-AuthenticodeSignature -LiteralPath '{literal}'; "
                      "if ($s.Status -ne 'Valid') {exit 1}; "
                      "$s.SignerCertificate.GetNameInfo([System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName,$false)")
            result = (run or subprocess.run)(_powershell(AUTHENTICODE_SCRIPT), stdin=subprocess.DEVNULL,
                                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                             creationflags=NO_WINDOW, check=False)
            name = result.stdout.decode("utf-8", errors="replace").strip() if isinstance(result.stdout, bytes) else result.stdout.strip()
            if result.returncode or name not in signers or _sha256(path) != actual:
                raise ValueError("publisher")
        elif not digest:
            raise ValueError("no checksum")
        return actual
    except Exception as error:
        raise RuntimeError("@t4.tools.verification_failed") from error


def _resolve(tool, folder, fetch):
    spec = dict(SPECS[tool], id=tool)
    if "repo" in spec:
        metadata = folder / (tool + "-release.json")
        fetch("https://api.github.com/repos/" + spec["repo"] + "/releases/latest", metadata)
        try:
            release = json.loads(metadata.read_text(encoding="utf-8"))
            asset = next(a for a in release["assets"] if re.fullmatch(spec["asset"], a["name"]))
            # Asset names and repository paths are checked independently of the API response.
            prefix = "https://github.com/" + spec["repo"] + "/releases/download/"
            if not asset["browser_download_url"].startswith(prefix):
                raise ValueError("release URL")
            spec.update(filename=asset["name"], url=asset["browser_download_url"])
            digest = asset.get("digest") or ""
            spec["digest"] = digest[7:] if re.fullmatch(r"sha256:[0-9a-f]{64}", digest) else ""
            if not spec["signer"] and not spec["digest"]:
                raise RuntimeError("@t4.tools.verification_failed")
        except RuntimeError:
            raise
        except (ValueError, KeyError, StopIteration, TypeError) as error:
            raise RuntimeError("@t4.tools.download_failed") from error
    return spec


# The manifest is embedded in the elevated command, not read from a writable file.
# Only administrator-owned copies are ever executed. The ZIP contains no paths we
# execute: only its exact, top-level ninja.exe entry is extracted.
WORKER = r"""
$ErrorActionPreference='Stop'
$out=__RESULT__
$cancel=__CANCEL__
$jobs=ConvertFrom-Json __MANIFEST__
$programFiles=[Environment]::GetFolderPath('ProgramFiles')
$secure=Join-Path $programFiles ('OpenRecomp-Setup-'+[guid]::NewGuid().ToString('N'))
$states=@()
$failure='@t4.tools.verification_failed'
try {
 New-Item -ItemType Directory -Path $secure -Force | Out-Null
 $acl=New-Object Security.AccessControl.DirectorySecurity
 $acl.SetAccessRuleProtection($true,$false)
 foreach($sid in @('S-1-5-32-544','S-1-5-18')) {
  $identity=New-Object Security.Principal.SecurityIdentifier($sid)
  $rule=New-Object Security.AccessControl.FileSystemAccessRule($identity,'FullControl','ContainerInherit,ObjectInherit','None','Allow')
  $acl.AddAccessRule($rule)
 }
 $acl.SetOwner((New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')))
 Set-Acl -LiteralPath $secure -AclObject $acl
 foreach($job in $jobs) {
  if(Test-Path -LiteralPath $cancel) {break}
  $failure='@t4.tools.verification_failed'
  $target=Join-Path $secure $job.filename
  Copy-Item -LiteralPath $job.path -Destination $target
  if((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -ne $job.sha256) {throw 'checksum'}
  if($job.signer.Count -gt 0) {
   $sig=Get-AuthenticodeSignature -LiteralPath $target
   $name=$sig.SignerCertificate.GetNameInfo([System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName,$false)
   if($sig.Status -ne 'Valid' -or $name -notin $job.signer) {throw 'publisher'}
  }
  @{index=$states.Count;states=@($states);running=$true}|ConvertTo-Json -Compress|Set-Content -LiteralPath $out -Encoding UTF8
  $failure='@t4.tools.install_failed'
  if($job.id -eq 'ninja') {
   Add-Type -AssemblyName System.IO.Compression.FileSystem
   $zip=[IO.Compression.ZipFile]::OpenRead($target)
   try {
    $entry=$zip.GetEntry('ninja.exe')
    if($null -eq $entry) {throw 'ninja missing'}
    $dest=Join-Path $programFiles ('OpenRecomp-Ninja-'+[guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $dest -Force|Out-Null
    $destAcl=Get-Acl -LiteralPath $secure
    $users=New-Object Security.Principal.SecurityIdentifier('S-1-5-32-545')
    $read=New-Object Security.AccessControl.FileSystemAccessRule($users,'ReadAndExecute','ContainerInherit,ObjectInherit','None','Allow')
    $destAcl.AddAccessRule($read)
    Set-Acl -LiteralPath $dest -AclObject $destAcl
    [IO.Compression.ZipFileExtensions]::ExtractToFile($entry,(Join-Path $dest 'ninja.exe'),$true)
   } finally {$zip.Dispose()}
   $old=[Environment]::GetEnvironmentVariable('Path','Machine')
   if($dest -notin $old.Split(';')) {[Environment]::SetEnvironmentVariable('Path',($old.TrimEnd(';')+';'+$dest),'Machine')}
   $code=0
  } else {
   if($job.id -eq 'cmake') {
    $exe=Join-Path ([Environment]::SystemDirectory) 'msiexec.exe'
    $arguments=@('/i',('"'+$target+'"'))+@($job.args)
   } else {$exe=$target;$arguments=@($job.args)}
   $process=Start-Process -FilePath $exe -ArgumentList $arguments -Wait -PassThru -WindowStyle Hidden
   $code=$process.ExitCode
  }
  if($code -eq 0) {$states+= 'ok'} elseif($code -in @(3010,1641)) {$states+='reboot'} else {$states+='failed';break}
  if($code -in @(3010,1641)) {break}
 }
 @{index=$states.Count;states=@($states);running=$false}|ConvertTo-Json -Compress|Set-Content -LiteralPath $out -Encoding UTF8
} catch {
 @{index=$states.Count;states=@($states);running=$false;error=$failure}|ConvertTo-Json -Compress|Set-Content -LiteralPath $out -Encoding UTF8
 exit 1
} finally {if(Test-Path -LiteralPath $secure) {Remove-Item -LiteralPath $secure -Recurse -Force}}
"""


def _quote(value):
    return "'" + value.replace("'", "''") + "'"


def _run_elevated(command, **kwargs):
    """ShellExecuteEx supplies one UAC prompt without nesting encoded commands."""
    class EXECUTE(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("mask", wintypes.ULONG), ("window", wintypes.HWND),
                    ("verb", wintypes.LPCWSTR), ("file", wintypes.LPCWSTR), ("parameters", wintypes.LPCWSTR),
                    ("directory", wintypes.LPCWSTR), ("show", ctypes.c_int), ("instance", wintypes.HINSTANCE),
                    ("idlist", ctypes.c_void_p), ("class_name", wintypes.LPCWSTR), ("class_key", wintypes.HKEY),
                    ("hotkey", wintypes.DWORD), ("icon", wintypes.HANDLE), ("process", wintypes.HANDLE)]

    info = EXECUTE()
    info.size, info.mask, info.verb, info.file = ctypes.sizeof(EXECUTE), 0x140, "runas", command[0]
    info.parameters, info.show = subprocess.list2cmdline(command[1:]), 0
    shell = ctypes.WinDLL("shell32", use_last_error=True).ShellExecuteExW
    shell.argtypes, shell.restype = [ctypes.POINTER(EXECUTE)], wintypes.BOOL
    if not shell(ctypes.byref(info)):
        code = ctypes.get_last_error()
        if code == 1223:
            return subprocess.CompletedProcess(command, code)
        raise ctypes.WinError(code)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    try:
        kernel.WaitForSingleObject(info.process, 0xFFFFFFFF)
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(info.process, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return subprocess.CompletedProcess(command, code.value)
    finally:
        kernel.CloseHandle(info.process)


def elevate(jobs, folder, progress, cancelled, run=None):
    result_path = folder / "install-result.json"
    cancel_path = folder / "cancel"
    replacements = dict(RESULT=_quote(str(result_path)), CANCEL=_quote(str(cancel_path)),
                        MANIFEST=_quote(json.dumps(jobs, ensure_ascii=True)))
    script = re.sub(r"__(RESULT|CANCEL|MANIFEST)__", lambda match: replacements[match.group(1)], WORKER)
    command = _powershell(script)
    if len(subprocess.list2cmdline(command)) >= 32760:
        raise RuntimeError("@t4.tools.install_failed")
    outcome = {}

    def work():
        try:
            outcome["result"] = (run or _run_elevated)(command, stdin=subprocess.DEVNULL,
                                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                                       creationflags=NO_WINDOW, check=False)
        except Exception as error:
            outcome["error"] = error

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    last = -1
    while worker.is_alive():
        if cancelled():
            try:
                cancel_path.touch()
            except OSError:
                pass  # Keep monitoring the running installer; never remove its staged files early.
        try:
            state = json.loads(result_path.read_text(encoding="utf-8-sig"))
            index = state.get("index", 0)
            if isinstance(index, int) and index != last and 0 <= index < len(jobs):
                last = index
                progress(index, len(jobs), "@t4.tools." + jobs[index]["id"])
        except (OSError, ValueError):
            pass
        # An in-flight vendor installer must finish; never kill it on navigation.
        worker.join(0.2)
    if outcome.get("error") or outcome["result"].returncode == 1223:
        raise RuntimeError("@t4.tools.elevation_cancelled")
    try:
        state = json.loads(result_path.read_text(encoding="utf-8-sig"))
        if state.get("error"):
            raise RuntimeError(state["error"] if state["error"] in
                               ("@t4.tools.verification_failed", "@t4.tools.install_failed")
                               else "@t4.tools.install_failed")
        statuses = state["states"]
        if not isinstance(statuses, list) or any(s not in ("ok", "reboot", "failed") for s in statuses):
            raise ValueError("result")
        if outcome["result"].returncode or not statuses and not cancel_path.exists():
            raise ValueError("worker failed")
        return statuses + ["cancelled"] * (len(jobs) - len(statuses))
    except (OSError, ValueError, KeyError) as error:
        raise RuntimeError("@t4.tools.install_failed") from error


def install_batch(tool_ids, progress=lambda index, total, name: None, cancelled=lambda: False,
                  directory=None, run=None, *, download=None, verify=None, elevate=None):
    """Install a missing-tool batch with at most one UAC prompt; injectable I/O for tests."""
    if platform.machine().lower() not in ("amd64", "x86_64"):
        raise RuntimeError("@t4.tools.install_unavailable")
    ids = ["vs2022" if tool == "msvc" else tool for tool in tool_ids]
    if any(tool not in SPECS for tool in ids) or len(set(ids)) != len(ids):
        raise RuntimeError("@t4.tools.install_unavailable")
    if not ids:
        return []
    fetch = download or globals()["download"]
    check = verify or globals()["verify"]
    launch = elevate or globals()["elevate"]
    with tempfile.TemporaryDirectory(prefix="openrecomp-tools-", dir=directory) as temporary:
        folder = Path(temporary)
        jobs = []
        for index, tool in enumerate(ids):
            if cancelled():
                return ["cancelled"] * len(ids)
            progress(index, len(ids), "@t4.tools." + tool)
            spec = _resolve(tool, folder, fetch)
            path = folder / spec["filename"]
            fetch(spec["url"], path)
            digest = check(path, spec["signer"], spec.get("digest", ""), run=run)
            jobs.append(dict(id=tool, path=str(path.resolve()), filename=spec["filename"],
                             sha256=digest, signer=spec["signer"], args=spec["args"]))
        if cancelled():
            return ["cancelled"] * len(ids)
        return launch(jobs, folder, progress, cancelled, run=run)
