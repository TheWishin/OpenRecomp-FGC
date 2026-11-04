"""Living menu art is bounded, main-first and entirely supplied by the adapter."""
from pathlib import Path
import unittest

from openrecomp.living_background import background_view


class Art:
    def __init__(self):
        self.calls = []
        self.roster_calls = 0
        self.available = True

    def fighters(self):
        self.roster_calls += 1
        return [dict(key="a", name="Fighter A"), dict(key="b", name="Fighter B"),
                dict(key="c", name="Fighter C")]

    def main_fighter(self):
        return "Fighter B"

    def fighter_render(self, key):
        self.calls.append(key)
        return str(Path(__file__).resolve().parent / (key + ".png")) if self.available else ""

    def hero(self):
        return ""


class LivingBackground(unittest.TestCase):
    def test_main_first_then_roster_without_decoding_every_fighter(self):
        adapter = Art()
        first = background_view(adapter, "t5dr", now=100)
        self.assertEqual(first["fighter"], "Fighter B")
        self.assertEqual(adapter.calls, ["b"])
        self.assertTrue(first["hasArt"])
        self.assertTrue(first["source"].endswith("/b.png"))
        self.assertEqual(background_view(adapter, "t5dr", now=117)["slot"], 0)
        self.assertEqual(adapter.calls, ["b"])
        second = background_view(adapter, "t5dr", now=118)
        self.assertEqual(second["fighter"], "Fighter A")
        self.assertEqual(adapter.calls, ["b", "a"])
        self.assertEqual(adapter.roster_calls, 1)

    def test_reduced_motion_remains_on_main_after_rotation(self):
        adapter = Art()
        background_view(adapter, "t4", main="c", now=0)
        self.assertEqual(background_view(adapter, "t4", main="c", now=19)["fighter"], "Fighter A")
        still = background_view(adapter, "t4", main="c", reduced_motion=True, now=90)
        self.assertEqual(still["slot"], 0)
        self.assertEqual(still["fighter"], "Fighter C")
        self.assertEqual(background_view(adapter, "t4", main="c", reduced_motion=True, now=200)["source"], still["source"])

    def test_missing_art_retries_at_most_once_a_second(self):
        adapter = Art()
        adapter.available = False
        first = background_view(adapter, "t4", now=0)
        self.assertFalse(first["hasArt"])
        for tick in range(1, 20):
            background_view(adapter, "t4", now=tick / 20)
        self.assertEqual(adapter.calls, ["b"])
        adapter.available = True
        self.assertTrue(background_view(adapter, "t4", now=1)["hasArt"])
        self.assertEqual(adapter.calls, ["b", "b"])

    def test_empty_roster_uses_runtime_hero_and_unknown_theme_stays_quiet(self):
        adapter = Art()
        adapter.fighters = lambda: []
        adapter.hero = lambda: str(Path(__file__).resolve())
        self.assertTrue(background_view(adapter, "t4", now=0)["hasArt"])
        adapter.fighters = lambda: self.fail("Unknown themes must not request game art")
        self.assertFalse(background_view(adapter, "other", now=0)["hasArt"])

    def test_new_main_resets_rotation_and_optional_art_errors_do_not_break_view(self):
        adapter = Art()
        background_view(adapter, "t5dr", now=0)
        self.assertEqual(background_view(adapter, "t5dr", main="a", now=40)["fighter"], "Fighter A")
        adapter.fighter_render = lambda key: (_ for _ in ()).throw(ValueError("unavailable"))
        self.assertFalse(background_view(adapter, "t5dr", main="c", now=41)["hasArt"])

    def test_uses_current_account_main_and_upgrades_temporary_face_fallback(self):
        adapter = Art()
        adapter.online_state = lambda: dict(me=dict(char_usage=[dict(char="c", games=12, wins=5)]))
        adapter.available = False
        adapter.fighter_image = lambda key: str(Path(__file__).resolve())
        first = background_view(adapter, "t5dr", now=0)
        self.assertEqual(first["fighter"], "Fighter C")
        self.assertTrue(first["hasArt"])
        adapter.available = True
        final = background_view(adapter, "t5dr", now=1)
        self.assertTrue(final["source"].endswith("/c.png"))


if __name__ == "__main__":
    unittest.main()
