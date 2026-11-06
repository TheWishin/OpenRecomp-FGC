"""The launcher's own Settings page (0.1.5): reachable from Quick access and the top bar, its rows, start with Windows
through a fake registry layer (the real registry is never touched), button prompt style, update channel."""
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp import i18n, launcher_prefs
from openrecomp.app import Backend
from openrecomp.nav import Game, Nav
from test_nav import Fake, manifest


class FakeRegistry:
    def __init__(self, fail=False):
        self.values, self.fail = {}, fail

    def get(self, name):
        return self.values.get(name)

    def set(self, name, value):
        if self.fail:
            raise OSError("denied")
        self.values[name] = value

    def delete(self, name):
        if self.fail:
            raise OSError("denied")
        self.values.pop(name, None)


class PrefsLayer(unittest.TestCase):
    def test_startup_writes_one_per_user_value_and_removes_it_again(self):
        reg = FakeRegistry()
        self.assertFalse(launcher_prefs.startup_enabled(reg))
        self.assertTrue(launcher_prefs.set_startup(True, reg, command='"C:\\x y\\pythonw.exe" -B -m openrecomp'))
        self.assertEqual(list(reg.values), [launcher_prefs.RUN_NAME])
        self.assertTrue(launcher_prefs.startup_enabled(reg))
        self.assertTrue(launcher_prefs.set_startup(False, reg))
        self.assertEqual(reg.values, {})
        self.assertTrue(launcher_prefs.set_startup(False, reg))          # already off: still fine

    def test_a_refused_registry_is_false_not_an_exception(self):
        reg = FakeRegistry(fail=True)
        self.assertFalse(launcher_prefs.set_startup(True, reg, command="x"))
        self.assertFalse(launcher_prefs.startup_enabled(reg))

    def test_the_command_is_quoted_and_starts_the_launcher_module(self):
        with tempfile.TemporaryDirectory() as program:
            os.makedirs(os.path.join(program, "portable"))
            open(os.path.join(program, "portable", "pythonw.exe"), "w").close()
            command = launcher_prefs.startup_command(program)
        self.assertTrue(command.startswith('"') and command.endswith("-B -m openrecomp"))
        self.assertIn("pythonw.exe", command)

    def test_the_real_key_is_the_current_users_run_key(self):
        self.assertTrue(launcher_prefs.RUN_KEY.endswith(r"CurrentVersion\Run"))
        with open(launcher_prefs.__file__, encoding="utf-8") as stream:
            source = stream.read()
        self.assertIn("HKEY_CURRENT_USER", source)
        self.assertNotIn("HKEY_LOCAL_MACHINE", source)

    def test_open_folder_creates_it_and_uses_the_given_opener(self):
        seen = []
        with tempfile.TemporaryDirectory() as temp:
            folder = os.path.join(temp, "data")
            self.assertTrue(launcher_prefs.open_folder(folder, seen.append))
            self.assertTrue(os.path.isdir(folder))
        self.assertEqual(seen, [folder])


class Page(unittest.TestCase):
    def setUp(self):
        self.adapters = [Fake(manifest(gid)) for gid in ("a", "b")]
        self.games = [Game(a.m, a) for a in self.adapters]
        self.calls = []
        self.info = dict(startup=False, data_dir="C:\\Data\\OpenRecomp", prompt_style="auto")
        self.nav = Nav(self.games, language="en", fullscreen=True, on_ui_sound=lambda on, vol: None,
                       on_update_check=lambda: None, on_setup=lambda *a: None)
        self.nav.on_launcher = self.launcher
        self.nav.on_uninstall = lambda action, keep: {}

    def launcher(self, action, value):
        self.calls.append((action, value))
        if action == "get":
            return dict(self.info)
        if action == "startup":
            self.info["startup"] = bool(value)
            return True
        return True

    def row(self, rid):
        return next(it for it in self.nav._launcher_items() if it["id"] == rid)

    def go(self, rid):
        items = self.nav._launcher_items()
        self.nav.launcher_focus = next(n for n, it in enumerate(items) if it["id"] == rid)

    def test_quick_access_has_the_launcher_settings_row_and_opens_the_page(self):
        self.nav.act("social")
        view = self.nav.view()
        labels = [r["label"] for r in view["drawer"]["rows"]]
        self.assertIn("Launcher settings", labels)
        self.nav.drawer_focus = labels.index("Launcher settings")
        self.nav.act("confirm")
        view = self.nav.view()
        self.assertEqual(self.nav.screen, "launcher")
        self.assertEqual(view["screen"], "hub")
        self.assertEqual(view["overlay"], "")
        self.assertEqual(view["settingsPage"]["layout"], "groups")

    def test_next_on_the_shelf_and_the_action_open_it_and_back_returns_there(self):
        self.nav.act("next")
        self.assertEqual(self.nav.screen, "launcher")
        self.nav.act("back")
        self.nav.act("launcherSettings")
        self.assertEqual(self.nav.screen, "launcher")
        self.nav.act("back")
        self.assertEqual(self.nav.screen, "start")
        self.nav.act("confirm")                                     # into a game
        self.assertEqual(self.nav.screen, "hub")
        game_focus = dict(self.nav.focus)
        self.nav.act("launcherSettings")
        self.assertEqual(self.nav.screen, "launcher")
        self.nav.act("home")
        self.assertEqual(self.nav.screen, "hub")
        self.assertEqual(self.nav.focus, game_focus)

    def test_the_page_is_separate_from_the_games_settings_and_has_every_asked_row(self):
        self.nav.act("launcherSettings")
        ids = [it["id"] for it in self.nav._launcher_items()]
        for wanted in ("language", "display", "startup", "prompts", "ui_sounds", "ui_sound_volume", "channel",
                       "check_now", "data_dir", "uninstall_all", "version", "releases"):
            self.assertIn(wanted, ids)
        view = self.nav.view()
        tabs = [t["label"] for t in view["settingsPage"]["tabs"]]
        self.assertEqual(tabs, ["General", "Sound", "Updates", "Data", "About"])
        self.assertEqual(view["tabs"][0]["label"], "Launcher settings")
        self.assertEqual([p["action"] for p in view["prompts"]][-1], "back")

    def test_language_row_changes_the_language_and_saves_it(self):
        saved = []
        self.nav.on_language = saved.append
        self.nav.act("launcherSettings")
        self.go("language")
        self.nav.act("right")
        self.assertEqual(saved, [self.nav.language])
        self.assertNotEqual(self.nav.language, "en")

    def test_start_with_windows_goes_through_the_app_and_a_failure_is_said(self):
        self.nav.act("launcherSettings")
        self.go("startup")
        self.nav.act("confirm")
        self.assertIn(("startup", True), self.calls)
        self.assertEqual(self.row("startup")["value"], "@on")
        self.nav.on_launcher = lambda action, value: dict(self.info) if action == "get" else False
        self.go("startup")
        self.nav.act("confirm")
        self.assertIn("did not accept", self.nav.view()["toast"])

    def test_without_the_registry_the_startup_row_is_left_out(self):
        self.info["startup"] = None
        self.nav.act("launcherSettings")
        self.assertNotIn("startup", [it["id"] for it in self.nav._launcher_items()])

    def test_prompt_style_forces_the_glyphs_whatever_was_pressed_last(self):
        self.nav.act("launcherSettings", device="xbox")
        self.go("prompts")
        self.assertEqual(self.nav.view()["prompts"][0]["g"]["text"], "A")
        self.nav.act("right")                                       # Auto -> Xbox
        self.nav.act("right")                                       # -> PlayStation
        self.assertEqual(self.nav.prompt_style, "ps")
        self.assertEqual(self.nav.view()["prompts"][0]["g"]["text"], "✕")
        self.nav.act("down", device="kb")
        self.assertEqual(self.nav.glyph("confirm")["text"], "✕")
        self.nav.act("up")
        self.go("prompts")
        self.nav.act("right")                                       # -> Keyboard
        self.assertTrue(self.nav.glyph("confirm")["key"])
        self.assertIn(("prompt_style", "kb"), self.calls)

    def test_update_channel_is_the_test_versions_flag_and_check_now_runs_the_check(self):
        flags, checks = [], []
        self.nav.on_prereleases = flags.append
        self.nav.on_update_check = lambda: checks.append(1)
        self.nav.act("launcherSettings")
        self.go("channel")
        self.nav.act("right")
        self.assertEqual(flags, [True])
        self.assertEqual(self.row("channel")["value"], "@launcher_settings.channel.test")
        self.go("check_now")
        self.nav.act("confirm")
        self.assertEqual(checks, [1])

    def test_data_folder_row_opens_the_folder_and_uninstall_asks_first(self):
        self.nav.act("launcherSettings")
        self.go("data_dir")
        self.assertEqual(self.nav.view()["prompts"][0]["label"], "Open folder")
        self.assertEqual(self.nav.view()["settingsPage"]["detail"]["rows"][0]["v"], self.info["data_dir"])
        self.nav.act("confirm")
        self.assertIn(("open_data", None), self.calls)
        self.go("uninstall_all")
        self.nav.act("confirm")
        self.assertEqual(self.nav.view()["overlay"], "dialog")
        self.nav.act("back")
        self.assertEqual(self.nav.screen, "launcher")                # closing the dialog leaves the page and its row
        self.assertEqual(self.row("uninstall_all")["id"], self.nav._launcher_items()[self.nav.launcher_focus]["id"])

    def test_about_shows_the_version_and_opens_the_releases_page(self):
        from openrecomp import __version__
        self.nav.act("launcherSettings")
        self.assertEqual(self.row("version")["value"], i18n.literal(__version__))
        self.go("releases")
        self.nav.act("confirm")
        self.assertTrue(self.nav.pending_url.startswith("https://github.com/"))

    def test_next_page_jumps_through_the_tabs_and_wraps(self):
        self.nav.act("launcherSettings")
        seen = [self.nav._launcher_items()[self.nav.launcher_focus]["tab"]]
        for _ in range(5):
            self.nav.act("next")
            seen.append(self.nav._launcher_items()[self.nav.launcher_focus]["tab"])
        self.assertEqual(seen, ["general", "audio", "updates", "data", "about", "general"])

    def test_mouse_rows_and_tabs_work_and_a_dialog_blocks_them(self):
        self.nav.act("launcherSettings")
        self.nav.select_settings_tab("about")
        self.assertEqual(self.nav._launcher_items()[self.nav.launcher_focus]["tab"], "about")
        index = [it["id"] for it in self.nav._launcher_items()].index("ui_sounds")
        self.nav.click_row(index)
        self.assertFalse(self.nav.ui_sounds)

    def test_every_new_text_exists_in_every_language(self):
        keys = [k for k in i18n.catalog("en") if k.startswith("launcher_settings.")] + ["t4.iso_row", "t4.folder_row"]
        self.assertGreaterEqual(len(keys), 30)
        for language in i18n.LANGUAGES:
            catalog = i18n.catalog(language)
            for key in keys:
                self.assertTrue(catalog.get(key), (language, key))


class BackendActions(unittest.TestCase):
    def make(self, registry):
        saved = []
        stub = SimpleNamespace(registry=registry, config={}, nav=SimpleNamespace(prompt_style="auto"),
                               folder_opener=lambda path: saved.append(("open", path)),
                               _save_config=lambda: saved.append("save"))
        return stub, saved

    def test_startup_prompt_and_folder_actions(self):
        reg = FakeRegistry()
        stub, saved = self.make(reg)
        with mock.patch.object(launcher_prefs, "available", return_value=True), \
                mock.patch.object(launcher_prefs, "startup_command", return_value="cmd"):
            self.assertFalse(Backend._launcher_action(stub, "get", None)["startup"])
            self.assertTrue(Backend._launcher_action(stub, "startup", True))
            self.assertEqual(reg.values, {launcher_prefs.RUN_NAME: "cmd"})
            self.assertTrue(stub.config["start_with_windows"])
            self.assertTrue(Backend._launcher_action(stub, "startup", False))
            self.assertEqual(reg.values, {})
        self.assertTrue(Backend._launcher_action(stub, "prompt_style", "ps"))
        self.assertEqual(stub.config["prompt_style"], "ps")
        self.assertTrue(Backend._launcher_action(stub, "open_data", None))
        self.assertEqual(saved[-1][0], "open")

    def test_a_failed_registry_write_saves_nothing(self):
        stub, saved = self.make(FakeRegistry(fail=True))
        self.assertFalse(Backend._launcher_action(stub, "startup", True))
        self.assertNotIn("start_with_windows", stub.config)
        self.assertEqual(saved, [])


if __name__ == "__main__":
    unittest.main()


class CjkFonts(unittest.TestCase):
    """日本語 / 한국어 must show in the language list even where Qt lists no CJK font (0.1.5)."""

    def test_a_pc_with_a_cjk_font_is_left_alone(self):
        from openrecomp import app
        with mock.patch.object(app.QFontDatabase, "families", return_value=["Yu Gothic UI"]), \
                mock.patch.object(app.QFontDatabase, "addApplicationFont") as add:
            self.assertEqual(app.load_system_cjk_fonts("C:\none"), [])
            add.assert_not_called()

    def test_without_one_windows_own_fonts_are_loaded_and_substituted(self):
        from openrecomp import app
        with tempfile.TemporaryDirectory() as fonts:
            for name in ("YuGothM.ttc", "malgun.ttf"):
                open(os.path.join(fonts, name), "wb").close()
            with mock.patch.object(app.QFontDatabase, "families", return_value=[]), \
                    mock.patch.object(app.QFontDatabase, "addApplicationFont", return_value=3) as add, \
                    mock.patch.object(app.QFontDatabase, "applicationFontFamilies", return_value=["Yu Gothic UI"]), \
                    mock.patch.object(app.QFont, "insertSubstitutions") as subst:
                self.assertEqual(app.load_system_cjk_fonts(fonts), ["Yu Gothic UI"])
            self.assertEqual(add.call_count, 2)
            subst.assert_any_call("IBM Plex Sans", ["Yu Gothic UI"])

    def test_the_language_names_are_native_script_in_every_catalog(self):
        for language in i18n.LANGUAGES:
            self.assertEqual(i18n.catalog(language)["language.ja"], "日本語")
            self.assertEqual(i18n.catalog(language)["language.ko"], "한국어")
