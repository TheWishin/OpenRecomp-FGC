"""Author metadata cannot opt into Qt rich text or remote inline images."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AuthorTextSafety(unittest.TestCase):
    def test_author_facing_text_items_explicitly_use_plain_text(self):
        for name in ("Shelf.qml", "Hub.qml", "Main.qml", "Overlays.qml"):
            source = (ROOT / "openrecomp" / "ui" / name).read_text(encoding="utf-8")
            blocks = re.findall(r"\bText\s*\{(.*?)\}", source, re.S)
            self.assertTrue(blocks, name)
            for block in blocks:
                with self.subTest(file=name, text=block[:70]):
                    self.assertRegex(block, r"\btextFormat:\s*Text\.PlainText\b")


if __name__ == "__main__":
    unittest.main()
