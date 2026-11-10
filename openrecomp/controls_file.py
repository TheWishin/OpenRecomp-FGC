"""One controls.ini for T5DR: atomic writes that survive a locked file, and the one-time move of OpenRecomp's own copy.

Before 0.1.6.1 OpenRecomp kept its edits in a private controls.json (the same ini text) and passed it to the game as
PS3_CONTROLS, so a binding made in one launcher never reached the other. Now both edit the file T5DR's launcher uses
(controls_edit.controls_path). A private copy that still exists is moved into it once, and backed up first."""
import os
import tempfile
import time

LOCK_ERRORS = (5, 32, 33)      # access denied, sharing violation, lock violation: the game or an antivirus has it


def locked(error):
    return isinstance(error, PermissionError) or getattr(error, "winerror", None) in LOCK_ERRORS


def atomic_write(path, data, seconds=2.0):
    """Write `data` (bytes) to `path` through a temporary file in the same folder. os.replace fails on Windows while
    another program has the target open: retry for `seconds`, then write in place (the game ignores a file it cannot
    parse and reads it again a second later); only fail when even that is refused."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".controls-", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        deadline = time.monotonic() + seconds
        delay = 0.05
        while True:
            try:
                os.replace(temporary, path)
                return
            except OSError as error:
                if not locked(error):
                    raise
                if time.monotonic() >= deadline:
                    break
                time.sleep(delay)
                delay = min(delay * 2, 0.4)
        with open(path, "wb") as stream:
            stream.write(data)
    finally:
        if os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass


def save_with_retry(editor, seconds=2.0):
    """editor.save() (the installed editor's own atomic write and backup), tried again while the file is held."""
    deadline = time.monotonic() + seconds
    delay = 0.05
    while True:
        try:
            editor.save()
            return
        except OSError as error:
            if not locked(error) or time.monotonic() >= deadline:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.4)


def _read(path):
    try:
        with open(path, "rb") as stream:
            return stream.read()
    except OSError:
        return None


def _backup(folder, name, data):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(folder, f"{name}-{stamp}.ini")
    counter = 1
    while os.path.exists(path):
        counter += 1
        path = os.path.join(folder, f"{name}-{stamp}-{counter}.ini")
    atomic_write(path, data)
    return path


def migrate(shared, legacy_paths):
    """Move OpenRecomp's own controls into `shared` once. Returns a list of what was done (log lines, may be empty).

    shared missing: the private copy becomes the file. Both there and different: the one written last wins and the
    other is saved beside the private copy first (controls-before-migration-*.ini / controls-openrecomp-*.ini), so
    nothing is lost. A private copy is renamed *.migrated afterwards and never read again; a chosen settings copy
    (read-only for us) is only used while there is no shared file."""
    done = []
    for index, legacy in enumerate(legacy_paths):
        data = _read(legacy)
        if data is None:
            continue
        own = index == 0
        folder = os.path.dirname(os.path.abspath(legacy))
        current = _read(shared)
        if not data.strip() or current == data:
            pass
        elif current is None or (not current.strip()):
            atomic_write(shared, data)
            done.append(f"controls: {legacy} -> {shared}")
        elif own:
            if os.path.getmtime(legacy) > os.path.getmtime(shared):
                saved = _backup(folder, "controls-before-migration", current)
                atomic_write(shared, data)
                done.append(f"controls: {legacy} -> {shared} (newer; the old file is kept as {saved})")
            else:
                saved = _backup(folder, "controls-openrecomp", data)
                done.append(f"controls: {shared} is newer; OpenRecomp's own copy is kept as {saved}")
        if own:
            target = legacy + ".migrated"
            try:
                if os.path.exists(target):
                    os.unlink(target)
                os.replace(legacy, target)
            except OSError:
                pass
    return done
