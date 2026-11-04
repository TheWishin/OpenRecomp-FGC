"""Player identities use their own normalized main, including unknown silhouettes."""
from pathlib import Path
import os
import subprocess
import sys
import unittest

from openrecomp.nav_common import uri
from test_online_hierarchy import hierarchy_nav


class PlayerPictureSurfaces(unittest.TestCase):
    def setup_nav(self, language="en", t4=False):
        adapter, nav = hierarchy_nav(language, t4)
        self.images = []

        def image(key):
            self.images.append(key)
            return str(Path(__file__).resolve().parent / (key + ".png"))

        adapter.fighter_image = image
        adapter.snapshot["me"]["main"] = "local-main"
        adapter.snapshot["profile"] = dict(name="Other", main="profile-main", history=[])
        adapter.snapshot["friends"] = [dict(name="Friend", main="friend-main", status="online", invite=True),
                                       dict(name="New player", status="offline")]
        adapter.snapshot["leaderboard"] = dict(rows=[dict(name="Leader", place=1, main="leader-main"),
                                                          dict(name="New player", place=2)])
        return adapter, nav

    def expected(self, key):
        return uri(str(Path(__file__).resolve().parent / (key + ".png")))

    def test_loaded_profile_and_friend_pictures_belong_to_that_player(self):
        for language in ("en", "de"):
            for t4 in (False, True):
                with self.subTest(language=language, t4=t4):
                    adapter, nav = self.setup_nav(language, t4)
                    nav._t5_profile_pages = {nav.game.id: "profile"}
                    nav.click_chapter("profile")
                    page = nav.view()["online"]
                    self.assertEqual(page["profile"]["face"], self.expected("local-main"))
                    summary = next(row for section in page["body"]["sections"] for row in section["lines"]
                                   if row.get("id") == "profile_summary")
                    self.assertTrue(summary["playerPortrait"])
                    self.assertEqual(summary["face"], self.expected("profile-main"))
                    nav.click_chapter("friends")
                    rows = [row for section in nav.view()["online"]["body"]["sections"] for row in section["lines"]]
                    buttons = [button for row in rows for button in row.get("buttons", [])]
                    friend = next(row for row in buttons if row["id"] == "invite_friend:Friend")
                    self.assertEqual(friend["face"], self.expected("friend-main"))
                    unknown = next(row for row in buttons if row["id"] == "remove_friend:New player")
                    self.assertTrue(unknown["playerPortrait"])
                    self.assertEqual(unknown["face"], "")
                    self.assertNotIn("", self.images)
                    self.assertEqual(adapter.calls, [])

    def test_leaderboard_rows_podium_and_local_position_have_independent_pictures(self):
        adapter, nav = self.setup_nav()
        nav._t5_profile_pages = {nav.game.id: "leaderboard"}
        nav.click_chapter("leaderboard")
        board = nav.view()["online"]["leaderboard"]
        self.assertEqual(board["rows"][0]["face"], self.expected("leader-main"))
        self.assertEqual(board["podium"][0]["face"], self.expected("leader-main"))
        self.assertEqual(board["rows"][1]["face"], "")
        self.assertEqual(board["own"]["face"], self.expected("local-main"))
        self.assertEqual(adapter.calls, [])

    def test_unknown_profile_never_borrows_local_picture(self):
        adapter, nav = self.setup_nav()
        adapter.snapshot["profile"].pop("main")
        nav._t5_profile_pages = {nav.game.id: "profile"}
        nav.click_chapter("profile")
        summary = next(item for item in nav.items() if item.get("id") == "profile_summary")
        self.assertTrue(summary["playerPortrait"])
        self.assertEqual(summary["face"], "")

    def test_unknown_player_silhouettes_render_on_profile_friends_and_ranking(self):
        script = '''
from pathlib import Path
import sys
sys.path.insert(0, str(Path("tests").resolve()))
from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from tools.online_shots import scene, snapshot
from test_ui_loads import FakeBackend, spin, wait_pages
app = QGuiApplication([])
backend = FakeBackend(scene("t5", "profile", "en"))
engine = QQmlApplicationEngine()
warnings = []
engine.warnings.connect(lambda messages: warnings.extend(m.toString() for m in messages))
engine.setInitialProperties(dict(backend=backend, wantFull=False))
engine.load(QUrl.fromLocalFile(str(Path("openrecomp/ui/Main.qml").resolve())))
assert engine.rootObjects(), warnings
window = engine.rootObjects()[0]
def descendants(item):
    for child in item.childItems():
        yield child
        yield from descendants(child)
for chapter, portrait in (("profile", "onlinePlayerPortrait"), ("friends", "onlinePlayerPortrait"),
                          ("leaderboard", "rankingPlayerPortrait")):
    backend.nav = scene("t5", chapter, "en")
    backend._v = snapshot(backend.nav)
    backend.viewChanged.emit()
    wait_pages(window)
    spin(30)
    pictures = [child for child in descendants(window.contentItem())
                if child.objectName() == portrait and child.isVisible()]
    assert pictures, chapter
    assert all(not item.property("source").toString() for item in pictures), chapter
assert not warnings, warnings
window.setProperty("allowClose", True)
window.close()
'''
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QML_DISABLE_DISK_CACHE="1")
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=20, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
