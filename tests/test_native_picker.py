"""Mouse and keyboard choose files in the Windows Explorer dialog; a controller keeps the launcher's own list.

The dialog cannot show offscreen: Nav and the Backend glue get a fake chooser. The real IFileOpenDialog is driven on
a hidden desktop of its own (nothing appears on the player's screen) by test_real_dialog_* below.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp import app, file_dialog, i18n
from openrecomp.nav import Game, Nav
from test_nav import Fake, manifest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Folder(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.iso = os.path.join(self.dir, "game.iso")
        open(self.iso, "w").close()
        open(os.path.join(self.dir, "notes.txt"), "w").close()
        self.saved = []
        self.a = Fake(manifest())
        self.nav = Nav([Game(self.a.m, self.a)], language="en", native_picker=True, on_picker_dir=self.saved.append)

    def open_iso_row(self, device):
        """Build -> the ISO row, the way a player gets there."""
        self.nav.act("confirm", device=device)
        self.nav.act("next", device=device)
        self.nav.act("next", device=device)
        self.nav.act("confirm", device=device)


class NavTests(Folder):
    def test_keyboard_or_mouse_asks_for_explorer_instead_of_the_list(self):
        self.open_iso_row("kb")
        self.assertIsNone(self.nav.overlay)
        self.assertIsNotNone(self.nav.pending_native)
        request = self.nav.native_request()
        self.assertIsNone(self.nav.pending_native, "a request is taken once")
        self.assertEqual(request["kind"], "file")
        self.assertEqual(request["title"], i18n.text("en", "choose_named", name="ISO"))
        self.assertEqual(request["filters"], [(i18n.text("en", "picker.filter_matching", patterns="*.iso"), "*.iso"),
                                              (i18n.text("en", "picker.filter_all"), "*.*")])
        self.assertEqual(request["start"], os.path.join(os.path.expanduser("~"), "Downloads")
                         if os.path.isdir(os.path.join(os.path.expanduser("~"), "Downloads")) else "")

    def test_a_controller_still_gets_the_launcher_list(self):
        for device in ("xbox", "ps"):
            with self.subTest(device=device):
                self.nav = Nav([Game(self.a.m, self.a)], language="en", native_picker=True)
                self.open_iso_row(device)
                self.assertEqual(self.nav.overlay, "picker")
                self.assertIsNone(self.nav.pending_native)

    def test_without_a_dialog_on_this_pc_the_keyboard_gets_the_list(self):
        nav = Nav([Game(self.a.m, self.a)], language="en")
        nav.act("confirm", device="kb")
        nav.act("next", device="kb")
        nav.act("next", device="kb")
        nav.act("confirm", device="kb")
        self.assertEqual(nav.overlay, "picker")
        self.assertIsNone(nav.pending_native)
        self.assertNotIn("x", [p["action"] for p in nav.view()["prompts"]])

    def test_the_chosen_file_goes_the_same_way_as_from_the_list(self):
        self.open_iso_row("kb")
        self.nav.native_result(self.nav.native_request(), self.iso)
        self.assertEqual(self.a.calls, [("source", "iso", self.iso)])
        self.assertEqual(self.nav.toast, "gut")
        self.assertEqual((self.nav.picker_dir, self.saved), (self.dir, [self.dir]))

    def test_cancel_changes_nothing(self):
        self.open_iso_row("kb")
        self.nav.native_result(self.nav.native_request(), "")
        self.assertEqual((self.a.calls, self.nav.toast, self.saved, self.nav.overlay), ([], "", [], None))

    def test_a_file_of_another_type_is_refused_like_the_list_never_offers_it(self):
        self.open_iso_row("kb")
        self.nav.native_result(self.nav.native_request(), os.path.join(self.dir, "notes.txt"))
        self.assertEqual(self.a.calls, [])
        self.assertEqual(self.nav.view()["toast"], i18n.text("en", "picker_wrong_type", types=".iso"))
        self.assertEqual(self.saved, [])

    def test_upper_case_extension_is_the_right_type(self):
        upper = os.path.join(self.dir, "SECOND.ISO")
        open(upper, "w").close()
        self.open_iso_row("kb")
        self.nav.native_result(self.nav.native_request(), upper)
        self.assertEqual(self.a.calls, [("source", "iso", upper)])

    def test_folder_request_opens_a_folder_dialog_and_refuses_a_file(self):
        self.nav.device = "kb"
        self.nav._open_picker("setting:replays", "@folder", [], [self.dir], "folder")
        request = self.nav.native_request()
        self.assertEqual((request["kind"], request["filters"], request["start"]), ("folder", [], self.dir))
        self.nav.native_result(request, self.iso)
        self.assertEqual(self.nav.view()["toast"], i18n.text("en", "picker_not_folder"))
        self.nav.native_result(request, self.dir)
        self.assertEqual(self.a.calls, [("set", "replays", self.dir)])

    def test_zip_or_folder_opens_the_file_dialog_for_the_zip(self):
        self.nav.device = "kb"
        self.nav._open_picker("source:folder", "@folder", [".zip"], [], "file_or_folder")
        request = self.nav.native_request()
        self.assertEqual(request["kind"], "file")
        self.assertEqual(request["filters"][0][1], "*.zip")

    def test_start_folder_is_the_last_one_used(self):
        self.nav.picker_dir = self.dir
        self.nav.device = "kb"
        self.nav._open_picker("source:iso", "@game_iso", [".iso"], [ROOT], "file")
        self.assertEqual(self.nav.native_request()["start"], self.dir)
        self.nav.device = "xbox"
        self.nav._open_picker("source:iso", "@game_iso", [".iso"], [ROOT], "file")
        self.assertEqual(self.nav.picker["dir"], self.dir, "the controller list opens there too")

    def test_folder_setting_starts_at_its_own_value_not_the_last_file(self):
        with tempfile.TemporaryDirectory() as other:
            self.nav.picker_dir = other
            self.nav.device = "kb"
            self.nav._open_picker("setting:replays", "@folder", [], [self.dir], "folder")
            self.assertEqual(self.nav.native_request()["start"], self.dir)

    def test_a_pick_in_the_list_is_remembered_too(self):
        self.open_iso_row("xbox")
        self.nav.picker["dir"] = self.dir
        self.nav.picker["focus"] = 1                      # "..", game.iso
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.a.calls, [("source", "iso", self.iso)])
        self.assertEqual(self.saved, [self.dir])

    def test_x_in_the_list_opens_explorer_at_the_list_folder(self):
        self.open_iso_row("xbox")
        self.nav.picker["dir"] = self.dir
        self.assertIn(("x", i18n.text("en", "picker.explorer")),
                      [(p["action"], p["label"]) for p in self.nav.view()["prompts"]])
        self.nav.act("x", device="xbox")
        self.assertIsNone(self.nav.overlay)
        self.assertEqual(self.nav.native_request()["start"], self.dir)

    def test_no_dialog_falls_back_to_the_list_at_the_same_folder(self):
        self.nav.picker_dir = self.dir
        self.open_iso_row("kb")
        self.nav.native_failed(self.nav.native_request())
        self.assertEqual(self.nav.overlay, "picker")
        self.assertEqual((self.nav.picker["dir"], self.nav.picker["exts"], self.nav.picker["target"]),
                         (self.dir, [".iso"], "source:iso"))

    def test_dry_run_remembers_nothing_on_disk(self):
        self.nav.dry = True
        self.open_iso_row("kb")
        self.nav.native_result(self.nav.native_request(), self.iso)
        self.assertEqual((self.a.calls, self.saved), ([], []))

    def test_every_language_names_the_filters(self):
        for code in i18n.LANGUAGES:
            with self.subTest(language=code):
                self.nav.language = code
                self.nav.device = "kb"
                self.nav._open_picker("source:pkg", "@package", [".pkg"], [], "file")
                names = [name for name, _spec in self.nav.native_request()["filters"]]
                self.assertIn("*.pkg", names[0])
                self.assertIn("*.*", names[1])
                self.assertFalse(any(name.startswith("@") or "{" in name for name in names))


class BackendTests(Folder):
    def backend(self, chooser):
        config = {}
        backend = SimpleNamespace(nav=self.nav, choose_file=chooser, _native_queued=False, _native_open=False,
                                  window=SimpleNamespace(winId=lambda: 4242), pads=mock.Mock(), refresh=mock.Mock(),
                                  config=config, _save_config=mock.Mock())
        backend._run_native = lambda: app.Backend._run_native(backend)
        return backend

    def test_the_dialog_opens_after_the_press_and_its_choice_is_used(self):
        chooser = mock.Mock(return_value=self.iso)
        backend = self.backend(chooser)
        self.open_iso_row("kb")
        with mock.patch.object(app.QTimer, "singleShot") as later:
            app.Backend._queue_native(backend)
            app.Backend._queue_native(backend)            # a second refresh before it ran: still one dialog
        self.assertEqual(later.call_count, 1)
        chooser.assert_not_called()
        later.call_args.args[1]()
        owner, title, kind, filters, start = chooser.call_args.args
        self.assertEqual((owner, kind, filters[0][1]), (4242, "file", "*.iso"))
        self.assertEqual(title, i18n.text("en", "choose_named", name="ISO"))
        self.assertEqual(self.a.calls, [("source", "iso", self.iso)])
        backend.pads.suppress.assert_called_once()
        backend.refresh.assert_called_once()
        self.assertFalse(backend._native_open)

    def test_a_dialog_that_cannot_open_gives_the_list(self):
        backend = self.backend(mock.Mock(side_effect=OSError("no COM")))
        self.open_iso_row("kb")
        app.Backend._run_native(backend)
        self.assertEqual(self.nav.overlay, "picker")
        self.assertEqual(self.a.calls, [])

    def test_a_refused_source_is_a_message_not_a_crash(self):
        backend = self.backend(mock.Mock(return_value=self.iso))
        self.open_iso_row("kb")
        with mock.patch.object(self.a, "set_source", side_effect=RuntimeError("@library.busy")):
            app.Backend._run_native(backend)
        self.assertEqual(self.nav.view()["toast"], i18n.text("en", "library.busy"))

    def test_last_folder_is_saved_in_the_config(self):
        backend = SimpleNamespace(config={}, _save_config=mock.Mock())
        app.Backend._save_picker_dir(backend, self.dir)
        self.assertEqual(backend.config, {"picker_dir": self.dir})
        backend._save_config.assert_called_once()

    def test_no_explorer_dialog_offscreen_or_when_switched_off(self):
        with mock.patch.object(app.QGuiApplication, "platformName", return_value="offscreen"):
            self.assertFalse(app.native_picker_available())
        with mock.patch.object(app.QGuiApplication, "platformName", return_value="windows"):
            self.assertEqual(app.native_picker_available(), os.name == "nt")
            with mock.patch.dict(os.environ, {"OPENRECOMP_NATIVE_PICKER": "0"}):
                self.assertFalse(app.native_picker_available())


DRIVE = textwrap.dedent(r'''
    import ctypes, ctypes.wintypes as wt, os, sys, threading, time
    sys.path.insert(0, sys.argv[1])
    from openrecomp import file_dialog
    mode, folder = sys.argv[2], sys.argv[3]
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.CreateDesktopW.restype = wt.HANDLE
    user32.CreateDesktopW.argtypes = [wt.LPCWSTR, wt.LPCWSTR, ctypes.c_void_p, wt.DWORD, wt.DWORD, ctypes.c_void_p]
    user32.SetThreadDesktop.argtypes = [wt.HANDLE]
    user32.CloseDesktop.argtypes = [wt.HANDLE]
    ENUM = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    user32.EnumDesktopWindows.argtypes = [wt.HANDLE, ENUM, wt.LPARAM]
    user32.FindWindowExW.restype = wt.HWND
    user32.FindWindowExW.argtypes = [wt.HWND, wt.HWND, wt.LPCWSTR, wt.LPCWSTR]
    user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, ctypes.c_void_p]
    user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    # A desktop of our own: the dialog is real but never on the player's screen and never takes the focus.
    desk = user32.CreateDesktopW("openrecomp-picker-test-%d" % os.getpid(), None, None, 0, 0x10000000, None)
    if not desk:
        print("SKIP no desktop"); sys.exit(0)
    out = {}
    def show():
        user32.SetThreadDesktop(desk)
        try:
            out["path"] = file_dialog.choose(0, "Test", "folder" if mode == "folder" else "file",
                                             [("ISO (*.iso)", "*.iso"), ("All (*.*)", "*.*")], folder)
        except OSError as e:
            out["error"] = str(e)
    def press():
        user32.SetThreadDesktop(desk)
        for _ in range(400):
            found = []
            def each(h, _l):
                name = ctypes.create_unicode_buffer(64)
                user32.GetClassNameW(h, name, 64)
                if name.value == "#32770":
                    found.append(h)
                return True
            user32.EnumDesktopWindows(desk, ENUM(each), 0)
            if found:
                time.sleep(0.5)
                if mode == "file":
                    combo = user32.FindWindowExW(found[0], None, "ComboBoxEx32", None)
                    edit = user32.FindWindowExW(user32.FindWindowExW(combo, None, "ComboBox", None), None, "Edit", None)
                    user32.SendMessageW(edit, 0x000C, 0, ctypes.c_wchar_p("game.iso"))   # WM_SETTEXT
                user32.SendMessageW(found[0], 0x0111, 2 if mode == "cancel" else 1, None)  # WM_COMMAND IDCANCEL/IDOK
                return
            time.sleep(0.05)
    a, b = threading.Thread(target=show), threading.Thread(target=press)
    a.start(); b.start(); a.join(30); b.join(5)
    print(repr(out.get("path", out.get("error", "TIMEOUT"))))
    sys.stdout.flush()
    user32.CloseDesktop(desk)
    os._exit(0)
''')


@unittest.skipUnless(os.name == "nt", "Windows only")
class RealDialog(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        open(os.path.join(self.dir, "game.iso"), "w").close()

    def drive(self, mode):
        result = subprocess.run([sys.executable, "-I", "-c", DRIVE, ROOT, mode, self.dir], capture_output=True,
                                text=True, timeout=60)
        if result.stdout.startswith("SKIP"):
            self.skipTest(result.stdout.strip())
        return result.stdout.strip()

    def test_real_dialog_returns_the_file_the_player_chose(self):
        self.assertEqual(self.drive("file"), repr(os.path.join(self.dir, "game.iso")))

    def test_real_dialog_cancel_returns_nothing(self):
        self.assertEqual(self.drive("cancel"), repr(""))

    def test_real_dialog_picks_a_folder_and_opens_at_the_start_folder(self):
        self.assertEqual(self.drive("folder"), repr(self.dir))

    def test_options_filters_and_start_folder_reach_the_dialog(self):
        with file_dialog.Dialog() as dialog:
            file_dialog.configure(dialog, "Test", "file", [("ISO", "*.iso"), ("All", "*.*")], self.dir)
            flags = dialog.options()
            self.assertTrue(flags & file_dialog.FOS_FILEMUSTEXIST)
            self.assertFalse(flags & file_dialog.FOS_PICKFOLDERS)
            self.assertEqual(dialog.filter_index(), 1)
            self.assertEqual(os.path.normcase(dialog.folder()), os.path.normcase(self.dir))
        with file_dialog.Dialog() as dialog:
            file_dialog.configure(dialog, "", "folder", [], os.path.join(self.dir, "missing"))
            self.assertTrue(dialog.options() & file_dialog.FOS_PICKFOLDERS)


if __name__ == "__main__":
    unittest.main()
