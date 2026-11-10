"""T5DR 1.2.3 ranked costume from the launcher (T5DR docs/RANKED.md "Costumes in ranked"): announce, send, choose."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp import i18n
from openrecomp.adapters.base import Adapter
from openrecomp.adapters.t5dr import T5DR
from openrecomp.nav import Game, Nav
from test_nav import Fake, manifest


def fighters_module(new=True):
    """The install's t5lobby.fighters as 1.2.3 has it (new) or as before (no costume functions)."""
    buttons = {"jin": (1, 3, 2), "kuma": (1,), "xiaoyu": (1, 3, 2, 4), "paul": (1, 3)}

    def costume_buttons(key):
        return buttons.get(key, ())

    def costume_button(key, button):
        own = costume_buttons(key)
        return 0 if not own else button if button in own else own[0]
    return SimpleNamespace(costume_buttons=costume_buttons, costume_button=costume_button) if new else SimpleNamespace()


class CostumeAdapter(unittest.TestCase):
    def setUp(self):
        self.folder = self.enterContext(tempfile.TemporaryDirectory(dir=Path(__file__).parent))
        self.path = Path(self.folder) / "online.json"
        self.a = object.__new__(T5DR)
        self.a.online_cfg_path = lambda: str(self.path)
        self.a._online_cfg = lambda: json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        self.module = fighters_module()
        self.a._costume_table = lambda: self.module

    def test_costumes_are_the_install_s_buttons_and_one_costume_offers_no_choice(self):
        self.assertEqual([(c["button"], c["name"]) for c in self.a.costumes("jin")], [(1, "LP"), (3, "LK"), (2, "RP")])
        self.assertEqual(self.a.costumes("kuma"), [])
        self.assertEqual(self.a.costumes("random"), [])
        self.module = fighters_module(new=False)
        self.a._costume_table = T5DR._costume_table.__get__(self.a)
        with mock.patch.object(T5DR, "_online_modules", return_value={}), \
                mock.patch("openrecomp.adapters.t5dr.importlib.import_module", return_value=fighters_module(new=False)):
            self.assertEqual(self.a.costumes("jin"), [])         # an install from before 1.2.3
            self.assertEqual(self.a.chosen_costume("jin"), 0)

    def test_remembered_per_fighter_in_the_shared_online_json_beside_other_fields(self):
        self.path.write_text(json.dumps(dict(char="jin", sessions={"x": {}}, costumes={"paul": 3})), encoding="utf-8")
        self.assertEqual(self.a.chosen_costume("jin"), 1)          # nobody chose: costume 1
        self.a.set_costume("jin", 2)
        self.a.set_costume("jin", 4)                               # not one of Jin's: ignored
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved, dict(char="jin", sessions={"x": {}}, costumes={"paul": 3, "jin": 2}))
        self.assertEqual(self.a.chosen_costume("jin"), 2)
        self.a.set_fighter("paul")                                 # the fighter field still works the same way
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["costumes"], {"paul": 3, "jin": 2})


class CostumeOnline(unittest.TestCase):
    def submit(self, costume_ok):
        a = object.__new__(T5DR)
        calls = []
        client = SimpleNamespace(ranked_match=lambda char, **kw: calls.append(("ranked", char, kw)),
                                 quick_match=lambda char, **kw: calls.append(("quick", char, kw)))
        if costume_ok is not None:
            client.costume_ok = lambda: costume_ok
        a._online_client, a._online_generation = client, 1
        a.chosen_fighter = lambda: "jin"
        a.chosen_costume = lambda key: 3
        a._online_game_check = lambda: ""
        a._online_queue_lock = mock.MagicMock()
        a._online_submit = lambda _action, work: work()
        with mock.patch("openrecomp.adapters.t5_online.t5_features.enabled", return_value=False):
            a._online_search_submit("ranked")
            a._online_search_submit("casual")
        return calls

    def test_the_costume_goes_with_the_search_only_to_a_client_that_takes_it(self):
        self.assertEqual(self.submit(True), [("ranked", "jin", dict(costume=3)), ("quick", "jin", dict(costume=3))])
        self.assertEqual(self.submit(False), [("ranked", "jin", {}), ("quick", "jin", {})])
        self.assertEqual(self.submit(None), [("ranked", "jin", {}), ("quick", "jin", {})])   # an older install

    def test_the_client_option_follows_the_in_game_select(self):
        a = object.__new__(T5DR)
        a._online_out_dir = lambda: ""
        for pick in (True, False):
            module = SimpleNamespace(game_files=mock.Mock(return_value=[]), game_supports_pick=lambda _p, v=pick: v)
            a._online_driver_module = lambda m=module: m
            options = a._online_match_client_options()
            self.assertEqual(options["ranked_costume"], pick)
            self.assertEqual(options["ranked_costume"], options["ingame_pick"])


class CostumeGrid(unittest.TestCase):
    def nav(self):
        adapter = Fake(manifest("a"))
        adapter.fighters = lambda: [dict(key="jin", name="Jin", image=""), dict(key="kuma", name="Kuma", image="")]
        saved = {}
        adapter.costumes = lambda key: [dict(button=b, name=n) for b, n in ((1, "LP"), (3, "LK"), (2, "RP"))] if key == "jin" else []
        adapter.chosen_costume = lambda key: saved.get(key, 1 if key == "jin" else 0)
        adapter.set_costume = lambda key, button: saved.__setitem__(key, button)
        nav = Nav([Game(adapter.m, adapter)], language="en")
        nav.screen = "hub"
        nav._open_fighters()
        return nav, saved

    def test_x_in_the_grid_cycles_the_focused_fighter_s_costume_and_confirm_still_picks(self):
        nav, saved = self.nav()
        nav.act("right")                                            # Random -> Jin
        view = nav.view()
        self.assertEqual(view["grid"]["costume"]["value"], "Costume 1 (LP)")
        self.assertIn("x", [p["action"] for p in view["prompts"]])
        for expected in (3, 2, 1):
            nav.act("x")
            self.assertEqual(saved["jin"], expected)
        nav.act("x")
        self.assertEqual(i18n.localize(nav.view()["grid"]["costume"]["value"], "en"), "Costume 2 (LK)")
        self.assertEqual(nav.overlay, "fighters")                  # X does not close the grid
        nav.act("right")                                            # Kuma: one costume, nothing to choose
        self.assertFalse(nav.view()["grid"]["costume"]["show"])
        nav.act("x")
        self.assertEqual(saved, {"jin": 3})
        nav.act("left")
        nav.act("confirm")
        self.assertIsNone(nav.overlay)

    def test_games_without_costumes_keep_the_old_grid_and_texts_exist_in_every_catalog(self):
        adapter = Fake(manifest("a"))
        adapter.fighters = lambda: [dict(key="f1", name="One", image="")]
        nav = Nav([Game(adapter.m, adapter)], language="en")
        nav._open_fighters()
        nav.act("right")
        self.assertFalse(nav.view()["grid"]["costume"]["show"])
        self.assertNotIn("x", [p["action"] for p in nav.view()["prompts"]])
        self.assertEqual(Adapter.costumes(adapter, "f1"), [])
        for code in i18n.LANGUAGES:
            for key in ("fighter.costume", "fighter.costume_value", "fighter.costume_change", "fighter.costume_hint"):
                self.assertTrue(i18n.catalog(code).get(key), (code, key))


if __name__ == "__main__":
    unittest.main()
