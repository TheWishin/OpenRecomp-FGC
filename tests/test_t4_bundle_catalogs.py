"""Source bundle guidance and runtime inventory, without tools or a game."""
import importlib.util
from pathlib import Path
import re
import unittest

from openrecomp import i18n


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("bundle_catalog_package", ROOT / "tools/package_release.py")
package = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package)

TOOLS = ("python", "git", "cmake", "ninja", "vs2022", "msvc", "title", "recheck", "hint", "copy",
         "command", "copied", "copy_failed", "failed", "missing", "unknown", "vs_incomplete", "checking", "required")
NETWORK = ("title", "firewall_title", "firewall", "forward_title", "forward", "tailscale_title", "tailscale",
           "check_title", "check")
SOURCE = ("step_prereq", "step_verify", "step_extract", "step_fork", "step_tools", "step_recomp", "step_stage",
          "step_runtime", "data_outside", "iso_missing", "iso_timeout", "iso_start_failed", "iso_checksum",
          "iso_wrong", "iso_unreadable", "ended", "game_failed", "resolution_native")


class T4BundleCatalogTests(unittest.TestCase):
    def test_bundle_instructions_and_errors_exist_in_every_catalog(self):
        keys = (["t4.tools." + key for key in TOOLS] + ["t4.network." + key for key in NETWORK]
                + ["t4.source." + key for key in SOURCE]
                + ["t4.direct_build_id", "t4.direct_compiler", "t4.direct_log_path"])
        english = i18n.catalog("en")
        for language in i18n.LANGUAGES:
            catalog = i18n.catalog(language)
            for key in keys:
                with self.subTest(language=language, key=key):
                    self.assertIn(key, catalog)
                    self.assertTrue(catalog[key].strip())
                    self.assertEqual(re.findall(r"\{[^{}]*\}", catalog[key]),
                                     re.findall(r"\{[^{}]*\}", english[key]))

    def test_german_network_steps_explain_both_internet_routes(self):
        catalog = i18n.catalog("de")
        self.assertIn("beiden PCs", catalog["t4.network.firewall"])
        self.assertIn("UDP-Port 7400", catalog["t4.network.firewall"])
        for token in ("eingehenden", "PowerShell", "T4-Laufzeit", "Portregel"):
            self.assertIn(token, catalog["t4.network.firewall"])
        for token in ("Router", "LAN-IPv4", "öffentliche IPv4", "CGNAT"):
            self.assertIn(token, catalog["t4.network.forward"])
        for token in ("beiden PCs", "Tailscale", "100.x.x.x", "Keine Routerweiterleitung", "Firewall"):
            self.assertIn(token, catalog["t4.network.tailscale"])
        for token in ("gleichzeitig", "Build", "Compiler", "ISO", "beide Richtungen", "Protokolle"):
            self.assertIn(token, catalog["t4.network.check"])

    def test_german_tool_guidance_explains_install_and_compiler_comparison(self):
        hint = i18n.catalog("de")["t4.tools.hint"]
        for token in ("kopieren", "Terminal", "Installer", "Launcher neu starten", "erneut prüfen", "dieselbe MSVC"):
            self.assertIn(token, hint)
        for key in ("iso_checksum", "iso_wrong"):
            self.assertIn("SLUS-20328 v1.00", i18n.catalog("de")["t4.source." + key])

    def test_source_release_catalog_contains_the_source_adapter_dependencies(self):
        for name in ("t4_source.py", "t4_prerequisites.py"):
            path = "openrecomp/adapters/" + name
            with self.subTest(path=path):
                self.assertIn(path, package.SOURCE_FILES)
                self.assertTrue((ROOT / path).is_file())


if __name__ == "__main__":
    unittest.main()
