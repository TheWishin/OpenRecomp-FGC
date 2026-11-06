"""After a game update the same T4 folder has a new launcher/t4core.py: load_core must load the new one."""
import os
import tempfile
import time
import unittest

from openrecomp.adapters import t4


class CoreReloadTest(unittest.TestCase):
    def test_new_core_after_update_in_the_same_folder(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "launcher"))
            os.makedirs(os.path.join(root, "toolchain"))
            open(os.path.join(root, "toolchain", "toolchain.json"), "w").close()
            core_py = os.path.join(root, "launcher", "t4core.py")
            with open(core_py, "w") as f:
                f.write("VERSION = 'old'\n")
            first = t4.load_core(root)
            self.assertEqual(first.VERSION, "old")
            self.assertIs(t4.load_core(root), first)          # unchanged file: the cached module
            time.sleep(0.05)
            with open(core_py, "w") as f:
                f.write("VERSION = 'new one'\n")
            os.utime(core_py, ns=(time.time_ns(), time.time_ns() + 1_000_000))
            second = t4.load_core(root)
            self.assertEqual(second.VERSION, "new one")


if __name__ == "__main__":
    unittest.main()
