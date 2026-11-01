"""Check bundled mail patches with Git without applying or building anything."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("patch_apply_bundle", ROOT / "tools/t4_test_bundle.py")
bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundle)


class T4PatchApplyTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("git"), "Git is needed for the read-only patch check")
    def test_cleaned_patch_passes_git_apply_check(self):
        address = b"synthetic" + b"@" + b"example.invalid"
        diff = (b"diff --git a/notes.txt b/notes.txt\n"
                b"--- a/notes.txt\n"
                b"+++ b/notes.txt\n"
                b"@@ -1 +1 @@\n"
                b"-Before\n"
                b"+After\n")
        patch = (b"From: Synthetic <" + address + b">\n"
                 b"Subject: [PATCH] Update a plain text sample\n\n"
                 b"Co-Authored-By: Synthetic <" + address + b">\n\n" + diff)
        cleaned = bundle.clean_patch_header(patch)
        self.assertEqual(cleaned[cleaned.index(b"diff --git "):], diff)
        self.assertTrue(cleaned.startswith(b"From: T4 test\n"))
        self.assertNotIn(address, cleaned)
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = Path(temporary)
            patch_path = root / "sample.patch"
            patch_path.write_bytes(cleaned)
            work = root / "work"
            work.mkdir()
            target = work / "notes.txt"
            target.write_bytes(b"Before\n")
            # Stop Git's repository discovery before the enclosing repository so
            # --check validates the temporary file, rather than skipping its path.
            environment = dict(os.environ, GIT_CEILING_DIRECTORIES=str(ROOT))
            command = [shutil.which("git"), "apply", "--check", str(patch_path)]
            checked = subprocess.run(command, cwd=work, env=environment, capture_output=True)
            self.assertEqual(checked.returncode, 0, checked.stderr.decode("utf-8", errors="replace"))
            self.assertEqual(target.read_bytes(), b"Before\n")
            # A mismatching target must fail, proving the check did inspect it.
            target.write_bytes(b"Different\n")
            rejected = subprocess.run(command, cwd=work, env=environment, capture_output=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(target.read_bytes(), b"Different\n")


if __name__ == "__main__":
    unittest.main()
