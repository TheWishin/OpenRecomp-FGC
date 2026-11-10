import importlib.util
import json
import os
import struct
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile


SPEC = importlib.util.spec_from_file_location("package_release", Path(__file__).parents[1] / "tools" / "package_release.py")
package = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parents[1])
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def write(self, name, data=b"fake reviewed library"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def fake_pe(self, gui=True):
        data = bytearray(158)
        data[:2] = b"MZ"
        struct.pack_into("<I", data, 60, 64)
        data[64:68] = b"PE\0\0"
        struct.pack_into("<H", data, 68, 0x8664)
        struct.pack_into("<H", data, 88, 0x20b)
        struct.pack_into("<H", data, 156, 2 if gui else 3)
        return bytes(data)

    def test_starter_requires_windows_gui_pe(self):
        path = self.write("starter", b"MZrenamed script")
        self.assertFalse(package.windows_pe(path, gui=True))
        path.write_bytes(self.fake_pe())
        self.assertTrue(package.windows_pe(path, gui=True))
        path.write_bytes(self.fake_pe(gui=False))
        self.assertFalse(package.windows_pe(path, gui=True))

    def test_plain_versions_and_distinct_channel(self):
        package.validate_release("v1.2.3", "openrecomp-owner-channel")
        for version in ("1.2.3", "V1.2.3", "v1.2.3-rc1", "v1.2.3+test", "v01.2.3", "v1.2.3\n"):
            with self.subTest(version=version), self.assertRaises(package.PackageError):
                package.validate_release(version, "openrecomp-owner-channel")
        with self.assertRaises(package.PackageError):
            package.validate_release("v1.2.3", "")

    def test_scan_refuses_game_and_private_material(self):
        for name, data in (("innocent.txt", b"\x7fELFfake"), ("innocent.json", b"\x7fPKGfake"),
                           ("disc.iso", b"fake"), ("saves/config.json", b"{}"),
                           ("key.txt", b"-----BEGIN PRIVATE KEY-----"),
                           ("notes.txt", b"C:\\Users\\player\\private"), ("art.png", b"fake"),
                           ("player.txt", b"player@example.invalid"),
                           ("long.txt", b"x" * (128 * 1024 - 10) + b"-----BEGIN PRIVATE KEY-----")):
            path = self.write("input", data)
            with self.subTest(name=name), self.assertRaises(package.PackageError):
                package.scan_file(path, name)
        path = self.write("input", b"\x00" * 0x8001 + b"CD001")
        with self.assertRaises(package.PackageError):
            package.scan_file(path, "renamed.dat", library=True)

    def test_manifest_has_no_fixed_game_paths(self):
        path = self.write("input", json.dumps({"locations": ["D:\\somegame"]}).encode())
        with self.assertRaises(package.PackageError):
            package.scan_file(path, "games/t4.json")
        path.write_text('{"locations": []}', encoding="utf-8")
        package.scan_file(path, "games/t4.json")

    def test_runtime_inventory_is_exact_and_hash_checked(self):
        path = self.write("runtime/pythonw.exe", b"MZfake-runtime")
        inventory = {"pythonw.exe": package.digest(path)}
        self.assertEqual(set(package.verify_inventory(path.parent, inventory)), set(inventory))
        path.write_bytes(b"MZchanged")
        with self.assertRaises(package.PackageError):
            package.verify_inventory(path.parent, inventory)
        path.write_bytes(b"MZfake-runtime")
        self.write("runtime/extra.exe")
        with self.assertRaises(package.PackageError):
            package.verify_inventory(path.parent, inventory)

    def test_archive_path_and_windows_alias_refused(self):
        for name in ("../x", "a/../x", "a\\x", "/absolute", "C:/x", "a/CON.txt", "a/COM¹.txt", "a/LPT²", "a/file:stream", "a/file.", "a//x"):
            with self.subTest(name=name), self.assertRaises(package.PackageError):
                package.safe_name(name)

    def fake_runtime(self):
        folder = self.root / "runtime"
        for name in package.REQUIRED_RUNTIME - {"python312.zip"}:
            self.write("runtime/" + name, self.fake_pe())
        # This archive contains a fake standard-library member, never executable Python.
        with zipfile.ZipFile(folder / "python312.zip", "w") as z:
            z.writestr("fake.pyc", b"fake")
        files = package.checked_files(folder)
        contract = {"python": "3.12", "pyside6": "6.8.2.1", "runtime": {n: package.digest(p) for n, p in files.items()}}
        return folder, contract

    def test_runtime_minimum_and_unrelated_package_refusal(self):
        folder, contract = self.fake_runtime()
        self.assertIn("pythonw.exe", package.runtime_files(folder, contract))
        path = self.write("runtime/Lib/site-packages/unrelated/__init__.py")
        contract["runtime"]["Lib/site-packages/unrelated/__init__.py"] = package.digest(path)
        with self.assertRaises(package.PackageError):
            package.runtime_files(folder, contract)

    def test_hidden_game_in_embedded_zip_refused(self):
        folder, contract = self.fake_runtime()
        with zipfile.ZipFile(folder / "python312.zip", "a") as z:
            z.writestr("game.iso", b"fake")
        contract["runtime"]["python312.zip"] = package.digest(folder / "python312.zip")
        with self.assertRaises(package.PackageError):
            package.runtime_files(folder, contract)

    def test_game_bytes_disguised_as_stdlib_member_refused(self):
        folder, contract = self.fake_runtime()
        for data in (b"\x7fELFfake", b"\x7fPKGfake", b"\x00" * 0x8001 + b"CD001",
                     b"-----BEGIN PRIVATE KEY-----\n" + b"A" * 64 + b"\n"):
            with zipfile.ZipFile(folder / "python312.zip", "w") as z:
                z.writestr("innocent.pyc", data)
            contract["runtime"]["python312.zip"] = package.digest(folder / "python312.zip")
            with self.subTest(data=data[:12]), self.assertRaises(package.PackageError):
                package.runtime_files(folder, contract)

    def test_licenses_and_exact_sources_required(self):
        folder = self.root / "licenses"
        for name in package.REQUIRED_LICENSES:
            self.write("licenses/" + name, b"complete reviewed license text " * 4)
        inventory = {n: package.digest(p) for n, p in package.checked_files(folder).items()}
        contract = {"licenses": inventory}
        with self.assertRaises(package.PackageError):
            package.license_files(folder, contract)
        contract["sources"] = {}
        for name, version in package.REQUIRED_SOURCES.items():
            path = self.write("licenses/sources/" + name + ".tar.xz", b"fake source archive")
            rel = path.relative_to(folder).as_posix()
            contract["sources"][name] = {"version": version, "path": rel}
            inventory[rel] = package.digest(path)
        self.assertEqual(set(package.license_files(folder, contract)), set(inventory))

    def test_boot_uses_relative_private_paths_and_isolated_starter(self):
        root = Path(__file__).parents[1]
        starter = (root / "tools/starter/openrecomp.c").read_text(encoding="utf-8")
        self.assertIn("GetModuleFileNameW", starter)
        self.assertIn("OPENRECOMP_HOME", starter)
        self.assertIn("-I -B", starter)
        self.assertIn("WaitForSingleObject", starter)
        self.assertIn("GetExitCodeProcess", starter)
        self.assertIn('root / "python" / "Lib" / "site-packages"', package.BOOT)
        self.assertNotIn(".venv", package.BOOT)

    def test_boot_makes_relative_user_home_absolute_before_helper_inherits_it(self):
        previous = Path.cwd()
        try:
            with mock.patch.dict(os.environ, {"OPENRECOMP_HOME": "player-data"}), mock.patch.object(package.sys, "path", list(package.sys.path)), mock.patch("runpy.run_module") as run:
                exec(package.BOOT, {"__file__": str(self.root / "openrecomp_boot.py")})
                self.assertEqual(os.environ["OPENRECOMP_HOME"], str(self.root / "player-data"))
                run.assert_called_once_with("openrecomp", run_name="__main__")
        finally:
            os.chdir(previous)

    def test_native_failure_has_all_catalog_languages(self):
        header = (Path(__file__).parents[1] / "tools/starter/startup-locales.h").read_text(encoding="utf-8")
        for language in ("GERMAN", "SPANISH", "FRENCH", "JAPANESE", "KOREAN", "PORTUGUESE"):
            self.assertIn("case LANG_" + language, header)
        self.assertIn("default:", header)
        self.assertIn("OpenRecomp could not start its private Python", header)

    def test_cli_trust_import_finds_repo_and_refuses_other_channel(self):
        trust = SimpleNamespace(name="owner-channel", public_keys=("fake-public-key",))
        updater = SimpleNamespace(configured_channel=lambda: trust, UpdateError=ValueError)
        original_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "openrecomp":
                self.assertEqual(package.sys.path[0], str(package.ROOT))
                return SimpleNamespace(updater=updater)
            return original_import(name, *args, **kwargs)

        with mock.patch.object(package.sys, "path", [str(package.ROOT / "tools")]), mock.patch("builtins.__import__", side_effect=fake_import):
            self.assertIs(package.release_trust("owner-channel"), trust)
            with self.assertRaises(package.PackageError):
                package.release_trust("other-project")

    def test_source_payload_includes_release_features_and_pad_bindings(self):
        required = {
            "openrecomp/t4_report.py", "openrecomp/ui_sound.py", "openrecomp/nav_sound.py",
            "openrecomp/adapters/t4_support.py", "openrecomp/adapters/t5_netext.py",
            "openrecomp/adapters/build_tool_downloads.py", "openrecomp/adapters/t5_discovery.py",
            "openrecomp/adapters/t5_build_runtime.py", "openrecomp/adapters/t5_buildlock.py",
            "openrecomp/ui/PageLoader.qml", "openrecomp/ui/PeerPing.qml",
            "openrecomp/nav_controls_page.py", "openrecomp/pad_glyphs.py", "openrecomp/pad_presets.py",
            "openrecomp/ui/BindingsPage.qml", "openrecomp/ui/PadGlyph.qml",
            "openrecomp/controls_file.py", "openrecomp/ps_hid.py", "openrecomp/settings_sync.py",
        }
        self.assertFalse(required - package.SOURCE_FILES)
        root = Path(__file__).parents[1]
        for name in required:
            with self.subTest(name=name):
                self.assertTrue((root / name).is_file())

    def test_source_payload_is_exact_and_ships_player_update_guides(self):
        for name in package.SOURCE_FILES:
            data = b"{}" if name.endswith(".json") else b"fake launcher source"
            self.write(name, data)
        for name in ("LICENSE", "docs/PACKAGING.md", "docs/INSTALLING.md", "docs/UPDATES.md"):
            self.write(name)
        selected = package.source_files(self.root)
        self.assertIn("docs/INSTALLING.md", selected)
        self.assertIn("docs/UPDATES.md", selected)
        self.write("openrecomp/accidental_game.py")
        with self.assertRaises(package.PackageError):
            package.source_files(self.root)


if __name__ == "__main__":
    unittest.main()
