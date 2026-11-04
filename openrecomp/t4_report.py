"""Bounded, text-only T4 diagnostics. No game tools are imported or run to make a report."""
import ipaddress
import json
import os
import platform
import re
import stat
import uuid
import zipfile
from pathlib import Path

SEND_TARGET = 7900 * 1024
FILE_CAP = 512 * 1024
TOTAL_CAP = 6 * 1024 * 1024
PRIVATE_KEY = re.compile(
    r"(?i)(token|password|passwd|secret|authorization|cookie|email|contact|username|"
    r"computer[_-]?name|host[_-]?name|user[_-]?name|player[_-]?name|account[_-]?name|"
    r"session[_-]?key|api[_-]?key|recovery|(?:^|_)name$)")


class Cleaner:
    def __init__(self, roots=(), private=()):
        values = list(private) + list(roots)
        values += [os.environ.get(k, "") for k in
                   ("USERNAME", "USER", "COMPUTERNAME", "USERPROFILE", "HOME")]
        values += [platform.node()]
        self.values = sorted({str(v) for v in values if v}, key=len, reverse=True)

    def text(self, text):
        # Both ordinary log paths and JSON-escaped Windows paths occur in diagnostics.
        for value in self.values:
            for spelling in {value, value.replace("\\", "/"), value.replace("\\", "\\\\")}:
                pattern = re.escape(spelling)
                if len(spelling) < 3:
                    pattern = r"(?<!\w)" + pattern + r"(?!\w)"
                text = re.sub(pattern, "[private]", text, flags=re.I)
        text = re.sub(r"(?i)(?:\b[a-z]:[\\/]+(?:users|documents and settings)[\\/]+|/(?:home|Users)/)"
                      r"[^\\/\r\n\"'<>]+", "[profile]", text)
        text = re.sub(r"\\\\[^\s\\/]+", "[computer]", text)
        text = re.sub(r"[\w.+%-]+@[\w.-]+\.[a-zA-Z]{2,}", "[email]", text)
        text = re.sub(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9_./+=-]+", r"\1 [secret]", text)
        text = re.sub(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@", r"\1[secret]@", text)
        text = re.sub(
            r"(?i)([\"']?[\w.-]*(?:token|password|passwd|secret|authorization|cookie|api[_-]?key|"
            r"session[_-]?key|user[_-]?name|computer[_-]?name|host[_-]?name|player[_-]?name|account[_-]?name|"
            r"email)[\w.-]*[\"']?\s*[:=]\s*)"
            r"(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;&}\r\n]+)", r'\1"[private]"', text)

        def ipv6(match):
            value = match.group()
            try:
                ipaddress.IPv6Address(value.split("%", 1)[0])
            except ValueError:
                return value
            return "[ip]"

        text = re.sub(r"(?<![\w:])[0-9a-fA-F:]*:[0-9a-fA-F:.]+(?:%[\w.-]+)?", ipv6, text)
        text = re.sub(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])", "[ip]", text)
        return text

    def document(self, value):
        if isinstance(value, dict):
            return {self.text(str(k)): "[private]" if PRIVATE_KEY.search(str(k)) else self.document(v)
                    for k, v in value.items()}
        if isinstance(value, list):
            return [self.document(v) for v in value]
        return self.text(value) if isinstance(value, str) else value


def _plain(base, path):
    """Reject symlinks, junctions and escapes at every component, including the diagnostic directory itself."""
    base, path = Path(os.path.abspath(base)), Path(os.path.abspath(path))
    try:
        relative = path.relative_to(base)
        for part in (base, *(base / Path(*relative.parts[:i]) for i in range(1, len(relative.parts) + 1))):
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                return False
        return path.is_file()
    except (OSError, ValueError):
        return False


def _read(base, path, cap=FILE_CAP):
    if not _plain(base, path):
        return None
    try:
        with open(path, "rb") as stream:
            size = os.fstat(stream.fileno()).st_size
            if size > cap:
                stream.seek(size - cap)
            data = stream.read(cap)
            if size > cap:
                data = data.partition(b"\n")[2]   # never include a fragment of a private first line
        # Diagnostics are text; a disguised binary file is not a report input.
        if b"\0" in data:
            return None
        return data.decode("utf-8-sig", "replace")
    except OSError:
        return None


def _group(name):
    name = name.lower()
    if re.fullmatch(r"(?:build|compile)[\w.-]*\.log", name):
        return "compile"
    if re.fullmatch(r"(?:net|rb)[\w.-]*\.log", name) or name == "preflight.json":
        return "online"
    if name in ("stdout.txt", "stderr.txt") or re.fullmatch(r"(?:game|tekken4|t4)[\w.-]*\.log", name):
        return "logs"
    return None


def _candidates(root):
    """Only logs/ and its immediate run directories. Never walk a game/build/source tree."""
    folder = Path(root) / "logs"
    try:
        if folder.is_symlink() or getattr(folder.lstat(), "st_file_attributes", 0) & 0x400:
            return []
        out = []
        with os.scandir(folder) as entries:
            for index, entry in enumerate(entries):
                if index >= 1000:
                    break
                if entry.is_file(follow_symlinks=False):
                    out.append(Path(entry.path))
                elif entry.is_dir(follow_symlinks=False) and not getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0) & 0x400:
                    with os.scandir(entry.path) as children:
                        for n, child in enumerate(children):
                            if n >= 100:
                                break
                            if child.is_file(follow_symlinks=False):
                                out.append(Path(child.path))
        return out
    except OSError:
        return []


def build(root, home, dest, note="", private=(), build_lines=(), save_dir=None, version="dev"):
    """Write a cleaned report; filenames in the archive never contain original paths or player names."""
    cleaner = Cleaner((str(root), str(home)), private)
    members = {
        "report.txt": cleaner.text("Tekken 4 Online\nVersion: " + version + "\n" + note),
        "system.txt": cleaner.text("\n".join(("OS: " + platform.system() + " " + platform.release(),
                                            "Machine: " + platform.machine(), "Python: " + platform.python_version(),
                                            "CPU count: " + str(os.cpu_count())))),
    }
    paths = _candidates(root)
    for name in ("build.log", "build_game.log", "build/build.log", "build/compile.log"):
        paths.append(Path(root) / name)
    if save_dir:
        paths += [Path(save_dir) / name for name in ("net.log", "rb_frames.log", "stdout.txt", "stderr.txt")]
    groups = {"logs": [], "online": [], "compile": []}
    for path in paths:
        group = _group(path.name)
        base = save_dir if save_dir and path.parent == Path(save_dir) else root
        if group and _plain(base, path):
            try:
                groups[group].append((path.stat().st_mtime_ns, str(path), base, path))
            except OSError:
                pass
    for group, rows in groups.items():
        remaining = (4 * 1024 * 1024) // len(groups)
        for index, (_stamp, _sort, base, path) in enumerate(sorted(rows, reverse=True)[:8], 1):
            text = _read(base, path, min(FILE_CAP, remaining)) if remaining else None
            if text is None:
                continue
            if path.suffix == ".json":
                try:
                    text = json.dumps(cleaner.document(json.loads(text)), ensure_ascii=False, indent=2)
                except ValueError:
                    continue
            else:
                text = cleaner.text(text)
            data = text.encode("utf-8")[:remaining]
            remaining -= len(data)
            members[f"{group}/{group}-{index:02d}{path.suffix}"] = data
    # Fixed launcher paths only; never include the launcher's config or account/session stores.
    for index, (base, path) in enumerate(((home, Path(home) / "launcher.log"),
                                          (home, Path(home) / "openrecomp.log"),
                                          (root, Path(root) / "launcher.log")), 1):
        text = _read(base, path)
        if text is not None:
            members[f"logs/launcher-{index}.log"] = cleaner.text(text)
    if build_lines:
        members["compile/launcher-build.log"] = cleaner.text("\n".join(build_lines)[-FILE_CAP:])
    members["build_identity.json"] = json.dumps({"available": False})
    identities = [Path(root) / "build_identity.json"] + [p for p in paths if p.name == "build_identity.json"]
    identities = [p for p in identities if _plain(root, p)]
    identities.sort(key=lambda p: p.stat().st_mtime_ns, reverse=True)
    for path in identities:
        text = _read(root, path, 32768)
        try:
            identity = json.loads(text) if text is not None else None
        except ValueError:
            continue
        if isinstance(identity, dict):
            members["build_identity.json"] = json.dumps(cleaner.document(identity), indent=2, ensure_ascii=False)
            break
    remaining = TOTAL_CAP
    for name, data in members.items():
        data = data.encode("utf-8") if isinstance(data, str) else data
        members[name] = data[:min(FILE_CAP, remaining)]
        remaining -= len(members[name])
    members["contents.txt"] = "Tekken 4 cleaned diagnostic report\n" + "\n".join(members) + "\n"
    Path(dest).mkdir(parents=True, exist_ok=True)
    path = Path(dest) / ("T4-report-" + uuid.uuid4().hex[:12] + ".zip")
    try:
        # Stored text keeps both packed size and expansion ratio within the server's limits.
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, data in members.items():
                archive.writestr(name, data)
        if path.stat().st_size > SEND_TARGET:
            raise ValueError("report_size")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return str(path)
