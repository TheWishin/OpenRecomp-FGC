"""The same settings give the game the same environment as T4's own launcher does. A fake core stands for the
install's (its game_env maps the settings as T4's does); no game starts and no window opens."""
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp.adapters.t4 import BETA_DISABLED_SWITCHES, T4

MANIFEST = dict(id="t4", short="T4", title="T4", numeral="4", accent="#ffffff", subtitle="", sections=["settings"])
# What the runtime does by itself when a name is not set: saying it aloud changes nothing in the game.
RUNTIME_DEFAULTS = dict({name: "0" for name in BETA_DISABLED_SWITCHES},
                        TEKKEN4_NET_DIAG="0", TEKKEN4_HUD="soft", TEKKEN4_ANISO="4")


class FakeCore:
    """Settings -> environment as T4's own launcher core does it (Play offline)."""
    RESOLUTIONS = [(key, key, None) for key in ("low", "lowest", "native", "1080p", "1440p", "4k", "auto")]
    DEFAULTS = dict(resolution="auto", fullscreen=False, fullscreen_exclusive=False, sound=True, aa=True,
                    progressive=True, widescreen=False, unlock_all=True, debug_panel=False)
    SAVE_DIR = ""

    def __init__(self, **saved):
        self.saved = dict(self.DEFAULTS, **saved)
        self.launched = None

    def load_settings(self):
        return dict(self.saved)

    def save_settings(self, settings):
        self.saved = dict(settings)

    def play_problems(self, settings):
        return []

    def run_lock_holder(self):
        return ""

    def take_run_lock(self, owner):
        pass

    def graphics_support(self, exe):
        return dict(aa=True, progressive=True, fullscreen=True, widescreen=True)

    def game_env(self, s, exe=None):
        low = s.get("resolution") == "low"
        env = dict(PS2X_GS_BACKEND="gl", PS2X_GS_THREADS="auto", TEKKEN4_SOUND="1" if s.get("sound") else "0",
                   TEKKEN4_INTERNAL_RES="native" if low else s.get("resolution"),
                   TEKKEN4_AA="fxaa" if s.get("aa") and not low else "off",
                   TEKKEN4_PROGRESSIVE="1" if s.get("progressive") else "0",
                   TEKKEN4_WIDESCREEN="1" if s.get("widescreen") else "0")
        if s.get("fullscreen"):
            env["TEKKEN4_FULLSCREEN"] = "exclusive" if s.get("fullscreen_exclusive") else "1"
        if low:
            env["TEKKEN4_ANISO"] = "1"
        return env

    def GameRun(self, settings):
        def start():
            self.launched = self.game_env(settings)
        return SimpleNamespace(start=start, proc=SimpleNamespace(pid=12, poll=lambda: 0))


class LaunchParity(unittest.TestCase):
    def setUp(self):
        self.enterContext(mock.patch("openrecomp.adapters.t4.save_config"))
        self.enterContext(mock.patch("openrecomp.adapters.t4.threading.Thread"))

    def adapter(self, config=None, **saved):
        core = FakeCore(**saved)
        adapter = T4(MANIFEST, {} if config is None else config, "fake-root", core=core)
        adapter._track_playtime = lambda *args, **kwargs: None
        return core, adapter

    def differences(self, core, adapter):
        """What this launcher gives the game beyond T4's own, runtime defaults said aloud left out."""
        own = core.game_env(core.load_settings())
        adapter._start(None)
        ours = core.launched
        return {name: (own.get(name), ours.get(name)) for name in sorted(set(own) | set(ours))
                if own.get(name) != ours.get(name) and not (name not in own and RUNTIME_DEFAULTS.get(name) == ours[name])}

    def test_settings_of_the_games_own_launcher_start_the_same_game(self):
        cases = (dict(),
                 dict(fullscreen=True, resolution="1080p", aa=False, widescreen=True, progressive=False),
                 dict(resolution="low", aa=True),
                 dict(fullscreen=True, fullscreen_exclusive=True, resolution="4k", widescreen=True, sound=False))
        for saved in cases:
            with self.subTest(settings=saved):
                self.assertEqual(self.differences(*self.adapter(**saved)), {})

    def test_low_keeps_the_old_pc_preset_whatever_this_page_chose(self):
        core, adapter = self.adapter(config=dict(t4_graphics=dict(aa="ssaa4", anisotropic="16")), resolution="low")
        adapter._start(None)
        self.assertEqual((core.launched["TEKKEN4_AA"], core.launched["TEKKEN4_ANISO"]), ("off", "1"))
        adapter.set_setting("resolution", "native")
        adapter._start(None)
        self.assertEqual((core.launched["TEKKEN4_AA"], core.launched["TEKKEN4_ANISO"]), ("ssaa4", "16"))

    def test_aspect_chosen_here_is_the_games_own_setting_too(self):
        core, adapter = self.adapter()
        adapter.set_setting("aspect", "16:9")
        self.assertIs(core.saved["widescreen"], True)
        self.assertEqual(self.differences(core, adapter), {})
        self.assertEqual(core.launched["TEKKEN4_WIDESCREEN"], "1")

    def test_a_later_change_in_the_games_own_launcher_counts(self):
        config = {}
        core, adapter = self.adapter(config=config)
        adapter.set_setting("aspect", "16:9")
        adapter.set_setting("aa", "smaa")
        core.saved.update(widescreen=False, aa=False)          # T4's own launcher: 4:3, anti-aliasing off
        core, adapter = self.adapter(config=config, **core.saved)
        rows = {row["id"]: row["value"] for row in adapter.settings()}
        self.assertEqual((rows["aspect"], rows["aa"]), ("4:3", "off"))
        self.assertEqual(self.differences(core, adapter), {})

    def test_a_choice_saved_before_this_version_stays(self):
        core, adapter = self.adapter(config=dict(t4_graphics=dict(aspect="16:9")))
        adapter._start(None)
        self.assertEqual(core.launched["TEKKEN4_WIDESCREEN"], "1")


if __name__ == "__main__":
    unittest.main()
