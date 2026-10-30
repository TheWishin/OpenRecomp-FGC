import ast
import json
import os
import re
import unittest
from pathlib import Path
from unittest import mock

from openrecomp import i18n
from openrecomp.adapters.base import Adapter
from openrecomp.nav import Game, Nav


ROOT = Path(__file__).parents[1]


def untranslated_literals(source):
    """Check every Python string, exempting code identifiers and external-data formats."""
    tree = ast.parse(source)
    ignored = set()
    errors = []
    english = i18n.catalog("en")

    def ignore(node):
        ignored.update(id(child) for child in ast.walk(node))

    def check_display(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if any(ch.isalpha() for ch in node.value) and not node.value.startswith("@") and node.value not in ("1080p", "1440p", "4K", "SLUS-20328", "T5DR Online"):
                errors.append((node.lineno, node.value))
        elif isinstance(node, ast.IfExp):
            check_display(node.body)
            check_display(node.orelse)

    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            ignore(node)  # docstrings
        elif isinstance(node, ast.FunctionDef) and node.name == "quick_settings":
            for child in ast.walk(node):
                if isinstance(child, ast.Return):
                    ignore(child.value)  # adapter setting IDs, never display labels
        elif isinstance(node, ast.Subscript):
            ignore(node.slice)  # field names, never their values
        elif isinstance(node, ast.Dict):
            for key in node.keys:
                if key is not None:
                    ignore(key)
        elif isinstance(node, ast.Tuple) and len(node.elts) == 2:
            # Option pairs carry a stable setting value and a catalog label.
            label = node.elts[1]
            if isinstance(label, ast.Constant) and isinstance(label.value, str) and label.value.startswith("@"):
                ignore(node.elts[0])
        elif isinstance(node, ast.Compare):
            for child in (node.left, *node.comparators):
                if isinstance(child, (ast.Constant, ast.Tuple, ast.List)):
                    ignore(child)  # action IDs and core protocol values
        elif isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id in ("GLYPHS", "TRAIL", "OSK", "__all__") for t in node.targets):
                ignore(node.value)  # physical button names, keyboard keys, exports
            if any(isinstance(t, ast.Name) and t.id in ("SECTION_TITLES", "DEVICE_LABEL", "OSK_ACTIONS") for t in node.targets):
                for child in ast.walk(node.value):
                    if isinstance(child, ast.Constant) and child.value in english:
                        ignore(child)  # tables of catalog keys
            if any(isinstance(t, ast.Attribute) and t.attr in ("screen", "overlay", "device", "pad_kind", "confirm_kind") for t in node.targets):
                if isinstance(node.value, ast.Constant):
                    ignore(node.value)
        elif isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if name in ("get", "setdefault", "getenv", "pop", "startswith", "import_module", "strftime", "compile", "match", "expanduser") and node.args:
                ignore(node.args[0])
            elif name in ("prompt", "glyph", "_ask", "_open_picker", "act") and node.args:
                ignore(node.args[0])
            elif name == "_go" and len(node.args) > 1:
                ignore(node.args[1])
            elif name == "message" and node.args:
                for key in ast.walk(node.args[0]):
                    if isinstance(key, ast.Constant) and isinstance(key.value, str) and key.value not in english:
                        errors.append((key.lineno, key.value))
                ignore(node.args[0])
            for kw in node.keywords:
                if kw.arg in ("label", "hint", "lead", "title", "verb", "kicker", "k", "v", "value", "note", "primary", "status", "version", "players", "last", "result", "empty", "bar"):
                    check_display(kw.value)
                if kw.arg in ("id", "kind", "opens", "encoding", "errors", "mode"):
                    ignore(kw.value)

    # These are filenames, environment variables, technical units, and protocol identifiers.
    technical = {
        "_items_", "_view_", "source:", "text:", "space", "del", "done", "random", "reload", "nt", "utf-8", "w", "replace",
        "folder", "file", "dir", "action", "dev", "auto", "1080p", "1440p", "4K", "SLUS-20328", "T5DR Online",
        "launcher", "runtime", "core.py", "t4core.py", "t4_launcher.pyw", "t5dr_launcher.pyw", "t5dr.exe",
        "T5DR Online.exe", "T5DROnline", "online.json", "release.json", "lobby", "t5lobby", "tools", "data",
        "cache", "fighters", "fighters.json", "python", "python.exe", "t4", "t5dr", "hero.png",
        "Downloads", "Desktop", "APPDATA", "OPENRECOMP_T4_ROOT", "OPENRECOMP_T5DR_ROOT", "T5_ONLINE_DIR",
        ".json", ".iso", "*.iso", ".pkg", ".rap", ".openrecomp.tmp", "logs\\build_game.log",
        "--search", "-Force", "openrecomp", "taskkill", "/T", "/F", "/PID", "W", "L",
    }
    formats = {
        'f"{platform} RECOMP"', 'f"slot{i}"', 'f"{self.game.id}:{self.section()}"', 'f"{letter}:\\\\"',
        'f"v{version}"', 'f"face_{gid:02d}.png"', 'f"hero_{gid:02d}.png"',
        'f"{e.score[0]}:{e.score[1]}"', 'f"{a} – {b}"', 'f"{m.group(2)}.{m.group(1)}., {m.group(3)}"',
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            if ast.get_source_segment(source, node) in formats:
                ignore(node)
    for node in ast.walk(tree):
        if id(node) in ignored or not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        value = node.value
        if not any(ch.isalpha() for ch in value):
            continue
        if value.startswith("@"):
            if value[1:] not in english and value != "@language.":
                errors.append((node.lineno, value))
        elif value not in technical:
            errors.append((node.lineno, value))
    return errors


class FakeAdapter:
    native_label = ""

    def found(self):
        return True

    def ready(self):
        return True

    def status(self):
        return {"status": "Ready", "version": "1", "players": "No", "last": "Never", "detail": "Ready."}

    def running(self):
        return False

    def hero(self):
        return ""

    def recent_results(self):
        return []

    def settings(self):
        return []

    def quick_settings(self):
        return []


def game():
    manifest = {"id": "test", "short": "Test", "accent": "#ffffff", "numeral": "T", "title": "Test", "subtitle": "", "sections": ["play"]}
    return Game(manifest, FakeAdapter())


class Catalogs(unittest.TestCase):
    def test_catalogs_have_equal_keys_and_placeholders(self):
        catalogs = {code: json.loads((ROOT / "openrecomp" / "i18n" / (code + ".json")).read_text(encoding="utf-8")) for code in i18n.LANGUAGES}
        keys = set(catalogs["en"])
        for code, entries in catalogs.items():
            self.assertEqual(set(entries), keys, code)
            for key in keys:
                self.assertEqual(set(re.findall(r"{(.*?)}", entries[key])), set(re.findall(r"{(.*?)}", catalogs["en"][key])), (code, key))

    def test_missing_translation_falls_back_to_english(self):
        english = i18n.catalog("en")
        german = dict(i18n.catalog("de"))
        german.pop("quick_access")
        with mock.patch("openrecomp.i18n.catalog", side_effect=lambda code: english if code == "en" else german):
            self.assertEqual(i18n.text("de", "quick_access"), "Quick access")

    def test_shared_input_delay_wording_matches_t5dr(self):
        expected = {
            "de": "Online-Input-Delay", "es": "Input delay online", "fr": "Input delay en ligne",
            "ja": "オンライン入力遅延", "ko": "온라인 입력 지연", "pt-BR": "Input delay online",
        }
        for code, label in expected.items():
            self.assertEqual(i18n.text(code, "input_delay"), label, code)

    def test_switching_language_changes_the_view(self):
        nav = Nav([game()], language="en")
        nav.act("social")
        before = nav.view()
        nav.act("confirm")
        after = nav.view()
        self.assertNotEqual(before, after)
        self.assertEqual(after["drawer"]["rows"][0]["value"], "Deutsch")

    def test_language_cycles_both_ways_and_notifies(self):
        changed = []
        nav = Nav([game()], language="en", on_language=changed.append)
        nav.act("social")
        for action, expected in (("left", "pt-BR"), ("right", "en"), ("confirm", "de")):
            nav.act(action)
            self.assertEqual(nav.language, expected)
        self.assertEqual(changed, ["pt-BR", "en", "de"])

    def test_unknown_at_strings_are_untouched_in_the_view(self):
        nav = Nav([game()], language="de")
        nav.game.m["title"] = "@Player"
        nav.say("@folder/path")
        view = nav.view()
        self.assertEqual(view["shelf"]["tiles"][0]["name"], "@Player")
        self.assertEqual(view["toast"], "@folder/path")
        self.assertEqual(i18n.localize(["@Player", "@folder/path", "@missing.key"], "ja"),
                         ["@Player", "@folder/path", "@missing.key"])
        self.assertEqual(i18n.localize("@quick_access", "de"), "Schnellzugriff")

    def test_placeholder_reaches_the_view_in_every_language(self):
        expected = {
            "en": "@Player is starting.", "de": "@Player startet.", "es": "Iniciando @Player.",
            "fr": "Lancement de @Player.", "ja": "@Playerを起動しています。",
            "ko": "@Player을 시작합니다.", "pt-BR": "Iniciando @Player.",
        }
        for code in i18n.LANGUAGES:
            nav = Nav([game()], language=code)
            nav.say(i18n.message("game_starting", name="@Player"))
            self.assertEqual(nav.view()["toast"], expected[code], code)

    def test_nested_placeholders_and_cycler_values_translate_in_the_view(self):
        adapter = FakeAdapter()
        adapter.settings = lambda: [dict(id="test", label="@display", value=True,
                                         options=[(True, "@on"), (False, "@off")])]
        adapter.quick_settings = lambda: ["test"]
        g = Game(game().m, adapter)
        for code in i18n.LANGUAGES:
            nav = Nav([g], language=code)
            nav.act("confirm")
            nav.act("down")
            nav.dry = True
            nav.act("right")
            view = nav.view()
            self.assertEqual(view["rows"][1]["value"], "‹ " + i18n.text(code, "on") + " ›", code)
            self.assertEqual(view["detail"]["rows"][0]["v"], i18n.text(code, "on"), code)
            self.assertEqual(view["toast"], i18n.text(code, "dry_run", what=i18n.text(code, "dry_change", name=i18n.text(code, "display"))), code)

    def test_adapter_messages_survive_the_view(self):
        g = game()
        g.a = Adapter(g.m)
        for code in i18n.LANGUAGES:
            nav = Nav([g], language=code)
            self.assertEqual(nav.view()["hint"], i18n.text(code, "game_not_found", name="Test"), code)
            nav.act("play")
            self.assertEqual(nav.view()["toast"], i18n.text(code, "not_ready"), code)

    def test_adapter_error_with_values_survives_the_view(self):
        for code in i18n.LANGUAGES:
            nav = Nav([game()], language=code)
            nav.game.a.start = mock.Mock(side_effect=RuntimeError(Adapter.message("t4.locked", holder="@Player")))
            nav.act("play")
            self.assertEqual(nav.view()["toast"], i18n.text(code, "t4.locked", holder="@Player"), code)

    def test_external_error_text_is_untouched(self):
        for value in ("@Player: core error", {"reason": "core error"}):
            nav = Nav([game()], language="ja")
            error = RuntimeError(value)
            nav.game.a.start = mock.Mock(side_effect=error)
            nav.act("play")
            self.assertEqual(nav.view()["toast"], str(error))

    def test_file_picker_title_translates_its_source_label(self):
        for code in i18n.LANGUAGES:
            g = game()
            g.a = Adapter(g.m)
            g.a.sources = lambda: [dict(id="iso", label="@game_iso", value="@missing", ok=False,
                                       kind="file", exts=[".iso"], dirs=[], hint="@iso.hint")]
            nav = Nav([g], language=code)
            with mock.patch.object(nav, "_picker_entries", return_value=[]):
                nav._items_build(g)[0]["run"]()
                self.assertEqual(nav.view()["picker"]["title"], i18n.text(code, "choose_named", name=i18n.text(code, "game_iso")), code)

    def test_recent_results_translate_without_changing_win_state(self):
        for code in i18n.LANGUAGES:
            nav = Nav([game()], language=code)
            nav.game.a.recent_results = lambda: ["W", "L"]
            cells = nav.view()["shelf"]["tiles"][0]["results"]
            self.assertEqual([cell["text"] for cell in cells], [i18n.text(code, "result.win_short"), i18n.text(code, "result.loss_short")], code)
            self.assertEqual([cell["win"] for cell in cells], [True, False], code)

    def test_catalogs_are_loaded_once(self):
        i18n._catalog.cache_clear()
        try:
            with mock.patch.object(Path, "open", autospec=True, side_effect=Path.open) as opened:
                for _ in range(3):
                    for code in i18n.LANGUAGES:
                        i18n.localize({"label": "@quick_access", "hint": "@language"}, code)
                self.assertEqual(opened.call_count, len(i18n.LANGUAGES))
                self.assertEqual(len({call.args[0] for call in opened.call_args_list}), len(i18n.LANGUAGES))
        finally:
            i18n._catalog.cache_clear()

    def test_python_has_no_player_facing_literals(self):
        paths = [ROOT / "openrecomp" / "nav.py", *(ROOT / "openrecomp").glob("nav_*.py"),
                 *(ROOT / "openrecomp" / "adapters").glob("*.py")]
        for path in paths:
            self.assertEqual(untranslated_literals(path.read_text(encoding="utf-8")), [], path.name)

    def test_python_scan_accepts_setting_ids_and_protocol_defaults(self):
        source = ('def quick_settings(self):\n'
                  '    return ["resolution", "fullscreen", "display", "internal_res"]\n'
                  'value = self.s.get("resolution", "auto")\n')
        self.assertEqual(untranslated_literals(source), [])
        self.assertTrue(untranslated_literals('dict(label="auto")'))
        self.assertTrue(untranslated_literals('def quick_settings(self):\n'
                                             '    self.say("Choose a setting")\n'
                                             '    return ["resolution"]\n'))

    def test_python_scan_rejects_untranslated_texts_and_f_strings(self):
        examples = [
            'dict(label="Start game", hint="Choose a file")',
            'dict(lead="ready", title="Hello", verb="Watch", kicker="Local", rows=[dict(k="Name", v="Unknown")])',
            'self.say(f"Starting {name}.")',
            'return [(True, "On"), (False, "Off")]',
            'status = "Ready"',
            'dict(label="file", value="ready")',
            'return "Choose your files first."',
        ]
        for source in examples:
            self.assertTrue(untranslated_literals(source), source)

    def test_qml_has_no_player_facing_literals(self):
        forbidden = ("Quick access", "Recent sets", "Choose your fighter", "Your main:", "Folder", "File", "MAIN")
        for path in (ROOT / "openrecomp" / "ui").glob("*.qml"):
            source = path.read_text(encoding="utf-8")
            self.assertFalse(any(text in source for text in forbidden), path.name)


if __name__ == "__main__":
    unittest.main()
