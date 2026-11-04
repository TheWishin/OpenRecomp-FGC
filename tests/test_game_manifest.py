"""Manifest version 2 (openrecomp/game_manifest.py, adapters/manifest_game.py) and games/tag2.json.

Inert files only: the "games" are empty .exe names and text files in temporary folders; no game is started.
"""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from openrecomp import adapters, game_manifest as gm, game_releases as gr, manifest as mf  # noqa: E402
from openrecomp.adapters import manifest_game as mg  # noqa: E402
import release_fixtures as rf  # noqa: E402

TAG2 = json.loads((ROOT / "games" / "tag2.json").read_text(encoding="utf-8"))


def minimal(**extra):
    m = {"schema_version": 2, "id": "demo", "title": "Demo Game", "platform": "PC", "numeral": "D",
         "accent": "#123456", "start": {"exe": "bin/demo.exe"}}
    m.update(extra)
    return m


class Home(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        patcher = mock.patch.dict(os.environ, {"OPENRECOMP_HOME": str(self.base / "home"),
                                               "USERPROFILE": str(self.base / "profile")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def game_folder(self, name="Demo", files=("bin/demo.exe",)):
        root = self.base / "profile" / "Downloads" / name
        for f in files:
            (root / f).parent.mkdir(parents=True, exist_ok=True)
            (root / f).write_bytes(b"x")
        return root


class ValidateTest(unittest.TestCase):
    def test_the_shipped_tag2_manifest_is_valid_without_warnings(self):
        m, warnings = gm.validate(copy.deepcopy(TAG2), builtin=True)
        self.assertEqual(warnings, [])
        self.assertEqual((m["adapter"], m["code_adapter"], m["shelf"]), ("manifest", "tag2", "found"))
        self.assertEqual(m["updates"]["verification"], {"method": "github-sha256"})
        self.assertEqual(set(TAG2["online"]["note"]), set(gm.LANGS))

    def test_a_players_file_may_not_name_launcher_code(self):
        with self.assertRaisesRegex(gm.ManifestError, "code_adapter"):
            gm.validate(copy.deepcopy(TAG2), builtin=False)
        user = copy.deepcopy(TAG2)
        del user["code_adapter"]
        gm.validate(user, builtin=False)

    def test_unknown_fields_are_warned_and_ignored(self):
        m, warnings = gm.validate(minimal(colour="red", start={"exe": "a.exe", "shell": "cmd"}))
        self.assertEqual(warnings, ["colour: unknown field, ignored", "start.shell: unknown field, ignored"])
        self.assertEqual(m["start"]["exe"], "a.exe")

    def test_refusals_name_the_field(self):
        cases = {
            "start.exe": minimal(start={"exe": "../evil.exe"}),
            "start.exe ": minimal(start={"exe": "C:/Windows/notepad.exe"}),
            "start.exe  ": minimal(start={"exe": "run.cmd"}),
            "start.env.PATH": minimal(start={"exe": "a.exe", "env": {"PATH": "x"}}),
            "start.env.PYTHONPATH": minimal(start={"exe": "a.exe", "env": {"PYTHONPATH": "x"}}),
            "install.search[0]": minimal(install={"search": ["C:/Games/*"]}),
            "install.search[0] ": minimal(install={"search": ["%USERPROFILE%/*/x"]}),
            "art.file": minimal(art={"file": "logo.svg"}),
            "art.cache": minimal(art={"cache": "../x.png"}),
            "updates.verification.key": minimal(updates=dict(repository="a/b", repository_id="1", asset="g-{version}.zip",
                                                             verification={"method": "ed25519", "key": "zz"})),
            "updates.asset": minimal(updates=dict(repository="a/b", repository_id="1", asset="game.zip",
                                                  verification={"method": "unsigned"})),
            "updates.repository_id": minimal(updates=dict(repository="a/b", repository_id="x", asset="g-{tag}.zip",
                                                          verification={"method": "unsigned"})),
            "settings[0].target": minimal(settings=[{"id": "s", "label": "S", "type": "toggle", "target": {}}]),
            "settings[0].target.arg": minimal(settings=[{"id": "s", "label": "S", "type": "toggle", "target": {"arg": "--x"}}]),
            "settings[0].default": minimal(settings=[{"id": "s", "label": "S", "type": "choice", "default": 3,
                                                      "options": [{"value": 1, "label": "a"}], "target": {"env": "GAME_S"}}]),
            "settings[0].target.ini": minimal(settings=[{"id": "s", "label": "S", "type": "toggle",
                                                         "target": {"ini": "../x.ini", "section": "a", "key": "b"}}]),
            "settings[0].label": minimal(settings=[{"id": "s", "label": {"de": "nur Deutsch"}, "type": "toggle",
                                                    "target": {"env": "GAME_S"}}]),
            "id": minimal(id="t5dr"),
            "online.mode": minimal(online={"mode": "lobby"}),
            "shelf": minimal(shelf="sometimes"),
            "schema_version": minimal(schema_version=3),
        }
        for field, m in cases.items():
            with self.subTest(field=field), self.assertRaises(gm.ManifestError) as cm:
                gm.validate(m)
            self.assertTrue(str(cm.exception).startswith(field.strip()), str(cm.exception))


class LoadTest(Home):
    def write(self, folder, name, data):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")

    def test_broken_manifests_stay_on_the_shelf_with_the_reason(self):
        games = Path(mf.user_games_dir())
        self.write(games, "demo.json", minimal(start={"exe": "../evil.exe"}))
        self.write(games, "extra.json", minimal(id="extra", colour="red"))
        manifests, problems = mf.load_all()
        by_id = {m["id"]: m for m in manifests}
        self.assertEqual(by_id["demo"]["adapter"], "broken")
        self.assertIn("demo.json: start.exe", by_id["demo"]["broken"])
        self.assertEqual(by_id["extra"]["adapter"], "manifest")
        self.assertIn("extra.json: colour: unknown field, ignored", problems)
        a = adapters.make(by_id["demo"], {})
        self.assertEqual(type(a).__name__, "Broken")
        self.assertEqual(a.status()["status"], "@manifest.broken")
        self.assertIn("start.exe", a.problem["_literal"])
        self.assertFalse(a.found())

    def test_a_players_tag2_file_with_code_is_broken_not_trusted(self):
        self.write(Path(mf.user_games_dir()), "tag2.json", TAG2)
        manifests, problems = mf.load_all()
        tag2 = next(m for m in manifests if m["id"] == "tag2")
        self.assertEqual(tag2["adapter"], "manifest")          # the bundled one stays: a broken file never replaces it
        self.assertTrue(tag2["builtin"])
        self.assertTrue(any("code_adapter" in p for p in problems))

    def test_bundled_tag2_without_its_adapter_is_a_manifest_game_hidden_until_found(self):
        manifests, problems = mf.load_all()
        tag2 = next(m for m in manifests if m["id"] == "tag2")
        self.assertEqual(problems, [])
        a = adapters.make(tag2, {})
        self.assertEqual(type(a).__name__, "ManifestGame")        # no tag2 adapter on this launcher
        self.assertFalse(a.found())
        from openrecomp.app import load_games
        self.assertNotIn("tag2", [g.m["id"] for g in load_games({})[0]])
        root = self.game_folder("TAG2-PC", files=("Tag2Launcher.exe", "README.txt"))
        (root / "README.txt").write_text("TAG2 PC 0.16.28 - build 44 - Preview\n", encoding="utf-8")
        self.assertIn("tag2", [g.m["id"] for g in load_games({})[0]])
        a = adapters.make(tag2, {})
        self.assertEqual(a.root, str(root))
        self.assertTrue(a.ready())
        self.assertEqual(a.installed_version(), "0.16.28")
        (root / "state.json").write_text(json.dumps(dict(highest_version="0.16.33")), encoding="utf-8")
        self.assertEqual(a.installed_version(), "0.16.33")


class FakeProc:
    def __init__(self, ends_on_close=True):
        self.pid, self.code, self.ends_on_close, self.terminated = 4242, None, ends_on_close, False

    def poll(self):
        return self.code

    def wait(self, timeout=None):
        import subprocess
        if self.code is None:
            raise subprocess.TimeoutExpired("x", timeout)
        return self.code

    def terminate(self):
        self.terminated, self.code = True, 1


class PlayTest(Home):
    SETTINGS = [
        {"id": "scale", "label": {"en": "Scale", "de": "Skalierung"}, "type": "choice", "default": 1,
         "options": [{"value": 1, "label": "1x"}, {"value": 2, "label": "2x"}], "target": {"arg": "--scale={value}"}},
        {"id": "vsync", "label": "VSync", "type": "toggle", "default": True, "target": {"env": "DEMO_VSYNC"}},
        {"id": "window", "label": "Windowed", "type": "toggle", "target": {"ini": "cfg/game.ini", "section": "Display", "key": "Windowed"}},
        {"id": "lang", "label": "Language", "type": "choice", "options": [{"value": "en", "label": "English"},
                                                                          {"value": "ja", "label": "Japanese"}],
         "target": {"json": "settings.json", "key": "language"}},
    ]

    def game(self, procs, **extra):
        root = self.game_folder()
        (root / "cfg").mkdir()
        (root / "cfg" / "game.ini").write_bytes(b"; mine\r\n[Display]\r\nWidth=1280\r\n\r\n[Audio]\r\nVolume=7\r\n")
        (root / "settings.json").write_text(json.dumps(dict(language="en", other=5)), encoding="utf-8")
        m, _ = gm.validate(minimal(install={"detect": ["bin/demo.exe"], "search": ["%USERPROFILE%/Downloads/Dem*"]},
                                   start={"exe": "bin/demo.exe", "args": ["--fast"], "cwd": "bin", "env": {"DEMO_MODE": "1"}},
                                   stop={"close_window_seconds": 2}, settings=self.SETTINGS, **extra))
        calls = []

        def popen(argv, **kw):
            calls.append((argv, kw))
            return procs.pop(0)
        config = {"language": "de"}
        return mg.ManifestGame(m, config, popen=popen, close=lambda pid: 1), calls, root, config

    def test_start_with_arguments_environment_and_settings(self):
        a, calls, root, config = self.game([FakeProc()])
        self.assertTrue(a.ready())
        a.set_setting("scale", 2)
        a.set_setting("vsync", False)
        self.assertEqual(config["manifest_settings"]["demo"], {"scale": 2, "vsync": False})
        a.start()
        argv, kw = calls[0]
        self.assertEqual(argv, [str(root / "bin" / "demo.exe"), "--fast", "--scale=2"])
        self.assertEqual(kw["cwd"], str(root / "bin"))
        self.assertFalse(kw["shell"])
        self.assertEqual((kw["env"]["DEMO_MODE"], kw["env"]["DEMO_VSYNC"]), ("1", "0"))
        self.assertEqual(kw["env"]["PATH"], os.environ["PATH"])
        self.assertEqual([s["label"]["_literal"] for s in a.settings()][0], "Skalierung")     # the launcher's language

    def test_ini_and_json_settings_change_only_their_line(self):
        a, _calls, root, _config = self.game([])
        values = {s["id"]: s["value"] for s in a.settings()}
        self.assertEqual((values["window"], values["lang"]), (False, "en"))
        a.set_setting("window", True)
        a.set_setting("lang", "ja")
        self.assertEqual((root / "cfg" / "game.ini").read_bytes(),
                         b"; mine\r\n[Display]\r\nWidth=1280\r\nWindowed=1\r\n\r\n[Audio]\r\nVolume=7\r\n")
        self.assertEqual(json.loads((root / "settings.json").read_text(encoding="utf-8")), dict(language="ja", other=5))
        values = {s["id"]: s["value"] for s in a.settings()}
        self.assertEqual((values["window"], values["lang"]), (True, "ja"))
        a.set_setting("window", False)
        self.assertIn(b"Windowed=0\r\n", (root / "cfg" / "game.ini").read_bytes())
        with self.assertRaises(RuntimeError):
            a.set_setting("lang", "fr")                 # not one of the options

    def test_stop_asks_the_window_first_then_ends_the_game(self):
        closed = FakeProc()
        a, _calls, _root, _config = self.game([closed])
        a.close_windows = lambda pid: (setattr(closed, "code", 0), 1)[1]       # the game closes on WM_CLOSE
        a.start()
        a.stop()
        for _ in range(200):
            if a.stopping is None:
                break
            import time
            time.sleep(0.01)
        self.assertEqual(closed.code, 0)
        self.assertFalse(closed.terminated)

        stuck = FakeProc()
        a.proc = stuck
        a.close_windows = lambda pid: 1
        a.m = dict(a.m, stop={"close_window_seconds": 1})
        a.stop()
        a.stop()                                      # a second Stop ends it at once
        self.assertTrue(stuck.terminated)

    def test_stop_without_close_time_ends_at_once(self):
        a, _calls, _root, _config = self.game([FakeProc()])
        a.m = dict(a.m, stop={})
        a.start()
        a.stop()
        self.assertTrue(a.proc.terminated)

    def test_folder_choice_must_hold_the_detected_files(self):
        a, _calls, root, config = self.game([])
        other = self.base / "elsewhere"
        other.mkdir()
        with self.assertRaises(RuntimeError):
            a.set_source("folder", str(other))
        self.assertEqual(a.set_source("folder", str(root)), "reload")
        self.assertEqual(config["roots"]["demo"], os.path.realpath(root))

    def test_tile_picture_only_from_the_players_files(self):
        a, _calls, root, _config = self.game([], art={"cache": "hero.png", "file": "pics/tile.png"})
        self.assertEqual(a.hero(), "")
        (root / "pics").mkdir()
        (root / "pics" / "tile.png").write_bytes(b"\x89PNG")
        self.assertEqual(a.hero(), str(root / "pics" / "tile.png"))
        cache = Path(mf.art_dir("demo")) / "hero.png"
        cache.parent.mkdir(parents=True)
        cache.write_bytes(b"\x89PNG")
        self.assertEqual(a.hero(), str(cache))

    def test_external_online_starts_the_game(self):
        a, calls, _root, _config = self.game([FakeProc()], online={"mode": "external", "note": "Their servers."})
        items = a.online_items()
        self.assertEqual([i["id"] for i in items], ["own"])
        self.assertEqual(items[0]["hint"], {"_literal": "Their servers."})
        a.run_online("own")
        self.assertEqual(len(calls), 1)


class FakeGitHubOpener:
    """game_releases' opener over a dict {url: bytes}."""

    def __init__(self, files):
        self.files, self.asked = files, []

    def __call__(self, src, url, kind="download", headers=None, timeout=None):
        self.asked.append(url)
        if not gr.url_allowed(src, url, kind):
            raise gr.ReleaseError("@setup.err_foreign", url)
        if url not in self.files:
            import urllib.error
            raise urllib.error.HTTPError(url, 404, "nf", {}, None)
        data = self.files[url]

        class R(io.BytesIO):
            headers = {"Content-Length": str(len(data))}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return R(data)


class UpdateCheckTest(Home):
    REPO, RID = "author/demo", "987654"

    def release(self, tag, method, seed=rf.TEST_SEED):
        name = f"Demo-{tag[1:]}.zip"
        data = b"zip bytes of " + tag.encode()
        dl = f"https://github.com/{self.REPO}/releases/download/{tag}/"
        assets = [dict(name=name, size=len(data), browser_download_url=dl + name,
                       digest="sha256:" + hashlib.sha256(data).hexdigest())]
        files = {}
        if method == "ed25519":
            sums = f"{hashlib.sha256(data).hexdigest()}  {name}\n".encode("ascii")
            sig = gr_sig(self.m["id"], tag[1:], sums, seed)
            files.update({dl + "SHA256SUMS": sums, dl + "SHA256SUMS.sig": sig})
            assets += [dict(name="SHA256SUMS", size=len(sums), browser_download_url=dl + "SHA256SUMS"),
                       dict(name="SHA256SUMS.sig", size=len(sig), browser_download_url=dl + "SHA256SUMS.sig")]
        api = json.dumps(dict(tag_name=tag, draft=False, prerelease=False, name=f"Demo {tag}", assets=assets)).encode()
        files[f"https://api.github.com/repos/{self.REPO}/releases/latest"] = api
        return files

    def game(self, method, version="1.0.0"):
        root = self.game_folder(files=("bin/demo.exe", "version.json"))
        (root / "version.json").write_text(json.dumps(dict(version=version)), encoding="utf-8")
        verification = {"method": method}
        if method == "ed25519":
            verification["key"] = rf.public_key().hex()
        self.m, _ = gm.validate(minimal(install={"search": ["%USERPROFILE%/Downloads/Demo"]}, updates=dict(
            repository=self.REPO, repository_id=self.RID, asset="Demo-{version}.zip", verification=verification,
            installed_version=[{"file": "version.json", "json_key": "version"}])))
        return root

    def check(self, files):
        a = mg.ManifestGame(self.m, {}, fetch=FakeGitHubOpener(files))
        self.assertTrue(a.check_updates(wait=True))
        return a

    def test_github_digest_release_newer_is_offered(self):
        self.game("github-sha256")
        a = self.check(self.release("v1.1.0", "github-sha256"))
        self.assertEqual(a.update_offer()["version"], "1.1.0")
        self.assertEqual(a.status()["status"], "@setup.update_available")
        self.assertEqual(a.status()["detail"]["_text"], "manifest.update_available")
        self.assertFalse(a.check_updates(wait=True))           # cached for an hour
        again = mg.ManifestGame(self.m, {})
        self.assertEqual(again.update_offer()["version"], "1.1.0")

    def test_not_newer_is_not_offered(self):
        self.game("github-sha256", version="1.1.0")
        self.assertIsNone(self.check(self.release("v1.1.0", "github-sha256")).update_offer())

    def test_signed_release_only_with_the_right_key(self):
        self.game("ed25519")
        a = self.check(self.release("v1.1.0", "ed25519"))
        self.assertEqual(a.update_offer()["version"], "1.1.0")
        self.assertTrue(a.update_offer()["signed"])
        Path(gm._cache_path()).unlink()
        b = self.check(self.release("v1.1.0", "ed25519", seed=bytes(range(1, 33))))
        self.assertIsNone(b.update_offer())
        self.assertEqual(b.update["error"], "@setup.err_signature")

    def test_unsigned_says_so(self):
        self.game("unsigned")
        a = self.check(self.release("v2.0.0", "unsigned"))
        self.assertEqual(a.status()["detail"]["_text"], "manifest.update_unsigned")

    def test_downloads_only_from_the_repository(self):
        self.game("github-sha256")
        files = self.release("v1.1.0", "github-sha256")
        api = f"https://api.github.com/repos/{self.REPO}/releases/latest"
        data = json.loads(files[api])
        data["assets"][0]["browser_download_url"] = "https://example.com/Demo-1.1.0.zip"
        files[api] = json.dumps(data).encode()
        a = self.check(files)
        self.assertIsNone(a.update_offer())
        self.assertEqual(a.update["error"], "@setup.err_release")


def gr_sig(game_id, version, sums, seed):
    """SHA256SUMS.sig in the manifest default format (the T4 envelope with the manifest's statement)."""
    public = rf.public_key(seed)
    statement = (f"OpenRecomp-game-release-signature-v1:{game_id}\nversion={version}\n"
                 f"sums-sha256={hashlib.sha256(sums).hexdigest()}\n").encode("utf-8")
    return json.dumps(dict(format="openrecomp-game-sig/1", version=version, key=hashlib.sha256(public).hexdigest()[:16],
                           signature=rf.sign(statement, seed).hex())).encode("utf-8")


class IniTest(unittest.TestCase):
    def test_new_section_and_bom_kept(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.ini")
            Path(p).write_bytes(b"\xef\xbb\xbf[A]\nx=1\n")
            gm.ini_write(p, "B", "y", "2")
            self.assertEqual(Path(p).read_bytes(), b"\xef\xbb\xbf[A]\nx=1\n\n[B]\ny=2\n")
            self.assertEqual(gm.ini_read(p, "b", "Y"), "2")
            gm.ini_write(os.path.join(d, "new.ini"), "S", "k", "v")
            self.assertEqual(Path(d, "new.ini").read_bytes(), b"[S]\nk=v\n")


class DocsTest(unittest.TestCase):
    def test_the_doc_shows_the_shipped_tag2_manifest(self):
        doc = (ROOT / "docs" / "ADD_A_GAME.md").read_text(encoding="utf-8")
        block = doc[doc.index("```json\n{\n \"schema_version\": 2,\n \"id\": \"tag2\""):]
        block = block[len("```json\n"):block.index("\n```")]
        shown = json.loads(block.replace('"de": "..."', '"de": "x"'))
        shipped = copy.deepcopy(TAG2)
        shown["online"]["note"] = shipped["online"]["note"]
        self.assertEqual(shown, shipped)
        for key in gm.FIELDS[""]:
            self.assertIn(f"`{key}`", doc)


if __name__ == "__main__":
    unittest.main()
