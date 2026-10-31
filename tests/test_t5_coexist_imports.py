"""Installed imports use fake loaders and cannot write bytecode into the old install."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp import pad
from openrecomp.adapters import t5_rules, t5_spectating
from openrecomp.adapters.support import T5Support
from openrecomp.adapters.t5_match import T5Match


class ReadOnlyRuntimeImports(unittest.TestCase):
    def setUp(self):
        self.root = os.path.abspath("selected-install")
        self.owner = SimpleNamespace(root=self.root, online_package="t5lobby",
                                     _online_modules=mock.Mock(),
                                     _online_out_dir=mock.Mock(return_value="chosen-output"))
        self.enterContext(mock.patch("builtins.open", side_effect=AssertionError("no native files")))

    def module(self, name):
        return SimpleNamespace(__file__=os.path.join(self.root, "lobby", "t5lobby", name + ".py"))

    def guarded_import(self, module, error=None):
        def imported(name):
            self.assertTrue(sys.dont_write_bytecode)
            if error is not None:
                raise error
            return module
        return imported

    def test_match_driver_import_does_not_enable_bytecode_and_restores_policy(self):
        subject = T5Match.__new__(T5Match)
        subject.root, subject.online_package = self.root, "t5lobby"
        subject._online_modules = self.owner._online_modules
        module = self.module("match_driver")
        for previous in (False, True):
            with self.subTest(previous=previous), mock.patch.object(sys, "dont_write_bytecode", previous), \
                    mock.patch("openrecomp.adapters.t5_match.importlib.import_module",
                               side_effect=self.guarded_import(module)):
                self.assertIs(subject._online_driver_module(), module)
                self.assertIs(sys.dont_write_bytecode, previous)

    def test_failed_match_driver_import_restores_policy(self):
        subject = T5Match.__new__(T5Match)
        subject.root, subject.online_package = self.root, "t5lobby"
        subject._online_modules = self.owner._online_modules
        with mock.patch.object(sys, "dont_write_bytecode", False), \
                mock.patch("openrecomp.adapters.t5_match.importlib.import_module",
                           side_effect=self.guarded_import(None, ImportError("unavailable"))):
            with self.assertRaises(ImportError):
                subject._online_driver_module()
            self.assertFalse(sys.dont_write_bytecode)

    def test_rules_import_is_read_only_and_preserves_native_capabilities(self):
        module = self.module("match_driver")
        module.game_files = mock.Mock(return_value={})
        module.game_supports_rules = mock.Mock(return_value=True)
        module.game_supports_life150 = mock.Mock(return_value=True)
        with mock.patch.object(sys, "dont_write_bytecode", False), \
                mock.patch("openrecomp.adapters.t5_rules.importlib.import_module",
                           side_effect=self.guarded_import(module)):
            self.assertEqual(t5_rules.client_options(self.owner), dict(match_rules=True, life150=True))
            self.assertFalse(sys.dont_write_bytecode)
        module.game_files.assert_called_once_with("chosen-output")

    def test_failed_rules_import_stays_optional_and_restores_policy(self):
        with mock.patch.object(sys, "dont_write_bytecode", False), \
                mock.patch("openrecomp.adapters.t5_rules.importlib.import_module",
                           side_effect=self.guarded_import(None, ImportError("unavailable"))):
            self.assertEqual(t5_rules.client_options(self.owner), dict(match_rules=False, life150=False))
            self.assertFalse(sys.dont_write_bytecode)

    def test_spectator_import_is_read_only_and_restores_policy_on_failure(self):
        module = self.module("spectate")
        for failure in (None, ImportError("unavailable")):
            with self.subTest(failure=failure), mock.patch.object(sys, "dont_write_bytecode", False), \
                    mock.patch("openrecomp.adapters.t5_spectating.importlib.import_module",
                               side_effect=self.guarded_import(module, failure)):
                if failure is None:
                    self.assertIs(t5_spectating._module(self.owner, "spectate"), module)
                else:
                    with self.assertRaises(ImportError):
                        t5_spectating._module(self.owner, "spectate")
                self.assertFalse(sys.dont_write_bytecode)

    def test_support_loader_executes_read_only_and_cleans_failed_module(self):
        subject = T5Support()
        subject.root = self.root
        name = "coexist_fake_support"
        for failure in (None, ImportError("unavailable")):
            module = SimpleNamespace()
            spec = SimpleNamespace(loader=SimpleNamespace(
                exec_module=mock.Mock(side_effect=self.guarded_import(module, failure))))
            with self.subTest(failure=failure), mock.patch.dict(sys.modules), \
                    mock.patch.object(sys, "dont_write_bytecode", False), \
                    mock.patch("openrecomp.adapters.support.os.path.isfile", return_value=True), \
                    mock.patch("openrecomp.adapters.support.importlib.util.spec_from_file_location", return_value=spec), \
                    mock.patch("openrecomp.adapters.support.importlib.util.module_from_spec", return_value=module):
                if failure is None:
                    self.assertIs(subject._support_import(name), module)
                    self.assertIs(sys.modules[name], module)
                else:
                    with self.assertRaises(ImportError):
                        subject._support_import(name)
                    self.assertNotIn(name, sys.modules)
                self.assertFalse(sys.dont_write_bytecode)

    def test_hid_reader_import_is_read_only_and_retains_reader(self):
        module = self.module("padnav")
        module.HidSource = mock.Mock(return_value=object())
        package = SimpleNamespace(origin=os.path.join(self.root, "lobby", "t5lobby", "__init__.py"))
        for failure in (None, ImportError("unavailable")):
            with self.subTest(failure=failure), mock.patch.dict(sys.modules), mock.patch.object(sys, "path", list(sys.path)), \
                    mock.patch.object(sys, "dont_write_bytecode", False), \
                    mock.patch("openrecomp.pad.PathFinder.find_spec", return_value=package), \
                    mock.patch("openrecomp.pad.importlib.import_module",
                               side_effect=self.guarded_import(module, failure)):
                for name in tuple(sys.modules):
                    if name == "t5lobby" or name.startswith("t5lobby."):
                        del sys.modules[name]
                reader = pad.PlayStationReader(self.root)
                self.assertIs(reader.source, module.HidSource.return_value if failure is None else None)
                self.assertFalse(sys.dont_write_bytecode)


if __name__ == "__main__":
    unittest.main()
