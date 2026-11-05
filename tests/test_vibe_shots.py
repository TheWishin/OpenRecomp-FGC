"""The original review GIF writer round-trips synthetic pixels without dependencies."""
from pathlib import Path
import tempfile
import unittest

from PySide6.QtGui import QColor, QImage, QImageReader

from tools.vibe_shots import write_gif


class VibeShots(unittest.TestCase):
    def test_gif_preserves_frames_size_timing_and_distinct_colours(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            frames = []
            for colour in ("#ff0000", "#0000ff", "#00ff00"):
                frame = QImage(32, 24, QImage.Format_RGB32)
                frame.fill(QColor(colour)); frames.append(frame)
            path = Path(directory) / "synthetic.gif"
            write_gif(path, frames, 100)
            reader = QImageReader(str(path))
            self.assertEqual(reader.imageCount(), 3)
            decoded_frames = [(reader.read(), reader.nextImageDelay()) for _ in frames]
            del reader
            for expected, (decoded, delay) in zip(frames, decoded_frames):
                self.assertFalse(decoded.isNull())
                self.assertEqual(decoded.size(), expected.size())
                self.assertEqual(decoded.pixelColor(4, 4), expected.pixelColor(4, 4))
                self.assertEqual(delay, 100)

    def test_gif_dictionary_resets_decode_nonuniform_pixels(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            frame = QImage(64, 64, QImage.Format_RGB32)
            for y in range(64):
                for x in range(64):
                    frame.setPixelColor(x, y, QColor(x * 4, y * 4, (x * y) % 256))
            path = Path(directory) / "synthetic.gif"
            write_gif(path, [frame])
            decoded = QImageReader(str(path)).read()
            self.assertFalse(decoded.isNull())
            self.assertEqual(decoded.size(), frame.size())
            self.assertNotEqual(decoded.pixelColor(0, 0), decoded.pixelColor(63, 63))

    def test_palette_preserves_dark_theme_shades(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            frames = []
            for colour in ("#1b1118", "#172330", "#454a53"):
                frame = QImage(32, 24, QImage.Format_RGB32)
                frame.fill(QColor(colour)); frames.append(frame)
            path = Path(directory) / "synthetic.gif"
            write_gif(path, frames)
            reader = QImageReader(str(path))
            decoded = [reader.read() for _ in frames]
            del reader
            for frame, result in zip(frames, decoded):
                self.assertEqual(result.pixelColor(4, 4), frame.pixelColor(4, 4))


if __name__ == "__main__":
    unittest.main()
