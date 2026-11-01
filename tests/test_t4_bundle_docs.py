"""Source-test instructions cover the source entry point and manual internet gate."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class T4BundleDocsTests(unittest.TestCase):
    def read(self, name):
        return " ".join((ROOT / name).read_text(encoding="utf-8").split())

    def test_source_bundle_walk_does_not_require_portable_release(self):
        text = self.read("docs/T4_FIRST_RUN.md")
        source = text.split("## Quelltext-Testbundle", 1)[1].split("## Portable release", 1)[0]
        for phrase in ("Python 3.12", "OpenRecomp-FGC/run.cmd", "START_HIER.txt",
                       "`T4/`", "automatisch", "winget", "Kopieren", "CMake",
                       "Ninja", "VS 2022", "SLUS-20328 v1.00", "Build-ID",
                       "Compiler/MSVC-Version", "Collect logs", "Dateipfad",
                       "PowerShell-Befehle abtippen", "vollstaendig schliessen",
                       "neuen PATH erbt", "Werkzeuge erneut pruefen"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, source)

    def test_network_preparation_explains_both_routes_in_german(self):
        text = self.read("docs/T4_ONLINE.md")
        preparation = text.split("## Internet vorbereiten", 1)[1].split("## Controller walk", 1)[0]
        for phrase in ("Portfreigabe", "Tailscale", "Tailnet", "UDP", "7400",
                       "DS-Lite/CGNAT", "Firewall nicht abschalten",
                       "Eingehende Regeln", "Check connection", "Start game",
                       "Collect logs", "Dateipfad", "PowerShell-Vorpruefung",
                       "UDP-Socket vor dem Spielstart", "freizugeben reicht deshalb nicht",
                       "Netzwerk beziehungsweise den Kollegen begrenzen"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, preparation)

    def test_manual_gate_covers_image_free_layout_and_real_gameplay(self):
        text = self.read("docs/HAND_CHECK.md").split("## Zusatz: T4-Testbundle", 1)[1]
        for phrase in ("Ohne Bilder", "sichtbarer Fokus", "Maus", "Kopieren",
                       "1080p/150 Prozent", "15 Minuten", "beiden PCs",
                       "Dateipfad", "vorhandenen ZIP", "View + Menu",
                       "Internet-Spiel muessen von Menschen geprueft werden"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_readme_exposes_the_test_bundle_entry_point(self):
        text = self.read("README.md")
        for phrase in ("tools\\make_t4_test_bundle.ps1", "both source scans",
                       "START_HIER.txt", "OpenRecomp-FGC/run.cmd", "sibling `T4/`",
                       "Python 3.12", "No typed PowerShell build"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
