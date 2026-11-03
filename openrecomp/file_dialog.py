"""The Windows Explorer open dialog (IFileOpenDialog) through ctypes: no Qt Widgets, no QApplication, no new module.

choose(owner, title, kind, filters, start) -> the chosen path, "" when the player cancelled. Raises OSError when the
dialog cannot be made (not Windows, COM refused); the caller then falls back to the launcher's own picker.
kind "folder" picks a folder; any other kind picks one existing file. filters = [(name, "*.iso;*.ISO"), ...].
"""
import ctypes
import os
import uuid

CLSID_FILE_OPEN_DIALOG = "{DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7}"
IID_IFILE_OPEN_DIALOG = "{D57C7288-D4AD-4768-BE02-9D969532D960}"
IID_ISHELL_ITEM = "{43826D1E-E718-42EE-BC55-A1E261C37BFE}"
CLSCTX_INPROC_SERVER = 1
COINIT_APARTMENTTHREADED = 2
RPC_E_CHANGED_MODE = -2147417850          # COM already set up by Qt (OleInitialize): fine, use it
ERROR_CANCELLED = -2147023673             # HRESULT_FROM_WIN32(ERROR_CANCELLED): the player closed the dialog
SIGDN_FILESYSPATH = 0x80058000 - (1 << 32)
FOS_NOCHANGEDIR = 0x8
FOS_PICKFOLDERS = 0x20
FOS_FORCEFILESYSTEM = 0x40
FOS_PATHMUSTEXIST = 0x800
FOS_FILEMUSTEXIST = 0x1000
# IFileDialog vtable slots (IUnknown 0-2, IModalWindow::Show 3).
RELEASE, SHOW, SET_FILE_TYPES, SET_FILE_TYPE_INDEX, GET_FILE_TYPE_INDEX = 2, 3, 4, 5, 6
SET_OPTIONS, GET_OPTIONS, SET_DEFAULT_FOLDER, SET_FOLDER, GET_FOLDER, SET_TITLE, GET_RESULT = 9, 10, 11, 12, 13, 17, 20
GET_DISPLAY_NAME = 5                      # IShellItem


class FilterSpec(ctypes.Structure):
    _fields_ = [("name", ctypes.c_wchar_p), ("spec", ctypes.c_wchar_p)]


def _guid(text):
    return (ctypes.c_byte * 16).from_buffer_copy(uuid.UUID(text).bytes_le)


def _call(obj, slot, *args, argtypes=()):
    """obj->vtable[slot](obj, *args) -> HRESULT (negative = failed)."""
    vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vtable[slot])
    return fn(obj, *args)


def _check(hr, what):
    if hr < 0:
        raise OSError(f"{what} failed (0x{hr & 0xFFFFFFFF:08X})")


class Dialog:
    """One IFileOpenDialog. Usable as a context manager; release() is safe to call twice."""

    def __init__(self):
        if os.name != "nt":
            raise OSError("Windows only")
        self.ole32 = ctypes.windll.ole32
        self.shell32 = ctypes.windll.shell32
        hr = self.ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
        self._uninit = hr >= 0            # S_OK / S_FALSE pair with CoUninitialize; RPC_E_CHANGED_MODE does not
        if hr < 0 and hr != RPC_E_CHANGED_MODE:
            _check(hr, "CoInitializeEx")
        self.obj = ctypes.c_void_p()
        hr = self.ole32.CoCreateInstance(ctypes.byref(_guid(CLSID_FILE_OPEN_DIALOG)), None, CLSCTX_INPROC_SERVER,
                                         ctypes.byref(_guid(IID_IFILE_OPEN_DIALOG)), ctypes.byref(self.obj))
        if hr < 0:
            self._done()
            _check(hr, "CoCreateInstance")

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.release()

    def _done(self):
        if self._uninit:
            self._uninit = False
            self.ole32.CoUninitialize()

    def release(self):
        if self.obj:
            _call(self.obj, RELEASE)
            self.obj = ctypes.c_void_p()
        self._done()

    def options(self):
        value = ctypes.c_uint()
        _check(_call(self.obj, GET_OPTIONS, ctypes.byref(value), argtypes=(ctypes.c_void_p,)), "GetOptions")
        return value.value

    def set_options(self, flags):
        _check(_call(self.obj, SET_OPTIONS, ctypes.c_uint(flags), argtypes=(ctypes.c_uint,)), "SetOptions")

    def set_title(self, title):
        _check(_call(self.obj, SET_TITLE, title, argtypes=(ctypes.c_wchar_p,)), "SetTitle")

    def set_filters(self, filters):
        self._specs = (FilterSpec * len(filters))(*[FilterSpec(n, s) for n, s in filters])   # alive until Show
        _check(_call(self.obj, SET_FILE_TYPES, ctypes.c_uint(len(filters)), self._specs,
                     argtypes=(ctypes.c_uint, ctypes.c_void_p)), "SetFileTypes")
        _check(_call(self.obj, SET_FILE_TYPE_INDEX, ctypes.c_uint(1), argtypes=(ctypes.c_uint,)), "SetFileTypeIndex")

    def filter_index(self):
        value = ctypes.c_uint()
        _check(_call(self.obj, GET_FILE_TYPE_INDEX, ctypes.byref(value), argtypes=(ctypes.c_void_p,)), "GetFileTypeIndex")
        return value.value

    def _item(self, path):
        item = ctypes.c_void_p()
        hr = self.shell32.SHCreateItemFromParsingName(ctypes.c_wchar_p(path), None,
                                                      ctypes.byref(_guid(IID_ISHELL_ITEM)), ctypes.byref(item))
        _check(hr, "SHCreateItemFromParsingName")
        return item

    def set_folder(self, path):
        """The folder the dialog opens in (SetFolder: also over the folder Windows remembers for this program)."""
        item = self._item(path)
        try:
            _check(_call(self.obj, SET_FOLDER, item, argtypes=(ctypes.c_void_p,)), "SetFolder")
        finally:
            _call(item, RELEASE)

    def folder(self):
        item = ctypes.c_void_p()
        _check(_call(self.obj, GET_FOLDER, ctypes.byref(item), argtypes=(ctypes.c_void_p,)), "GetFolder")
        try:
            return item_path(item)
        finally:
            _call(item, RELEASE)

    def show(self, owner):
        """Modal over owner (a window handle or 0). -> the chosen path, "" when cancelled."""
        hr = _call(self.obj, SHOW, ctypes.c_void_p(owner or None), argtypes=(ctypes.c_void_p,))
        if hr == ERROR_CANCELLED:
            return ""
        _check(hr, "Show")
        item = ctypes.c_void_p()
        _check(_call(self.obj, GET_RESULT, ctypes.byref(item), argtypes=(ctypes.c_void_p,)), "GetResult")
        try:
            return item_path(item)
        finally:
            _call(item, RELEASE)


def item_path(item):
    """IShellItem -> its file system path."""
    text = ctypes.c_void_p()
    _check(_call(item, GET_DISPLAY_NAME, ctypes.c_int(SIGDN_FILESYSPATH), ctypes.byref(text),
                 argtypes=(ctypes.c_int, ctypes.c_void_p)), "GetDisplayName")
    try:
        return ctypes.wstring_at(text.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(text)


def configure(dialog, title, kind, filters, start):
    flags = dialog.options() | FOS_NOCHANGEDIR | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST
    flags |= FOS_PICKFOLDERS if kind == "folder" else FOS_FILEMUSTEXIST
    dialog.set_options(flags)
    if title:
        dialog.set_title(title)
    if filters and kind != "folder":
        dialog.set_filters(filters)
    if start and os.path.isdir(start):
        try:
            dialog.set_folder(start)
        except OSError:
            pass                          # a folder Windows will not open: the dialog's own start is fine


def choose(owner, title, kind, filters, start):
    with Dialog() as dialog:
        configure(dialog, title, kind, filters, start)
        return dialog.show(owner)
