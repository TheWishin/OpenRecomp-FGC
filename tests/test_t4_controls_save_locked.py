"""A held controls.ini (the running game re-reads it, an antivirus scan) must not stop the second save."""
import os
import tempfile
import unittest
from unittest import mock

from openrecomp import t4_controls_ini as ini


class SaveLockedTest(unittest.TestCase):
    def test_second_save_while_replace_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "controls.ini")
            c = ini.Controls.load(path)
            c.save(path)                                   # first save: the file is new
            real = os.replace
            calls = {"n": 0}

            def refuse(src, dst):
                calls["n"] += 1
                raise PermissionError(5, "Access is denied")
            with mock.patch.object(ini.os, "replace", side_effect=refuse), mock.patch.object(ini.time, "sleep"):
                c2 = ini.Controls.load(path)
                c2.save(path)                              # replace always refused -> written in place
            self.assertGreater(calls["n"], 1)
            self.assertTrue(os.path.isfile(path))
            self.assertEqual([n for n in os.listdir(d) if n.endswith(".tmp")], [])
            self.assertIs(os.replace, real)


if __name__ == "__main__":
    unittest.main()
