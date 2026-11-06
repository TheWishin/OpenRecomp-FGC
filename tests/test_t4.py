"""T4 settings and controller actions with a core that never opens a game or a file."""
import json
import os
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp import i18n
from openrecomp.adapters.t4 import T4
from openrecomp.nav import Game, Nav


MANIFEST = dict(id="t4", short="T4", title="T4", numeral="4", accent="#ffffff",
                subtitle="", sections=["settings"])
AA_LEVELS = ["off", "fxaa", "smaa", "ssaa2", "ssaa3", "ssaa4", "msaa2", "msaa4", "msaa8", "ssaa2+fxaa"]


class FakeCore:
    RESOLUTIONS = [("auto", "Auto", 1)]

    SAVE_DIR = os.path.join("fake-root", "save")

    def __init__(self, aa=True, supports_aa=True):
        self.saved = dict(aa=aa)
        self.supports_aa = supports_aa
        self.env_calls = []
        self.started = []
        self.locks = []
        self.fail_start = False

    def load_settings(self):
        return dict(self.saved)

    def save_settings(self, settings):
        self.saved = dict(settings)

    def play_problems(self, settings):
        return []

    def run_lock_holder(self):
        return ""

    def find_runtime(self, settings):
        return "fake-runtime", ""

    def take_run_lock(self, owner):
        self.locks.append(owner)

    def graphics_support(self, exe):
        return dict(aa=self.supports_aa)

    def game_env(self, settings, exe=None):
        self.env_calls.append((dict(settings), exe))
        env = dict(CORE_SETTING="preserved", TEKKEN4_HUD="inherited", TEKKEN4_ANISO="inherited")
        if self.supports_aa:
            env["TEKKEN4_AA"] = "fxaa" if settings.get("aa") else "off"
        return env

    def GameRun(self, settings):
        def start():
            self.started.append(self.game_env(settings, "fake-runtime"))
            if self.fail_start:
                raise RuntimeError("fake start failure")
        proc = SimpleNamespace(pid=123, returncode=0)
        proc.poll = lambda: proc.returncode
        return SimpleNamespace(start=start, proc=proc)


class Graphics(unittest.TestCase):
    def setUp(self):
        self.save_config = self.enterContext(mock.patch("openrecomp.adapters.t4.save_config"))
        self.thread = self.enterContext(mock.patch("openrecomp.adapters.t4.threading.Thread"))
        self.guard = self.enterContext(mock.patch("openrecomp.adapters.t4.LaunchGuard"))
        self.enterContext(mock.patch("openrecomp.adapters.t4.game_process_running", return_value=False))
        self.core = FakeCore()
        self.config = {}
        self.adapter = self.make_adapter()

    def make_adapter(self):
        adapter = T4(MANIFEST, self.config, "fake-root", core=self.core)
        adapter.hero = lambda: ""
        return adapter

    def rows(self):
        return {row["id"]: row for row in self.adapter.settings()}

    def test_documented_choices_and_defaults(self):
        rows = self.rows()
        self.assertEqual([value for value, _label in rows["aa"]["options"]], AA_LEVELS)
        self.assertEqual(rows["aa"]["value"], "fxaa")
        self.assertEqual([value for value, _label in rows["hud"]["options"]], ["soft", "sharp"])
        self.assertEqual(rows["hud"]["value"], "soft")
        self.assertEqual([value for value, _label in rows["anisotropic"]["options"]], ["1", "2", "4", "8", "16"])
        self.assertEqual(rows["anisotropic"]["value"], "4")
        self.assertEqual([value for value, _label in rows["aspect"]["options"]], ["4:3", "16:9"])
        self.assertEqual(rows["aspect"]["value"], "4:3")
        self.assertFalse(any("ahead" in sid for sid in rows))

    def test_legacy_aa_boolean_selects_off_or_fxaa(self):
        for enabled, expected in ((False, "off"), (True, "fxaa")):
            with self.subTest(enabled=enabled):
                self.core.saved["aa"] = enabled
                self.adapter = self.make_adapter()
                self.assertEqual(self.rows()["aa"]["value"], expected)
                self.adapter.start()
                self.assertEqual(self.core.started[-1]["TEKKEN4_AA"], expected)

    def test_invalid_graphics_choices_fall_back_and_are_not_saved(self):
        invalid = dict(aa="unknown-aa", hud="unknown-hud", anisotropic="32")
        self.config["t4_graphics"] = dict(invalid)
        rows = self.rows()
        for sid, expected in (("aa", "fxaa"), ("hud", "soft"), ("anisotropic", "4")):
            self.assertEqual(rows[sid]["value"], expected, sid)
            self.adapter.set_setting(sid, invalid[sid])
        self.assertEqual(self.config["t4_graphics"], invalid)
        self.assertEqual(self.core.saved, dict(aa=True))
        self.save_config.assert_not_called()

    def test_graphics_persist_in_launcher_config_and_core_keeps_boolean_aa(self):
        self.config["language"] = "de"
        for sid, value in (("aa", "ssaa2+fxaa"), ("hud", "sharp"), ("anisotropic", "16")):
            self.adapter.set_setting(sid, value)
        self.save_config.assert_called_with(self.config)
        self.assertEqual(self.config["t4_graphics"], dict(aa="ssaa2+fxaa", hud="sharp", anisotropic="16"))
        self.assertIs(self.core.saved["aa"], True)
        self.assertNotIn("hud", self.core.saved)
        self.assertNotIn("anisotropic", self.core.saved)
        self.config = json.loads(json.dumps(self.config))
        self.adapter = self.make_adapter()
        rows = self.rows()
        for sid, value in self.config["t4_graphics"].items():
            self.assertEqual(rows[sid]["value"], value, sid)
        self.assertEqual(self.config["language"], "de")
        self.adapter.set_setting("aa", "off")
        self.assertIs(self.core.saved["aa"], False)
        self.adapter = self.make_adapter()
        self.assertEqual(self.rows()["aa"]["value"], "off")

    def test_every_graphics_choice_reaches_the_core_launch_environment(self):
        original = self.core.game_env
        for sid, switch, values in (("aa", "TEKKEN4_AA", AA_LEVELS),
                                    ("hud", "TEKKEN4_HUD", ["soft", "sharp"]),
                                    ("anisotropic", "TEKKEN4_ANISO", ["1", "2", "4", "8", "16"])):
            for value in values:
                with self.subTest(sid=sid, value=value):
                    self.adapter.set_setting(sid, value)
                    self.assertEqual(self.adapter.start(), 123)
                    self.assertEqual(self.core.started[-1][switch], value)
                    self.assertEqual(self.core.started[-1]["CORE_SETTING"], "preserved")
                    self.assertEqual(self.core.env_calls[-1][1], "fake-runtime")
                    self.assertEqual(self.core.game_env, original)
        self.assertEqual(len(self.core.locks), len(self.core.started))
        self.thread.assert_called()

    def test_the_pad_bindings_file_reaches_the_game(self):
        self.adapter.start()
        self.assertEqual(self.core.started[-1]["TEKKEN4_CONTROLS"], os.path.join("fake-root", "save", "controls.ini"))
        self.assertEqual(self.adapter._t4c_path(), self.core.started[-1]["TEKKEN4_CONTROLS"])

    def test_defaults_replace_inherited_hud_and_filter_values(self):
        self.adapter.start()
        self.assertEqual(self.core.started[-1]["TEKKEN4_HUD"], "soft")
        self.assertEqual(self.core.started[-1]["TEKKEN4_ANISO"], "4")
        self.assertEqual(self.core.started[-1]["TEKKEN4_WIDESCREEN"], "0")

    def test_aspect_choice_reaches_the_game_and_persists_in_launcher_config(self):
        for value, switch in (("16:9", "1"), ("4:3", "0"), ("16:9", "1")):
            with self.subTest(value=value):
                self.adapter.set_setting("aspect", value)
                self.assertEqual(self.config["t4_graphics"]["aspect"], value)
                self.assertNotIn("aspect", self.core.saved)
                self.adapter.start()
                self.assertEqual(self.core.started[-1]["TEKKEN4_WIDESCREEN"], switch)
        self.adapter.set_setting("aspect", "21:9")
        self.assertEqual(self.config["t4_graphics"]["aspect"], "16:9")
        self.adapter = self.make_adapter()
        self.assertEqual(self.rows()["aspect"]["value"], "16:9")
        # A widescreen player online: the setting stays (picture only, any mix of 4:3 and 16:9 plays together).
        self.adapter.start(extra_env=dict(TEKKEN4_NET="host:7000"))
        self.assertEqual(self.core.started[-1]["TEKKEN4_WIDESCREEN"], "1")

    def test_running_child_keeps_reservation_and_refuses_duplicate_launch(self):
        self.adapter.start()
        reservation = self.guard.return_value.acquire.return_value
        running = reservation.watch.call_args.args[0]
        self.assertFalse(running())
        self.adapter.run.proc.returncode = None
        self.assertTrue(running())
        with self.assertRaisesRegex(RuntimeError, "@online.game_running"):
            self.adapter.start()
        self.guard.assert_called_once_with("t4")
        reservation.release.assert_not_called()
        self.assertEqual(len(self.core.started), 1)
        self.adapter.run.proc.returncode = 0
        self.assertFalse(running())
        self.adapter.start()
        reservation.release.assert_called_once_with()
        self.assertEqual(len(self.core.started), 2)

    def test_existing_settings_still_persist_through_the_core(self):
        self.adapter.set_setting("resolution", "auto")
        self.assertEqual(self.core.saved["resolution"], "auto")
        self.assertNotIn("t4_graphics", self.config)
        self.save_config.assert_not_called()

    def test_aa_capability_gate_and_explicit_environment_overrides(self):
        self.core.supports_aa = False
        self.adapter.set_setting("aa", "ssaa4")
        self.adapter.start()
        self.assertNotIn("TEKKEN4_AA", self.core.started[-1])
        overrides = dict(TEKKEN4_AA="off", TEKKEN4_HUD="soft", TEKKEN4_ANISO="2", TEST_ONLY="extra")
        self.adapter.start(extra_env=overrides)
        for name, value in overrides.items():
            self.assertEqual(self.core.started[-1][name], value)

    def test_failed_start_restores_core_environment_hook(self):
        original = self.core.game_env
        self.core.fail_start = True
        with self.assertRaisesRegex(RuntimeError, "fake start failure"):
            self.adapter.start(extra_env={"TEST_ONLY": "extra"})
        self.assertEqual(self.core.game_env, original)
        self.assertEqual(self.core.locks, [])
        self.assertIsNone(self.adapter.run)
        self.thread.assert_not_called()

    def test_controller_cycles_every_choice_and_translates_in_all_languages(self):
        targets = {"aa", "hud", "anisotropic", "aspect"}
        for code in i18n.LANGUAGES:
            with self.subTest(language=code):
                nav = Nav([Game(MANIFEST, self.adapter)], language=code)
                nav.act("confirm")
                seen = set()
                for setting in self.adapter.settings():
                    if setting["id"] in targets:
                        # Settings are grouped (Display & graphics first): walk to the row with the pad.
                        for _ in range(60):
                            items = nav.items()
                            target = next(i for i, item in enumerate(items) if item.get("id") == setting["id"])
                            if nav.focus_index(items) == target:
                                break
                            nav.act("down" if nav.focus_index(items) < target else "up")
                        seen.add(setting["id"])
                        for field in ("label", "hint", "lead"):
                            self.assertTrue(setting[field].startswith("@"))
                            self.assertIn(setting[field][1:], i18n.catalog(code))
                        for _ in setting["options"]:
                            current = self.rows()[setting["id"]]["value"]
                            label = dict(setting["options"])[current]
                            self.assertTrue(label.startswith("@"))
                            self.assertIn(label[1:], i18n.catalog(code))
                            view = nav.view()
                            focused = next(row for row in view["rows"] if row["focused"])
                            self.assertEqual(focused["label"], i18n.text(code, setting["label"][1:]))
                            self.assertEqual(view["detail"]["rows"][0]["v"], i18n.text(code, label[1:]))
                            nav.act("right")
                        before = self.rows()[setting["id"]]["value"]
                        nav.act("left")
                        self.assertNotEqual(self.rows()[setting["id"]]["value"], before)
                        nav.act("confirm")
                        self.assertEqual(self.rows()[setting["id"]]["value"], before)
                self.assertEqual(seen, targets)
                self.assertEqual(nav.toast, "")


if __name__ == "__main__":
    unittest.main()
