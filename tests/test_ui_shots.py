"""The screenshot tool uses safe synthetic scenes and never loads player art."""
from pathlib import Path
import unittest
from unittest import mock

from tools import ui_shots


class SyntheticScreenshots(unittest.TestCase):
    def test_every_scene_uses_fake_adapters_in_every_catalog(self):
        with mock.patch("openrecomp.app.Backend", side_effect=AssertionError("Real backend")), \
                mock.patch("socket.socket", side_effect=AssertionError("Network")), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("External process")):
            for language in ui_shots.i18n.LANGUAGES:
                for name in ui_shots.SCENES:
                    with self.subTest(language=language, scene=name):
                        nav = ui_shots.scene(name, language)
                        view = ui_shots.snapshot(nav, name)
                        self.assertTrue(nav.dry)
                        self.assertEqual(view["overlay"] == "dialog", name in ("confirm", "info", "error"))
                        self.assertEqual(nav.game.a.calls, [])
                        self.assertNotIn("controls.slot.CROSS", str(view))

    def test_snapshot_removes_art_at_every_depth(self):
        nav = ui_shots.scene("shelf", "en")
        original_view = nav.view

        def with_art():
            view = original_view()
            view["hero"] = "private-game-art.png"
            view["detail"] = dict(image="private.png", images=["private2.png"])
            view["nested"] = [dict(art="private.png", mosaic=["private3.png"], wordmark="private.png",
                                   face="private.png", plate="private.png", portrait="private.png", background="private.png")]
            return view

        nav.view = with_art
        self.assertNotIn("private", str(ui_shots.snapshot(nav, "shelf")))

    def test_default_output_and_private_home_are_inside_worktree(self):
        self.assertEqual(ui_shots.HOME, ui_shots.ROOT / "build" / "tmp-home")
        with mock.patch.dict(ui_shots.os.environ, {}, clear=True):
            ui_shots.configure_environment()
            for name in ("OPENRECOMP_HOME", "APPDATA", "LOCALAPPDATA", "TMP", "TEMP"):
                self.assertEqual(Path(ui_shots.os.environ[name]), ui_shots.HOME)
            self.assertEqual(ui_shots.os.environ["QT_QPA_PLATFORM"], "offscreen")


if __name__ == "__main__":
    unittest.main()
