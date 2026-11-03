"""Source test setup is reachable by controller or mouse without executing tools."""
import unittest
from unittest import mock

from openrecomp.adapters.base import Adapter
from openrecomp.nav import Game, Nav
from test_nav import Fake, manifest
from test_t4_beta_navigation import Direct


class SourceSetup(Fake):
    def __init__(self):
        super().__init__(manifest("t4", adapter="t4"), is_ready=False)
        self.tool_rows = [dict(id="git", label="Git", value="@missing", ok=False,
                              command="winget install --id Git.Git --exact --source winget")]
        self.build_snapshot = dict(running=False, fraction=0, title="", steps=[], result="", line="")

    def prerequisites(self):
        return [dict(row) for row in self.tool_rows]

    def refresh_prerequisites(self):
        self.calls.append(("tools",))

    def build_state(self):
        return dict(self.build_snapshot)


class BundleNavigation(unittest.TestCase):
    def nav_for(self, adapter, section):
        nav = Nav([Game(adapter.m, adapter)], language="de")
        nav.screen = "hub"
        nav.sec["t4"] = section
        return nav

    def choose(self, nav, iid):
        for _ in range(100):
            items = nav.items()
            if items[nav.focus_index(items)].get("id") == iid:
                nav.act("confirm", device="xbox")
                return
            nav.act("down", device="xbox")
        self.fail("controller could not reach " + iid)

    def test_base_checks_are_optional(self):
        adapter = Adapter(dict(id="other"))
        self.assertEqual(adapter.prerequisites(), [])
        self.assertIsNone(adapter.refresh_prerequisites())

    def test_missing_tools_are_no_row_build_installs_them(self):
        adapter = SourceSetup()
        nav = self.nav_for(adapter, "build")
        ids = [row.get("id") for row in nav.items()]
        self.assertEqual([i for i in ids if str(i).startswith("tool")], [], "the launcher installs them at Build")
        self.choose(nav, "build")
        self.assertEqual(adapter.calls, [("build", False)])

    def test_mouse_reaches_help_after_a_failed_install(self):
        adapter = SourceSetup()
        adapter.build_snapshot.update(failed="tools", result="@t4.tools.install_failed")
        nav = self.nav_for(adapter, "build")
        nav.device = "kb"
        index = next(i for i, row in enumerate(nav.items()) if row.get("id") == "tools:help")
        nav.click_row(index)
        self.assertEqual(nav.confirm_kind, "tools_help")
        self.assertIn("Git", nav.view()["dialog"]["text"])
        nav.act("right", device="kb")
        nav.copy_text = mock.Mock()
        nav.act("confirm", device="kb")
        nav.copy_text.assert_called_once_with(adapter.tool_rows[0]["command"])

    def test_no_tool_rows_during_a_build_or_while_checking(self):
        adapter = SourceSetup()
        nav = self.nav_for(adapter, "build")
        adapter.build_snapshot.update(running=True, failed="tools")
        self.assertFalse([row for row in nav.items() if str(row.get("id", "")).startswith("tools")])
        adapter.build_snapshot.update(running=False, failed="")
        adapter.tool_rows[0].update(busy=True, command="")
        self.assertFalse([row for row in nav.items() if str(row.get("id", "")).startswith("tools")])

    def test_dry_build_does_not_touch_the_pc(self):
        adapter = SourceSetup()
        adapter.install_prerequisites = mock.Mock(return_value=True)
        nav = self.nav_for(adapter, "build")
        nav.dry = True
        self.choose(nav, "build")
        adapter.install_prerequisites.assert_not_called()
        self.assertEqual(adapter.calls, [])

    def test_built_source_has_controller_route_to_online(self):
        adapter = SourceSetup()
        adapter.is_ready = True
        nav = self.nav_for(adapter, "build")
        self.choose(nav, "online_setup")
        self.assertEqual(nav.section(), "online")
        self.assertEqual(adapter.calls, [])

    def test_network_instructions_identity_and_log_path_are_focusable(self):
        adapter = Direct()
        adapter.snapshot.update(build_id="0123456789abcdef", compiler="MSVC 19.44",
                                log_path="@on")
        nav = self.nav_for(adapter, "online")
        for iid, expected in (("direct:build_id", "0123456789abcdef"),
                              ("direct:compiler", "MSVC 19.44"), ("direct:log_path", "@on")):
            nav.focus["t4:online"] = 0
            self.choose(nav, iid)
            self.assertEqual(nav.view()["detail"]["lead"], expected)
        for step in ("firewall", "forward", "tailscale", "check"):
            nav.focus["t4:online"] = 0
            self.choose(nav, "network:" + step)
            detail = nav.view()["detail"]
            self.assertEqual(detail["leadLines"], 10)
            self.assertTrue(detail["lead"])
        self.assertEqual(adapter.calls, [])
        ids = {row.get("id") for row in nav.items()}
        self.assertFalse({"search_ranked", "login_guest", "return_lobby"} & ids)


if __name__ == "__main__":
    unittest.main()
