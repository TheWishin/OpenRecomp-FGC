"""The intro sound delay: one launcher setting, one start variable. A fake core; no game runs."""
import unittest
from unittest import mock

from openrecomp import i18n
from openrecomp.adapters.t4 import T4
from openrecomp.nav import Game, Nav
from pad_step import pad_step
from test_t4_beta_settings import MANIFEST, FakeCore

INTRO_AUDIO_DELAY_ENV = "TEKKEN4_MOVIE_AUDIO_DELAY_MS"


class IntroAudioDelay(unittest.TestCase):
    def setUp(self):
        self.save = self.enterContext(mock.patch("openrecomp.adapters.t4.save_config"))
        self.enterContext(mock.patch("openrecomp.adapters.t4.threading.Thread"))
        self.core = FakeCore()
        self.config = {}
        self.adapter = T4(MANIFEST, self.config, "fake-root", core=self.core)
        self.adapter.hero = lambda: ""

    def row(self):
        return next(row for row in self.adapter.settings() if row["id"] == "intro_audio_delay")

    def test_off_by_default_and_the_start_has_no_variable(self):
        self.assertEqual(self.row()["value"], 0)
        self.assertEqual(self.row()["options"], [(0, "@off"), (1770, "@t4.intro_audio_delay_ms_1770")])
        self.adapter._start()
        self.assertNotIn(INTRO_AUDIO_DELAY_ENV, self.core.launched)

    def test_a_chosen_delay_reaches_the_start_and_off_takes_it_away(self):
        self.adapter.set_setting("intro_audio_delay", 1770)
        self.save.assert_called_once_with(self.config)
        self.assertEqual(self.config["t4_intro_audio_delay_ms"], 1770)
        self.assertEqual(self.core.saved, {})               # the launcher's own config, not the game's settings
        self.assertEqual(self.row()["value"], 1770)
        self.adapter._start()
        self.assertEqual(self.core.launched[INTRO_AUDIO_DELAY_ENV], "1770")
        self.adapter._start(dict(TEKKEN4_NET="host:7400"))
        self.assertEqual(self.core.launched[INTRO_AUDIO_DELAY_ENV], "1770")
        self.adapter.set_setting("intro_audio_delay", 0)
        self.adapter._start()
        self.assertNotIn(INTRO_AUDIO_DELAY_ENV, self.core.launched)

    def test_off_also_drops_a_value_inherited_from_the_environment(self):
        with mock.patch.object(self.core, "game_env", return_value={INTRO_AUDIO_DELAY_ENV: "900"}):
            self.adapter._start()
            self.assertNotIn(INTRO_AUDIO_DELAY_ENV, self.core.launched)

    def test_a_number_typed_into_the_config_counts_and_is_shown(self):
        self.config["t4_intro_audio_delay_ms"] = 1500
        self.assertEqual(self.row()["value"], 1500)
        self.assertEqual(self.row()["options"][-1], (1500, i18n.message("t4.intro_audio_delay_custom", ms=1500)))
        self.adapter._start()
        self.assertEqual(i18n.localize(self.row()["options"][-1][1], "de"), "1500 ms")
        self.assertEqual(self.core.launched[INTRO_AUDIO_DELAY_ENV], "1500")

    def test_anything_else_is_off(self):
        for invalid in ("1770", 1770.0, True, -1, 5001, None, [1770]):
            with self.subTest(value=invalid):
                self.config["t4_intro_audio_delay_ms"] = invalid
                self.assertEqual(self.row()["value"], 0)
                self.adapter._start()
                self.assertNotIn(INTRO_AUDIO_DELAY_ENV, self.core.launched)
                self.adapter.set_setting("intro_audio_delay", invalid)
                self.assertEqual(self.config["t4_intro_audio_delay_ms"], invalid)
        self.save.assert_not_called()

    def test_the_settings_page_shows_it_and_the_pad_changes_it(self):
        nav = Nav([Game(MANIFEST, self.adapter)])
        nav.act("confirm", "xbox")
        target = next(i for i, row in enumerate(nav.items()) if row.get("id") == "intro_audio_delay")
        self.assertEqual(nav.items()[target]["label"], "@t4.intro_audio_delay")
        for _ in range(len(nav.items())):
            if nav.focus_index(nav.items()) == target:
                break
            pad_step(nav, target)
        self.assertEqual(nav.focus_index(nav.items()), target)
        nav.act("right", "xbox")
        self.assertEqual(self.row()["value"], 1770)
        nav.act("left", "xbox")
        self.assertEqual(self.row()["value"], 0)

    def test_every_language_has_the_texts(self):
        keys = ("t4.intro_audio_delay", "t4.intro_audio_delay_ms_1770", "t4.intro_audio_delay_custom",
                "t4.intro_audio_delay_hint",
                "t4.intro_audio_delay_lead")
        for language in i18n.LANGUAGES:
            for key in keys:
                with self.subTest(language=language, key=key):
                    self.assertTrue(i18n.catalog(language)[key].strip())
            self.assertIn("1770", i18n.catalog(language)["t4.intro_audio_delay_hint"])
        self.assertEqual(i18n.catalog("de")["t4.intro_audio_delay"], "Intro-Ton verzögern (ms)")


if __name__ == "__main__":
    unittest.main()
