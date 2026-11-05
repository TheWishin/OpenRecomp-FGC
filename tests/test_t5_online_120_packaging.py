"""Read-only release inventory checks; no package, runtime or game is built."""
import ast
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("t5_online_package", ROOT / "tools/package_release.py")
package = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package)

FEATURES = {"accounts", "challenges", "community", "moderation", "private_chat", "profiles",
            "rules", "spectating", "tournaments", "netext"}
FEATURE_SOURCES = {"openrecomp/nav_" + name + ".py" for name in FEATURES}
FEATURE_SOURCES.update("openrecomp/adapters/t5_" + name + ".py" for name in FEATURES)
FEATURE_SOURCES.add("openrecomp/adapters/t5_features.py")


class T5OnlinePackagingTests(unittest.TestCase):
    def test_t5_build_runtime_import_is_shipped(self):
        tree = ast.parse((ROOT / "openrecomp/adapters/t5dr.py").read_text(encoding="utf-8"))
        imports = {node.module for node in ast.walk(tree)
                   if isinstance(node, ast.ImportFrom) and node.level == 1}
        self.assertIn("t5_build_runtime", imports)
        name = "openrecomp/adapters/t5_build_runtime.py"
        self.assertIn(name, package.SOURCE_FILES)
        selected = package.source_files(ROOT)
        self.assertIn(name, selected)
        package.scan_file(selected[name], name)

    def test_coexistence_runtime_modules_and_guide_are_shipped(self):
        required = {"openrecomp/adapters/t5_coexist.py", "openrecomp/adapters/t5_compatibility.py",
                    "openrecomp/adapters/t5_discovery.py", "openrecomp/adapters/t5_build_runtime.py",
                    "openrecomp/adapters/t5_buildlock.py", "docs/T5DR_COEXISTENCE.md"}
        self.assertEqual(required - package.SOURCE_FILES, set())
        selected = package.source_files(ROOT)
        for name in required:
            with self.subTest(name=name):
                self.assertIn(name, selected)
                package.scan_file(selected[name], name)

    def test_all_online_feature_modules_and_parity_guide_are_shipped(self):
        required = FEATURE_SOURCES | {"docs/T5DR_ONLINE.md"}
        self.assertEqual(required - package.SOURCE_FILES, set())
        for name in required:
            with self.subTest(name=name):
                self.assertTrue((ROOT / name).is_file())

    def test_feature_registry_and_navigation_imports_are_in_inventory(self):
        tree = ast.parse((ROOT / "openrecomp/adapters/t5_features.py").read_text(encoding="utf-8"))
        registry = next(ast.literal_eval(node.value) for node in tree.body
                        if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id == "MODULES" for target in node.targets))
        self.assertEqual({name.removeprefix(".t5_") for name in registry}, FEATURES)
        for name in registry:
            self.assertIn("openrecomp/adapters/" + name.removeprefix(".") + ".py", package.SOURCE_FILES)
        tree = ast.parse((ROOT / "openrecomp/nav_online.py").read_text(encoding="utf-8"))
        imports = {alias.name for node in ast.walk(tree)
                   if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module is None
                   for alias in node.names if alias.name.startswith("nav_")}
        self.assertTrue({"nav_" + name for name in FEATURES} <= imports)
        for name in imports:
            self.assertIn("openrecomp/" + name + ".py", package.SOURCE_FILES)

    def test_current_launcher_inventory_remains_exact_and_safe(self):
        selected = package.source_files(ROOT)
        self.assertEqual(set(selected), package.SOURCE_FILES)
        self.assertTrue(FEATURE_SOURCES <= selected.keys())
        for name in selected:
            with self.subTest(name=name):
                self.assertFalse({"launcher", "lobby", "t5lobby", "src", "native"}
                                 & set(Path(name).parts))
        for name in FEATURE_SOURCES:
            package.scan_file(selected[name], name)


if __name__ == "__main__":
    unittest.main()
