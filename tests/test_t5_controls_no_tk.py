"""Player report 2026-11-06: a fresh OpenRecomp-FGC 0.1.2 with T5DR-Online-1.2.1 beside it showed no "Pad bindings"
entry. T5DR 1.2.1's launcher/controls_ui.py imports tkinter at the top (and t5lobby.theme / dialogs subclass
tk.Canvas), but our own Python has no Tk: the import failed and controls_supported() said False. The two classes we
use (DevicePoller, Capture) never touch Tk, so the import must work without it."""
import importlib.abc
import os
import sys
import tempfile
import textwrap
import unittest
from types import SimpleNamespace

from openrecomp.adapters.base import Adapter
from openrecomp.adapters.t5_controls import Controls, TK_MODULES, _TkStandIn

# The shape of T5DR 1.2.1's files the adapter loads (the names and the top-of-file imports are the real ones).
FILES = {
    "lobby/t5lobby/__init__.py": "",
    "lobby/t5lobby/i18n.py": "def t(text):\n    return text\n\ndef N_(text):\n    return text\n\ndef ui_family():\n    return 'Segoe UI'\n",
    "lobby/t5lobby/padmap.py": "KEYS = {}\nXINPUT = {}\nDINPUT = {}\nKEYS1 = {}\nKEYS2 = {}\n\nclass PortMap:\n"
                               "    def __init__(self, controls=None):\n        pass\n\n    def update(self, *a):\n        pass\n",
    "lobby/t5lobby/padnav.py": "def default_sources(keyboard=False):\n    return []\n",
    "lobby/t5lobby/dialogs.py": """
        import tkinter as tk
        from tkinter import ttk

        from .i18n import t


        class Dialog(tk.Toplevel):
            pass
        """,
    "lobby/t5lobby/theme.py": """
        import tkinter as tk
        import tkinter.font as tkfont
        from tkinter import ttk

        from . import i18n


        class Badge(tk.Canvas):
            pass
        """,
    "launcher/first_start.py": "CONTROLS_HINT = 'hint'\n",
    "launcher/controls_edit.py": """
        from collections import namedtuple

        from t5lobby import padmap

        DeviceRef = namedtuple("DeviceRef", "kind port vid pid")
        Slot = namedtuple("Slot", "key mask")
        SLOTS = (Slot("1", 1),)
        SCOPE_PORT = "port"
        N_ = t = str


        def controls_path(out_dir, env):
            return "controls.ini"


        def mask_text(mask):
            return str(mask)


        class ControlsEditor:
            @classmethod
            def load(cls, path):
                return cls()

            def controls(self):
                return self

            def sources(self, *a):
                return []

            def table(self, *a):
                return None

            def bind(self, *a):
                pass

            def save(self):
                pass
        """,
    "launcher/controls_ui.py": """
        import queue
        import tkinter as tk
        import tkinter.font as tkfont
        from collections import namedtuple
        from tkinter import ttk

        import controls_edit as ce
        from first_start import CONTROLS_HINT
        from controls_edit import N_, t  # noqa: F401
        from controls_edit import DeviceRef
        from t5lobby import dialogs, padmap, padnav, theme
        from t5lobby.i18n import ui_family
        from t5lobby.padmap import KEYS, XINPUT


        class DevicePoller:
            def __init__(self, sources, foreground, controls):
                pass

            def step(self, now):
                pass

            def drain(self):
                return []


        class Capture:
            def update(self, now, edges, held):
                return None


        class ControlsDialog:
            def __init__(self, app):
                self.top = tk.Toplevel(app)
        """,
}


class NoTk(importlib.abc.MetaPathFinder):
    """This Python has no Tk (like the launcher's portable Python)."""

    def find_spec(self, name, path=None, target=None):
        if name == "tkinter" or name.startswith("tkinter.") or name == "_tkinter":
            raise ImportError("No module named " + repr(name))
        return None


class Subject(Controls, Adapter):
    def __init__(self, root):
        super().__init__({"id": "t5dr", "short": "T5DR"})
        self.root = root
        self.s = SimpleNamespace(out_dir=os.path.join(root, "native"), env_overrides=lambda: {})


def make_install(parent, version="1.2.1"):
    root = os.path.join(parent, "T5DR-Online-" + version)
    for relative, text in FILES.items():
        path = os.path.join(root, *relative.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(text).lstrip("\n"))
    return root


class PadBindingsWithoutTk(unittest.TestCase):
    NAMES = ("t5lobby", "t5lobby.i18n", "t5lobby.padmap", "t5lobby.padnav", "t5lobby.dialogs", "t5lobby.theme",
             "controls_edit", "controls_ui", "first_start")

    def setUp(self):
        self.saved_modules = {name: sys.modules.pop(name) for name in self.NAMES + TK_MODULES + ("_tkinter",)
                              if name in sys.modules}
        self.saved_path = list(sys.path)
        self.blocker = NoTk()
        sys.meta_path.insert(0, self.blocker)

    def tearDown(self):
        sys.meta_path.remove(self.blocker)
        for name in self.NAMES + TK_MODULES + ("_tkinter",):
            sys.modules.pop(name, None)
        sys.modules.update(self.saved_modules)
        sys.path[:] = self.saved_path

    def test_a_1_2_1_folder_shows_pad_bindings_on_a_python_without_tk(self):
        with tempfile.TemporaryDirectory() as temp:
            root = make_install(temp)
            adapter = Subject(root)
            self.assertTrue(adapter.controls_supported())
            ce, ui, pm, pn = adapter._controls_modules
            self.assertEqual(os.path.realpath(ui.__file__), os.path.realpath(os.path.join(root, "launcher", "controls_ui.py")))
            self.assertTrue(callable(ui.DevicePoller) and callable(ui.Capture))
            # the stand-in never stays where the rest of the launcher could take it for Tk
            for name in TK_MODULES:
                self.assertNotIsInstance(sys.modules.get(name), _TkStandIn, name)
            with self.assertRaises(ImportError):
                import tkinter  # noqa: F401

    def test_a_folder_without_the_controls_files_still_has_no_entry(self):
        with tempfile.TemporaryDirectory() as temp:
            root = make_install(temp)
            os.remove(os.path.join(root, "launcher", "controls_ui.py"))
            self.assertFalse(Subject(root).controls_supported())

    @unittest.skipUnless(os.environ.get("T5DR_121_ROOT"), "set T5DR_121_ROOT to a real unpacked T5DR-Online-1.2.1")
    def test_the_real_1_2_1_release(self):
        self.assertTrue(Subject(os.environ["T5DR_121_ROOT"]).controls_supported())


if __name__ == "__main__":
    unittest.main()
