"""Wine / Proton (Linux, Steam Deck; docs/LINUX_STEAM_DECK.md). Tekken 4's build and its online check are PowerShell
scripts that Wine and Proton cannot run: there the launcher says so (@t4.no_powershell) instead of starting them.
On Windows nothing is asked. The CJK fallback list keeps Windows' fonts first and adds the Linux ones. The T5DR
problem check's wine_graphics finding has its texts. No PowerShell, Wine or game is started here."""
import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from openrecomp import app, wine
from openrecomp.adapters import support

ROOT = Path(__file__).parents[1]


class Fn:
    def __init__(self, ret):
        self.ret = ret

    def __call__(self):
        return self.ret


class WineNtdll:
    wine_get_version = Fn(b"10.0")


class WindowsNtdll:
    pass


def never(*_a, **_k):
    raise AssertionError("PowerShell was started")


class Detect(unittest.TestCase):
    def test_stand_ins(self):
        self.assertEqual(wine.wine_version(WineNtdll()), "10.0")
        self.assertIsNone(wine.wine_version(WindowsNtdll()))

    @unittest.skipUnless(os.name == "nt", "Windows")
    def test_this_pc_is_windows(self):
        self.assertIsNone(wine.wine_version())
        with mock.patch.object(wine.subprocess, "run", never):
            self.assertTrue(wine.powershell_works())         # nothing started on Windows


class PowerShell(unittest.TestCase):
    def test_answers(self):
        self.assertTrue(wine.powershell_works(run=never, wine=None) if os.name == "nt" else True)
        silent = lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "", "")    # Wine's stand-in: no output
        self.assertFalse(wine.powershell_works(run=silent, wine="10.0"))
        ok = lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "orpsok\r\n", "")
        self.assertTrue(wine.powershell_works(run=ok, wine="10.0"))

        def missing(*_a, **_k):
            raise FileNotFoundError("powershell.exe")
        self.assertFalse(wine.powershell_works(run=missing, wine="10.0"))


class Adapters(unittest.TestCase):
    def test_t4_build_refused_without_powershell(self):
        from openrecomp.adapters import t4

        class Fake:
            _online_work_active = running = _building = lambda self: False
        with mock.patch.object(wine, "powershell_works", return_value=False):
            with self.assertRaises(RuntimeError) as e:
                t4.T4.build_start(Fake())
            self.assertEqual(str(e.exception), "@t4.no_powershell")

    def test_t4_direct_scripts_refused_without_powershell(self):
        from openrecomp.adapters import t4_online
        cancel = mock.Mock(is_set=lambda: False)
        with mock.patch.object(wine, "powershell_works", return_value=False), \
                mock.patch.object(t4_online.subprocess, "Popen", never):
            with self.assertRaises(t4_online.DirectCheckError) as e:
                t4_online.T4Direct._direct_process(object(), ["powershell.exe", "-File", "x.ps1"], cancel)
            self.assertEqual(str(e.exception), "@t4.no_powershell")


class Texts(unittest.TestCase):
    def test_keys_in_every_catalog(self):
        keys = ("t4.no_powershell", "support.finding.wine_graphics.title", "support.finding.wine_graphics.fix")
        for path in sorted((ROOT / "openrecomp" / "i18n").glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for key in keys:
                self.assertTrue(data.get(key), (path.name, key))
        self.assertEqual(support.FINDINGS["wine_graphics"], ("@support.finding.wine_graphics.title",
                                                             "@support.finding.wine_graphics.fix"))

    def test_cjk_fallbacks_keep_windows_first(self):
        self.assertEqual(app.CJK_FALLBACKS[:2], ["Yu Gothic UI", "Malgun Gothic"])
        self.assertIn("Noto Sans CJK JP", app.CJK_FALLBACKS)


if __name__ == "__main__":
    unittest.main()
