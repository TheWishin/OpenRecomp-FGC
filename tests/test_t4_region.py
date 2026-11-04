"""The launcher's T4 is Tekken 4 USA only: a tree made for another disc (PAL SCES-50878) is refused, never built."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from openrecomp.adapters import t4_region, t4_source

US = t4_region.US_ELF_SHA1
PAL_SHA1 = "0123456789abcdef0123456789abcdef01234567"


def us_iso_tool(boot="SLUS_203.28", sha1=US):
    # The real US tool's lines (tools/iso_extract.py); its error text names the PAL serial, which is no evidence.
    return ('"""Minimal ISO9660 reader for Tekken 4 (US, SLUS-20328)."""\n'
            'EXPECTED_BOOT = "%s"\nEXPECTED_SHA1 = "%s"\n'
            'MSG = "only the US release is supported (PAL SCES-50878, Japan SLPS-25??? ...)"\n' % (boot, sha1))


class Tree(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "T4"
        for name in ("config", "runtime", "patches", "tools"):
            (self.root / name).mkdir(parents=True)
        self.write("tools/iso_extract.py", us_iso_tool())
        self.write("tools/build_game.ps1", "$ExpectedElfSha1 = '%s'\n# fork into ..\\tekken4-fork-ps2recomp\n" % US)
        self.write("tools/net_preflight.ps1", "# preflight\n")
        # Model a launcher separate from the fake player's home, even with TEMP inside this checkout.
        module = mock.patch.object(t4_source, "__file__",
                                   str(Path(self.tmp.name) / "launcher" / "openrecomp" / "adapters" / "t4_source.py"))
        module.start()
        self.addCleanup(module.stop)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_the_us_tree_passes(self):
        self.assertIsNone(t4_region.tree_problem(str(self.root)))

    def test_trees_for_another_disc_are_refused(self):
        cases = (("tools/iso_extract.py", us_iso_tool(boot="SCES_508.78")),
                 ("tools/iso_extract.py", us_iso_tool(sha1=PAL_SHA1)),
                 ("tools/build_game.ps1", "$ExpectedElfSha1 = '%s'\n" % PAL_SHA1),
                 ("launcher/t4core.py", 'GAME_ELF = os.path.join(ROOT, "game", "disc", "SCES_508.78")\n'),
                 ("game/disc/SCES_508.78", "elf"))
        for name, text in cases:
            with self.subTest(name=name, text=text[:40]):
                original = (self.root / name).read_text(encoding="utf-8") if (self.root / name).exists() else None
                self.write(name, text)
                self.assertEqual(t4_region.tree_problem(str(self.root)), t4_region.NOT_US)
                if original is None:
                    (self.root / name).unlink()
                else:
                    self.write(name, original)
        self.assertIsNone(t4_region.tree_problem(str(self.root)))

    def test_an_extracted_elf_must_be_the_us_one(self):
        elf = self.write("game/disc/SLUS_203.28", "not the US ELF")
        self.assertEqual(t4_region.tree_problem(str(self.root)), t4_region.NOT_US)
        self.assertNotEqual(hashlib.sha1(elf.read_bytes()).hexdigest(), US)
        with mock.patch.object(t4_region, "_elf_sha1", return_value=US):     # the real US ELF is not test data
            self.assertIsNone(t4_region.tree_problem(str(self.root)))

    def test_disc_check_output_naming_another_disc_is_refused(self):
        self.assertIsNone(t4_region.checked_disc_problem("BOOT2 SLUS_203.28\nELF_SHA1 %s\nOK\n" % US))
        self.assertIsNone(t4_region.checked_disc_problem("OK\n"))
        self.assertEqual(t4_region.checked_disc_problem("BOOT2 SCES_508.78\nOK\n"), t4_region.NOT_US)
        self.assertEqual(t4_region.checked_disc_problem("ELF_SHA1 %s\nOK\n" % PAL_SHA1), t4_region.NOT_US)

    def test_source_core_refuses_check_build_and_play_for_a_pal_tree(self):
        self.write("tools/iso_extract.py", us_iso_tool(boot="SCES_508.78", sha1=PAL_SHA1))
        with mock.patch.object(t4_source, "user_dir", return_value=str(Path(self.tmp.name) / "home")):
            core = t4_source.SourceCore(str(self.root))
        iso = self.write("pal.iso", "image")
        with mock.patch.object(t4_source.subprocess, "run") as run:
            self.assertEqual(core.verify_iso(str(iso)), (False, t4_region.NOT_US))
            run.assert_not_called()                   # the tree's own (PAL) check never runs
        with self.assertRaisesRegex(RuntimeError, "t4.region.not_us"):
            core.build_command(str(iso))
        self.assertEqual(core.play_problems({}), [t4_region.NOT_US])

    def test_source_core_refuses_an_image_whose_check_names_another_elf(self):
        with mock.patch.object(t4_source, "user_dir", return_value=str(Path(self.tmp.name) / "home")):
            core = t4_source.SourceCore(str(self.root))
        iso = self.write("x.iso", "image")
        answer = mock.Mock(returncode=0, stdout="BOOT2 SLUS_203.28\nELF_SHA1 %s\nOK\n" % PAL_SHA1)
        with mock.patch.object(t4_source.subprocess, "run", return_value=answer):
            self.assertEqual(core.verify_iso(str(iso)), (False, t4_region.NOT_US))
        answer.stdout = "BOOT2 SLUS_203.28\nELF_SHA1 %s\nOK\n" % US
        with mock.patch.object(t4_source.subprocess, "run", return_value=answer):
            self.assertEqual(core.verify_iso(str(iso)), (True, ""))

    def test_a_built_pal_install_with_its_own_core_never_reaches_play(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from test_t4 import MANIFEST, FakeCore
        from openrecomp.adapters.t4 import T4
        self.write("tools/iso_extract.py", us_iso_tool(boot="SCES_508.78", sha1=PAL_SHA1))
        core = FakeCore()                               # a native core: accepts its own build, knows no region
        with mock.patch("openrecomp.adapters.t4.save_config"),                 mock.patch("openrecomp.adapters.t4.threading.Thread"),                 mock.patch("openrecomp.adapters.t4.LaunchGuard"),                 mock.patch("openrecomp.adapters.t4.game_process_running", return_value=False):
            adapter = T4(MANIFEST, {}, str(self.root), core=core)
            self.assertEqual(adapter.problems()[0], t4_region.NOT_US)
            self.assertFalse(adapter.ready())
            with self.assertRaisesRegex(RuntimeError, "t4.region.not_us"):
                adapter.start()
            self.assertEqual(core.started, [])          # GameRun never ran
            self.write("tools/iso_extract.py", us_iso_tool())
            self.assertEqual(adapter.problems(), [])

    def test_the_refusal_names_the_us_release_in_every_language(self):
        import json
        folder = Path(t4_region.__file__).resolve().parents[1] / "i18n"
        for path in folder.glob("*.json"):
            text = json.loads(path.read_text(encoding="utf-8"))["t4.region.not_us"]
            with self.subTest(language=path.stem):
                self.assertIn("SLUS-20328", text)


if __name__ == "__main__":
    unittest.main()
