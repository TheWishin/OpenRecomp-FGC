"""Which core drives a T4 folder: a source tree that also ships T4's own launcher/ (release zips since T4 99b95b9)
is built as a source tree; only a portable release (toolchain/toolchain.json) uses its own launcher/t4core.py."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from openrecomp.adapters import t4
from openrecomp.adapters.t4_install import SOURCE_DIRS, SOURCE_TOOLS


class CoreChoice(unittest.TestCase):
    def tree(self, launcher=True, toolchain=False):
        tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / "T4"
        for name in SOURCE_TOOLS:
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text("", encoding="utf-8")
        for name in SOURCE_DIRS:
            (root / name).mkdir(parents=True, exist_ok=True)
        if launcher:
            (root / "launcher").mkdir()
            (root / "launcher" / "t4core.py").write_text("OWN_CORE = True\n", encoding="utf-8")
        if toolchain:
            (root / "toolchain").mkdir()
            (root / "toolchain" / "toolchain.json").write_text("{}", encoding="utf-8")
        return str(root)

    def test_source_tree_with_t4s_own_launcher_is_built_as_a_source_tree(self):
        facade = object()
        with mock.patch("openrecomp.adapters.t4_source.create_core", return_value=facade):
            self.assertIs(t4.load_core(self.tree(launcher=True)), facade)
            self.assertIs(t4.load_core(self.tree(launcher=False)), facade)

    def test_portable_release_uses_its_own_core(self):
        with mock.patch("openrecomp.adapters.t4_source.create_core", side_effect=AssertionError("source core")):
            core = t4.load_core(self.tree(launcher=True, toolchain=True))
        self.assertTrue(getattr(core, "OWN_CORE", False))


if __name__ == "__main__":
    unittest.main()
