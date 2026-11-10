"""VS render caches use synthetic pixels and inert installed-decoder interfaces."""
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp import fighter_render, t4_art
from openrecomp.adapters.base import Adapter
from openrecomp.adapters.t5dr import T5DR
from test_t4_art import read_png


class RenderPixels(unittest.TestCase):
    def test_runtime_helper_is_in_the_explicit_launcher_payload(self):
        from tools import package_release
        self.assertIn("openrecomp/fighter_render.py", package_release.SOURCE_FILES)

    def decoder(self, rgba=None):
        width = fighter_render.RENDER_SIZE
        self.pixels = rgba or (bytes((10, 20, 30, 0)) + bytes((90, 80, 70, 255)) * (width - 1)) * width
        return SimpleNamespace(TEX_W=1008,
            render_dxt=mock.Mock(return_value=b"synthetic compressed render"),
            dxt5_square=mock.Mock(return_value=self.pixels))

    def test_upper_body_uses_large_source_crop_and_keeps_alpha(self):
        decoder = self.decoder()
        width, height, rgba = fighter_render.t5_cutout(decoder, ("source",), 9)
        self.assertEqual((width, height), (768, 768))
        decoder.render_dxt.assert_called_once_with("source", 9, rows=768)
        decoder.dxt5_square.assert_called_once_with(b"synthetic compressed render", 1008, 120, 0, 768)
        self.assertEqual(rgba, self.pixels)
        self.assertEqual(rgba[3], 0)
        self.assertEqual(rgba[7], 255)

    def test_p2_reverses_pixels_without_losing_alpha(self):
        decoder = self.decoder()
        width, height, rgba = fighter_render.t5_cutout(decoder, (), 9, mirrored=True)
        self.assertEqual(rgba[:4], bytes((90, 80, 70, 255)))
        self.assertEqual(rgba[(width - 1) * 4:width * 4], bytes((10, 20, 30, 0)))
        self.assertEqual(fighter_render.mirror_rgba(rgba, width, height), self.pixels)

    def test_native_opposite_side_render_is_preferred_and_not_flipped_twice(self):
        decoder = self.decoder()
        calls = []
        def native(*sources, rows=0, mirrored=False):
            calls.append((sources, rows, mirrored))
            return b"native opposite-side render"
        decoder.render_dxt = native
        self.assertEqual(fighter_render.t5_cutout(decoder, ("source",), 9, mirrored=True)[2], self.pixels)
        self.assertEqual(calls, [(("source", 9), 768, True)])

    def test_small_or_truncated_source_is_rejected(self):
        decoder = self.decoder()
        decoder.TEX_W = 128
        with self.assertRaisesRegex(ValueError, "too small"):
            fighter_render.t5_cutout(decoder, (), 9)
        decoder.TEX_W = 1008
        decoder.dxt5_square.return_value = self.pixels[:-1]
        with self.assertRaisesRegex(ValueError, "ends early"):
            fighter_render.t5_cutout(decoder, (), 9)

    def test_render_publish_is_atomic_and_preserves_alpha(self):
        folder = Path(self.enterContext(tempfile.TemporaryDirectory(dir=Path(__file__).parent)))
        path = folder / "renders" / "fighter.png"
        rgba = bytes((1, 2, 3, 0, 4, 5, 6, 255))
        fighter_render.write_render(str(path), 2, 1, rgba)
        self.assertEqual(read_png(str(path)), (2, 1, [rgba]))
        with mock.patch.object(fighter_render.os, "replace", side_effect=OSError("synthetic publish failure")):
            with self.assertRaises(OSError):
                fighter_render.write_render(str(path), 2, 1, bytes(8))
        self.assertEqual(read_png(str(path)), (2, 1, [rgba]))
        self.assertEqual(list(path.parent.iterdir()), [path])


class T5RenderCache(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory(dir=Path(__file__).parent)))
        self.enterContext(mock.patch("openrecomp.adapters.t5dr.art_dir", return_value=str(self.folder / "art")))
        self.adapter = T5DR.__new__(T5DR)
        self.adapter._fighters = [dict(id=9, key="jin")]
        self.adapter.s = SimpleNamespace(out_dir=str(self.folder / "readonly-build"))
        self.adapter.state = lambda: dict(built=True)
        self.adapter.problem = ""

    def test_separate_large_cache_is_reused_without_touching_list_portraits(self):
        path = self.folder / "art" / "fighters" / "render_09_p2.png"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"synthetic cache")
        self.adapter.state = mock.Mock(side_effect=AssertionError("cache needs no game read"))
        self.assertEqual(self.adapter.fighter_render("jin", mirrored=True), str(path))
        self.assertEqual(self.adapter.fighter_render("unknown"), "")
        self.assertEqual(Adapter({}).fighter_render("jin"), "")

    def test_missing_cache_is_decoded_once_in_background_per_side(self):
        entered, release = threading.Event(), threading.Event()
        def make(*args):
            entered.set()
            release.wait(5)
        with mock.patch.object(self.adapter, "_make_fighter_render", side_effect=make) as worker:
            try:
                self.assertEqual(self.adapter.fighter_render("jin"), "")
                self.assertTrue(entered.wait(2))
                for _ in range(5):
                    self.assertEqual(self.adapter.fighter_render("jin"), "")
                worker.assert_called_once()
                self.assertEqual(worker.call_args.args[0], 9)
                self.assertFalse(worker.call_args.args[2])
            finally:
                release.set()

    def test_child_job_uses_readonly_build_and_writes_only_private_large_cache(self):
        from openrecomp import t5_art_child
        source = Path(self.adapter.s.out_dir)
        source.mkdir()
        marker = source / "synthetic-data.txt"
        marker.write_bytes(b"unchanged synthetic data")
        pixels = bytes((3, 4, 5, 0, 6, 7, 8, 255)) * (768 * 768 // 2)
        decoder = SimpleNamespace(TEX_W=1008,
            ra=SimpleNamespace(find_sources=mock.Mock(return_value=(str(marker),))),
            render_dxt=mock.Mock(return_value=b"synthetic DXT5"),
            dxt5_square=mock.Mock(return_value=pixels))
        path = self.folder / "art" / "fighters" / "render_09_p1.png"
        with mock.patch("openrecomp.t5_art_child.importlib.import_module", return_value=decoder):
            t5_art_child.make_render(str(source), 9, str(path))
        self.assertEqual(read_png(str(path))[:2], (768, 768))
        self.assertEqual(marker.read_bytes(), b"unchanged synthetic data")
        self.assertEqual(list(source.iterdir()), [marker])

    def test_worker_runs_in_a_child_process_and_clears_busy(self):
        self.adapter._render_lock = threading.Lock()
        self.adapter._render_busy = {(9, False)}
        path = self.folder / "art" / "fighters" / "render_09_p1.png"
        with mock.patch.object(self.adapter, "_art_child", return_value=(0, "")) as child:
            self.adapter._make_fighter_render(9, str(path))
        self.assertEqual(child.call_args.args[0], {"job": "render", "gid": 9, "path": str(path), "mirrored": False})
        self.assertEqual(self.adapter._render_busy, set())
        self.assertEqual(self.adapter.problem, "")

    def test_worker_failure_leaves_no_partial_cache_and_clears_busy(self):
        self.adapter._render_lock = threading.Lock()
        self.adapter._render_busy = {(9, False)}
        path = self.folder / "art" / "fighters" / "render_09_p1.png"
        with mock.patch.object(self.adapter, "_art_child", return_value=(1, "ImportError: synthetic missing decoder")):
            self.adapter._make_fighter_render(9, str(path))
        self.assertFalse(path.exists())
        self.assertEqual(self.adapter._render_busy, set())
        self.assertEqual(self.adapter.problem["_text"], "picture_error")

    def test_unbuilt_game_does_not_schedule_source_read(self):
        self.adapter.state = lambda: dict(built=False)
        with mock.patch.object(self.adapter, "_make_fighter_render") as worker:
            self.assertEqual(self.adapter.fighter_render("jin"), "")
        worker.assert_not_called()

    def test_thread_start_failure_leaves_art_optional_and_allows_retry(self):
        self.adapter.message = lambda key, **values: values.get("error", key)
        with mock.patch("openrecomp.adapters.t5dr.threading.Thread.start", side_effect=RuntimeError("synthetic thread failure")):
            self.assertEqual(self.adapter.fighter_render("jin"), "")
        self.assertIn("synthetic thread failure", self.adapter.problem)
        self.assertEqual(self.adapter._render_busy, set())
        self.assertEqual(self.adapter._render_tried, set())
        with mock.patch("openrecomp.adapters.t5dr.threading.Thread.start") as start:
            self.assertEqual(self.adapter.fighter_render("jin"), "")
        start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
