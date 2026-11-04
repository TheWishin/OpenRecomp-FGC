"""Existing-install preflight uses synthetic layouts, registry entries and shortcut metadata."""
import json
import os
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp.adapters import t5_discovery as discovery
from test_t5_folder_choice import FolderLayout


class ExistingDiscovery(FolderLayout):
    def setUp(self):
        super().setUp()
        self.launcher = self.folder / "bundle" / "OpenRecomp-FGC"
        self.launcher.mkdir(parents=True)
        self.enterContext(mock.patch.object(discovery, "_launcher_folder", return_value=str(self.launcher)))
        self.drives = self.enterContext(mock.patch.object(discovery, "_drive_roots", return_value=[]))
        self.registry = self.enterContext(mock.patch.object(discovery, "_registry_paths", return_value=[]))
        self.recent = self.enterContext(mock.patch.object(discovery, "_recent_paths", return_value=[]))
        self.enterContext(mock.patch.dict(os.environ, USERPROFILE=str(self.folder / "home"),
                                         OPENRECOMP_T5DR_ROOT=""))

    def find(self, config=None, manifest=None, parent=""):
        result = discovery.existing_installs(manifest or {}, config or {}, parent)
        self.runtime.assert_not_called()
        self.process.assert_not_called()
        return result

    def test_all_common_folders_and_launchers_own_folder_are_checked(self):
        roots = [self.install("home/" + name + "/custom-name") for name in ("Desktop", "Downloads", "Documents")]
        roots += [self.install("bundle/OpenRecomp-FGC/owned"), self.install("bundle/sibling")]
        self.assertEqual(self.find(), sorted((str(root.resolve()) for root in roots), key=str.casefold))

    def test_drive_roots_are_checked_through_two_child_levels_only(self):
        drive = self.folder / "drive"
        roots = [self.install("drive/level-one"), self.install("drive/folder/level-two")]
        self.install("drive/folder/wrapper/too-deep")
        self.drives.return_value = [str(drive)]
        self.assertEqual(self.find(), sorted((str(root.resolve()) for root in roots), key=str.casefold))

    def test_a_drive_root_can_itself_be_an_install(self):
        root = self.install("root-install")
        self.drives.return_value = [str(root)]
        self.assertEqual(self.find(), [str(root.resolve())])

    def test_config_environment_manifest_registry_and_recent_paths_are_hints(self):
        roots = [self.install("elsewhere/" + name) for name in ("config", "env", "manifest", "registry", "recent")]
        self.registry.return_value = [str(roots[3])]
        self.recent.return_value = [str(roots[4] / "native" / "build")]
        (roots[4] / "native" / "build").mkdir(parents=True)
        with mock.patch.dict(os.environ, OPENRECOMP_T5DR_ROOT=str(roots[1])):
            result = self.find(config=dict(roots=dict(t5dr=str(roots[0]))),
                               manifest=dict(locations=[str(roots[2])]))
        self.assertEqual(result, sorted((str(root.resolve()) for root in roots), key=str.casefold))

    def test_launcher_metadata_and_config_recent_folders_find_moved_old_installs(self):
        root = self.install("elsewhere/old-install", "1.1.9")
        recent = self.install("elsewhere/recent-install", "1.1.8")
        output = root / "native" / "build"
        output.mkdir(parents=True)
        (self.launcher / "launcher.json").write_text(json.dumps(dict(root=str(root))), encoding="utf-8")
        self.assertEqual(self.find(config=dict(recent_folders=[str(recent)])),
                         sorted((str(root.resolve()), str(recent.resolve())), key=str.casefold))

    def test_relative_metadata_folder_is_resolved_at_the_metadata_file(self):
        root = self.install("elsewhere/old-install")
        relative = os.path.relpath(root, self.launcher)
        (self.launcher / "launcher.json").write_text(json.dumps(dict(install_dir=relative)), encoding="utf-8")
        self.assertEqual(self.find(), [str(root.resolve())])

    def test_launcher_output_metadata_and_remembered_picker_folders_find_the_owner(self):
        root = self.install("elsewhere/old-install")
        output = root / "native" / "build"
        output.mkdir(parents=True)
        (self.launcher / "launcher.json").write_text(json.dumps(dict(out_dir=str(output))), encoding="utf-8")
        self.assertEqual(self.find(dict(picker_dirs=dict(folder=str(output)))), [str(root.resolve())])

    def test_old_launcher_with_missing_release_and_python_is_still_offered(self):
        root = self.folder / "home" / "Desktop" / "old"
        root.mkdir(parents=True)
        marker = root / ".core-marker"
        marker.write_text("inert identity", encoding="utf-8")
        self.files[str(root / "launcher" / "core.py")] = marker
        self.files[str(root / "T5DR Online.exe")] = marker
        self.assertEqual(self.find(), [str(root.resolve())])

    def test_unrelated_launcher_core_is_not_treated_as_a_t5dr_install(self):
        root = self.folder / "home" / "Desktop" / "unrelated"
        root.mkdir(parents=True)
        marker = root / ".core-marker"
        marker.write_text("inert identity", encoding="utf-8")
        self.files[str(root / "launcher" / "core.py")] = marker
        self.assertEqual(self.find(), [])

    def test_duplicate_hints_are_canonical_sorted_and_never_write_existing_files(self):
        root = self.install("home/Documents/existing")
        metadata = root / "launcher.json"
        metadata.write_text('{"unknown":{"keep":true}}', encoding="utf-8")
        before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        self.registry.return_value = [str(root), str(root / ".")]
        self.assertEqual(self.find(dict(recent_paths=[str(root)])), [str(root.resolve())])
        self.assertEqual({str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}, before)

    def test_unreadable_folders_and_bad_metadata_do_not_hide_other_installs(self):
        root = self.install("home/Downloads/valid")
        (self.launcher / "launcher.json").write_text("[invalid", encoding="utf-8")
        original = discovery.os.scandir

        def scan(path):
            if path == str(self.folder / "home" / "Desktop"):
                raise PermissionError("synthetic denial")
            return original(path)

        with mock.patch.object(discovery.os, "scandir", side_effect=scan):
            self.assertEqual(self.find(), [str(root.resolve())])

    def test_scan_does_not_descend_through_junctions(self):
        root = self.install("home/Documents/junction/install")
        junction = str(root.parent)
        original = discovery.os.path.isjunction
        with mock.patch.object(discovery.os.path, "isjunction", side_effect=lambda path: path == junction or original(path)):
            self.assertEqual(self.find(), [])

    def test_incomplete_marker_folders_do_not_count_as_installs(self):
        root = self.install("home/Desktop/incomplete")
        self.files[str(root / "T5DR Online.exe")].unlink()
        self.assertEqual(self.find(), [])

    def test_explicit_parent_and_wrapper_hints_are_checked(self):
        root = self.install("different-parent/wrapper/install")
        self.assertEqual(self.find(parent=str(root.parent.parent)), [str(root.resolve())])


class RegistryDiscovery(unittest.TestCase):
    def test_uninstall_app_paths_and_legacy_recent_fields_are_read_only(self):
        uninstall = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
        values = {
            uninstall: {},
            uninstall + r"\old": dict(DisplayName="T5DR Online", InstallLocation=r"D:\old"),
            uninstall + r"\unrelated": dict(DisplayName="Unrelated", InstallLocation=r"D:\other"),
            r"Software\Microsoft\Windows\CurrentVersion\App Paths\T5DR Online.exe":
                {"": r'"E:\portable\T5DR Online.exe"'},
            r"Software\T5DR Online": dict(RecentFolders=[r"F:\recent"]),
        }

        class Key:
            def __init__(self, name):
                self.name = name

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def open_key(hive, name, reserved, access):
            if name not in values:
                raise OSError("missing synthetic key")
            return Key(name)

        def enum_key(key, index):
            names = ["old", "unrelated"] if key.name == uninstall else []
            if index >= len(names):
                raise OSError("end")
            return names[index]

        def enum_value(key, index):
            pairs = list(values[key.name].items())
            if index >= len(pairs):
                raise OSError("end")
            return (*pairs[index], 1)

        fake = SimpleNamespace(HKEY_CURRENT_USER=1, HKEY_LOCAL_MACHINE=2, KEY_READ=4,
                               OpenKey=mock.Mock(side_effect=open_key), EnumKey=enum_key, EnumValue=enum_value)
        with mock.patch.dict(sys.modules, winreg=fake):
            paths = discovery._registry_paths()
        self.assertEqual(set(paths), {os.path.realpath(path) for path in (r"D:\old", r"E:\portable", r"F:\recent")})
        self.assertTrue(all(call.args[3] == fake.KEY_READ for call in fake.OpenKey.call_args_list))

    def test_missing_registry_is_harmless(self):
        with mock.patch.dict(sys.modules, winreg=None):
            self.assertEqual(discovery._registry_paths(), [])


class ShortcutDiscovery(FolderLayout):
    def test_recent_shortcut_target_is_read_without_executing_it(self):
        root = self.install("elsewhere/existing")
        path = str(root / "T5DR Online.exe")
        header = bytearray(76)
        struct.pack_into("<I", header, 0, 76)
        struct.pack_into("<I", header, 20, 2)
        target = path.encode("utf-16-le") + b"\0\0"
        info = struct.pack("<9I", 36 + len(target), 36, 1, 0, 0, 0, 0, 36, 0)
        recent = self.folder / "appdata" / "Microsoft" / "Windows" / "Recent"
        recent.mkdir(parents=True)
        (recent / "old launcher.lnk").write_bytes(header + info + target)
        (recent / "broken.lnk").write_bytes(b"inert malformed shortcut")
        with mock.patch.dict(os.environ, APPDATA=str(self.folder / "appdata")):
            self.assertEqual(discovery._recent_paths(), [path])
        self.process.assert_not_called()
        self.runtime.assert_not_called()


if __name__ == "__main__":
    unittest.main()
