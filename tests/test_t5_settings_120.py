"""T5 settings use inert settings objects; no installed runtime or game is opened."""
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp.adapters.t5dr import T5DR


class Settings(dict):
    def save(self):
        self.saved = getattr(self, "saved", 0) + 1


class T5SettingsTests(unittest.TestCase):
    def setUp(self):
        self.a = T5DR.__new__(T5DR)
        self.a.s = Settings(display="window", internal_res="native", vsync="on", shadows="on",
                            effects="on", stage_blur="off", input_delay="auto", training="off",
                            practice=False, always_left=False, mute=False, replays=True,
                            unlock_stages=False, unlock_items=False, nickname="Pad",
                            replay_dir="", replay_names=True, spectators=True,
                            spectators_ranked=False, auto_spectate=False)
        self.a.core = SimpleNamespace(INTERNAL_RES_LABELS={"native": "Native"},
                                      INPUT_DELAYS={"auto": "Auto", "0": "0", "1": "1", "2": "2"},
                                      DEFAULTS=dict(self.a.s))

    def rows(self):
        return {row["id"]: row for row in self.a.settings()}

    def test_native_spectator_and_replay_preferences_are_exposed(self):
        rows = self.rows()
        for sid in ("replay_names", "spectators", "spectators_ranked", "auto_spectate"):
            self.assertIn(sid, rows)
            self.assertEqual(rows[sid]["value"], self.a.s[sid])
            self.a.set_setting(sid, not self.a.s[sid])
            self.assertEqual(rows[sid]["options"], [(False, "@off"), (True, "@on")])
        self.assertEqual(self.a.s.saved, 4)

    def test_older_installs_do_not_offer_unsupported_preferences(self):
        for sid in ("replay_names", "spectators", "spectators_ranked", "auto_spectate", "replay_dir"):
            self.a.core.DEFAULTS.pop(sid)
        rows = self.rows()
        self.assertNotIn("replay_dir", rows)
        self.assertNotIn("auto_spectate", rows)

    def test_delay_options_follow_selected_runtime(self):
        self.assertEqual([value for value, _label in self.rows()["input_delay"]["options"]],
                         ["auto", "0", "1", "2"])
        self.a.core.INPUT_DELAYS = {value: value for value in ["auto"] + [str(n) for n in range(10)]}
        self.assertEqual([value for value, _label in self.rows()["input_delay"]["options"]],
                         ["auto"] + [str(n) for n in range(9)])
        self.a.set_setting("input_delay", 8)
        self.assertEqual(self.a.s["input_delay"], "8")
        with self.assertRaises(ValueError):
            self.a.set_setting("input_delay", 9)

    def test_unsupported_delay_is_not_saved(self):
        with self.assertRaises(ValueError):
            self.a.set_setting("input_delay", "8")
        self.assertEqual(self.a.s["input_delay"], "auto")
        self.assertFalse(hasattr(self.a.s, "saved"))

    def test_screen_side_uses_native_mirror_preference(self):
        row = self.rows()["always_left"]
        self.assertEqual(row["label"], "@t5.screen_side")
        self.assertEqual(row["options"], [(False, "@t5.side_server"), (True, "@t5.side_left")])
        self.a.set_setting("always_left", True)
        self.assertTrue(self.a.s["always_left"])

    def test_replay_folder_can_be_chosen_and_reset_without_touching_a_replay(self):
        folder = "chosen-replays"
        self.a._replays = [object()]
        with mock.patch("openrecomp.adapters.t5dr.os.path.isdir", return_value=True) as isdir:
            self.a.set_setting("replay_dir", folder)
        isdir.assert_called_once_with(folder)
        self.assertIsNone(self.a._replays)
        self.assertEqual(self.a.text_value("replay_dir"), folder)
        self.assertEqual(self.rows()["replay_dir"]["kind"], "folder")
        self.assertEqual(self.rows()["replay_dir"]["value"], folder)
        self.a.set_text_value("replay_dir", "")
        self.assertEqual(self.a.s["replay_dir"], "")
        self.assertEqual(self.rows()["replay_dir"]["display"], "@t5.replay_folder_default")

    def test_missing_replay_folder_preserves_preference_and_cache(self):
        cached = self.a._replays = [object()]
        with mock.patch("openrecomp.adapters.t5dr.os.path.isdir", return_value=False):
            with self.assertRaisesRegex(ValueError, "replay_folder_missing"):
                self.a.set_setting("replay_dir", "missing-replays")
        self.assertEqual(self.a.s["replay_dir"], "")
        self.assertIs(self.a._replays, cached)
        self.assertFalse(hasattr(self.a.s, "saved"))

    def test_character_lock_stops_all_configuration_access(self):
        self.a._online_character_locked = True
        with mock.patch.object(self.a, "online_cfg_path", side_effect=AssertionError("must not open config")):
            with self.assertRaisesRegex(RuntimeError, "character_locked"):
                self.a.set_fighter("any-character")


if __name__ == "__main__":
    unittest.main()
