"""Offline 1.1.9 coexistence setup and rollback drill; never starts a launcher.

The owner supplies a private COPY of the real settings folder, outside this checkout.
Only launcher.json, online.json and controls.json are read. The generated launcher
configuration references that copy and the existing game installation in place.
This is not a signed update, process-survival or game-build test.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SETTINGS_FILES = ("launcher.json", "online.json", "controls.json")
MAX_SETTINGS_BYTES = 4 * 1024 * 1024


class DrillError(ValueError):
    """A privacy-safe explanation; never includes a player's path or file values."""


def _inside(path, parent):
    try:
        return os.path.normcase(os.path.commonpath((path, parent))) == os.path.normcase(parent)
    except ValueError:
        return False


def _plain_path(path):
    path = Path(os.path.abspath(os.path.expanduser(path)))
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise DrillError("Links and junctions cannot be used by the drill.")
    return path


def _read(path, required=False):
    try:
        if path.is_symlink() or path.is_junction() or not path.is_file():
            if not path.exists() and not required:
                return None
            raise DrillError("A settings or metadata entry is not a plain file.")
        with path.open("rb") as stream:
            data = stream.read(MAX_SETTINGS_BYTES + 1)
        if len(data) > MAX_SETTINGS_BYTES:
            raise DrillError("A settings or metadata file exceeds the drill size limit.")
        value = json.loads(data.decode("utf-8-sig"))
        if not isinstance(value, dict):
            raise DrillError("A settings or metadata file must contain a JSON object.")
        return data, value
    except (OSError, UnicodeError, ValueError) as error:
        if isinstance(error, DrillError):
            raise
        raise DrillError("A settings or metadata file could not be read as JSON.") from None


def snapshot(folder, names):
    """Private in-memory fingerprints; no paths, hashes or contents enter the report."""
    result = {}
    for name in names:
        entry = _read(folder / name)
        result[name] = hashlib.sha256(entry[0]).digest() if entry else None
    return result


def _exercise_settings(old_install, settings_copy, home):
    """Exercise our persistence helper with an inert facade, never installed code."""
    before_env = os.environ.get("OPENRECOMP_HOME")
    before_path = list(sys.path)
    before_bytecode = sys.dont_write_bytecode
    try:
        os.environ["OPENRECOMP_HOME"] = str(home)
        sys.path.insert(0, str(ROOT))
        sys.dont_write_bytecode = True
        from openrecomp.adapters.t5_coexist import load_settings, read_object

        class Settings(dict):
            def __init__(self):
                super().__init__()
                self.path = str(old_install / "launcher.json")
                self.save()

            @property
            def out_dir(self):
                return str(old_install / "native")

            def env_overrides(self):
                return {}

            def save(self):
                raise DrillError("The native facade persistence must never be called.")

        core = SimpleNamespace(Settings=Settings, DEFAULTS={})
        source = read_object(settings_copy / "launcher.json")
        settings = load_settings(core, old_install, settings_copy)
        if dict(settings) != source:
            raise DrillError("The helper did not retain all settings-copy values.")
        if settings.legacy_online_paths != (str(settings_copy / "online.json"),):
            raise DrillError("The helper did not retain the explicit online source.")
        controls = settings_copy / "controls.json"
        if controls.exists() and settings.env_overrides().get("PS3_CONTROLS") != str(controls):
            raise DrillError("The helper did not retain the explicit controls source.")
        private = Path(settings.private_path("settings.json"))
        if private.exists():
            raise DrillError("The helper wrote settings during read-only attachment.")
        probe = "openrecomp_drill_probe"
        while probe in source:
            probe += "_"
        settings[probe] = True
        settings.save()
        retained = load_settings(core, old_install, settings_copy)
        if dict(retained) != dict(source, **{probe: True}) or read_object(private) != {probe: True}:
            raise DrillError("The helper did not isolate and reload an explicit private edit.")
        # Remove only the file and empty directories this exercise just created.
        # The usable setup retains config.json, never the synthetic probe.
        private.unlink()
        private.parent.rmdir()
        private.parent.parent.rmdir()
        if dict(load_settings(core, old_install, settings_copy)) != source:
            raise DrillError("The helper did not roll back the private test edit.")
        return dict(settings_loaded=True, online_source_checked=True,
                    controls_source_checked=controls.exists(), private_write_checked=True,
                    private_edit_rollback_checked=True, inert_settings_facade=True)
    except (OSError, ValueError, TypeError, AttributeError):
        raise DrillError("The inert settings helper exercise failed.") from None
    finally:
        if before_env is None:
            os.environ.pop("OPENRECOMP_HOME", None)
        else:
            os.environ["OPENRECOMP_HOME"] = before_env
        sys.path[:] = before_path
        sys.dont_write_bytecode = before_bytecode


def run_drill(old_install, settings_copy, work, expect="update", checkout=ROOT):
    if expect not in ("update", "rollback"):
        raise DrillError("The expected result must be update or rollback.")
    old_install, settings_copy, work = map(_plain_path, (old_install, settings_copy, work))
    checkout = Path(os.path.abspath(checkout))
    paths = (old_install, settings_copy, work)
    if any(_inside(path, checkout) or _inside(checkout, path) for path in paths):
        raise DrillError("Keep installation, settings copy and drill work outside the public checkout.")
    for index, path in enumerate(paths):
        for other in paths[index + 1:]:
            if _inside(path, other) or _inside(other, path):
                raise DrillError("Installation, settings copy and work folders must not overlap.")
    if not old_install.is_dir() or not settings_copy.is_dir():
        raise DrillError("The old installation and the settings copy must be existing folders.")
    if work.exists() and (not work.is_dir() or any(work.iterdir())):
        raise DrillError("The drill work folder must be empty.")

    release = _read(old_install / "release.json", required=True)[1]
    if release.get("version") not in ("1.1.9", "v1.1.9"):
        raise DrillError("The coexistence drill requires a 1.1.9 installation.")
    old_before = snapshot(old_install, ("release.json", "launcher.json"))
    before = snapshot(settings_copy, SETTINGS_FILES)
    if before["launcher.json"] is None:
        raise DrillError("The settings copy must include launcher.json from the 1.1.9 installation.")
    ignored = 0
    for entry in settings_copy.iterdir():
        if entry.is_symlink() or entry.is_junction():
            raise DrillError("The settings copy cannot contain links or junctions.")
        if entry.name not in SETTINGS_FILES:
            ignored += 1

    # This is the actual launcher config, not an import of the legacy program.
    # The adapter loads these explicit copy paths without changing them.
    config = dict(roots={"t5dr": str(old_install)}, t5dr_settings_copy=str(settings_copy))
    work.mkdir(parents=True, exist_ok=True)
    home = work / "home"
    home.mkdir()
    config_path = home / "config.json"
    with config_path.open("x", encoding="utf-8") as stream:
        json.dump(config, stream, indent=1)
    staged = _read(config_path, required=True)[1]
    if staged != config:
        raise DrillError("The drill configuration did not retain the selected sources.")
    exercise = _exercise_settings(old_install, settings_copy, home)

    if expect == "rollback":
        # Only these two new entries belong to this drill. No recursive removal,
        # source restoration, program swap or legacy launcher restart is involved.
        config_path.unlink()
        home.rmdir()

    unchanged_old = old_before == snapshot(old_install, ("release.json", "launcher.json"))
    unchanged_copy = before == snapshot(settings_copy, SETTINGS_FILES)
    result = dict(scope="offline-settings-only", old_version="1.1.9", expected=expect,
                  ok=unchanged_old and unchanged_copy,
                  old_metadata_unchanged=unchanged_old, settings_copy_unchanged=unchanged_copy,
                  settings_files_checked=sum(value is not None for value in before.values()),
                  ignored_entries=ignored, configuration_retained=config_path.exists(),
                  rollback_checked=expect == "rollback" and not home.exists(),
                  launcher_started=False, game_started=False, signed_update_checked=False)
    result.update(exercise)
    with (work / "report.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=1)
    return result


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--old-install", required=True, help="existing T5DR Online 1.1.9 folder; read only")
    parser.add_argument("--settings-copy", required=True, help="private settings folder COPY including launcher.json")
    parser.add_argument("--work", required=True, help="empty private folder outside the checkout")
    parser.add_argument("--expect", choices=("update", "rollback"), default="update",
                        help="rollback checks removal of only the drill's new launcher configuration")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        result = run_drill(args.old_install, args.settings_copy, args.work, args.expect)
    except DrillError as error:
        print("COEXISTENCE DRILL FAIL: " + str(error))
        return 1
    except OSError:
        # A traceback or OSError text can contain personal paths and file values.
        print("COEXISTENCE DRILL FAIL: input validation or private-work operation failed.")
        return 1
    print("COEXISTENCE DRILL " + ("PASS" if result["ok"] else "FAIL") + ": offline settings setup only.")
    print("Old metadata and the supplied settings copy checked; launcher, game and signed update not tested.")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
