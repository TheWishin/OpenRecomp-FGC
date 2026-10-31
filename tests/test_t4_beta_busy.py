"""Local diagnostic workers cannot be interrupted by an update or install reload."""
from types import SimpleNamespace
import unittest

from openrecomp.app import Backend
from openrecomp.adapters.base import Adapter
from openrecomp.nav import Game, Nav


class BetaBusyTests(unittest.TestCase):
    def setUp(self):
        manifest = dict(id="t4", short="T4", accent="#ffffff", sections=["online"])
        self.adapter = Adapter(manifest)
        self.state = dict(phase="offline", busy=True)
        self.adapter.online_state = lambda: dict(self.state)
        self.nav = Nav([Game(manifest, self.adapter)])

    def test_local_log_collection_blocks_update_restart(self):
        backend = SimpleNamespace(nav=self.nav)
        for phase in ("offline", "error"):
            self.state["phase"] = phase
            self.assertTrue(Backend._update_busy(backend))
        self.state["busy"] = False
        self.assertFalse(Backend._update_busy(backend))

    def test_local_log_collection_blocks_library_reload_and_update_offer(self):
        self.assertTrue(self.nav._update_busy())
        self.assertFalse(self.nav.can_reload_games())
        self.nav.update_state = dict(phase="available", version="v1.0.0")
        self.assertFalse(self.nav.offer_update())
        self.state["busy"] = False
        self.assertTrue(self.nav.can_reload_games())
        self.assertTrue(self.nav.offer_update())


if __name__ == "__main__":
    unittest.main()
