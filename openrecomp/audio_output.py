"""Is there a playback device? Asked with Windows' own MMDevice API (ctypes, no new dependency).

TAG2's public build can end right after start when Windows has none; the launcher warns before such a start
(adapters/tag2.py start_warning). Only a clear "no" is a warning: when Windows cannot answer, nothing is said.
"""
import ctypes
import os
import threading
import uuid

S_OK, S_FALSE = 0, 1
E_NOTFOUND = -2147023728            # HRESULT_FROM_WIN32(ERROR_NOT_FOUND) 0x80070490: no default endpoint
CLSCTX_ALL = 0x17
COINIT_MULTITHREADED = 0
E_RENDER, E_CONSOLE, E_MULTIMEDIA = 0, 0, 1
DEVICE_STATE_ACTIVE = 1
CLSID_MMDEVICE_ENUMERATOR = "BCDE0395-E52F-467C-8E3D-C4579291692E"
IID_IMMDEVICE_ENUMERATOR = "A95664D2-9614-4F35-A746-DE8DB63617E6"


class _GUID(ctypes.Structure):
    _fields_ = [("data", ctypes.c_ubyte * 16)]

    @classmethod
    def of(cls, text):
        g = cls()
        ctypes.memmove(g.data, uuid.UUID(text).bytes_le, 16)
        return g


def _method(obj, index, *argtypes):
    """The COM method at vtable slot index of obj (an interface pointer), returning the HRESULT as a plain int."""
    vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vtable[index])


def _release(obj):
    if obj:
        _method(obj, 2)(obj)


def _probe():
    """True / False / None (cannot tell); runs on its own thread, which it initialises for COM itself."""
    ole32 = ctypes.WinDLL("ole32")
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    ole32.CoCreateInstance.restype = ctypes.c_long
    ole32.CoCreateInstance.argtypes = [ctypes.POINTER(_GUID), ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(_GUID),
                                       ctypes.POINTER(ctypes.c_void_p)]
    initialised = ole32.CoInitializeEx(None, COINIT_MULTITHREADED) in (S_OK, S_FALSE)
    try:
        enum = ctypes.c_void_p()
        if ole32.CoCreateInstance(ctypes.byref(_GUID.of(CLSID_MMDEVICE_ENUMERATOR)), None, CLSCTX_ALL,
                                  ctypes.byref(_GUID.of(IID_IMMDEVICE_ENUMERATOR)), ctypes.byref(enum)) < 0 or not enum:
            return None
        try:
            default = _method(enum, 4, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))   # GetDefaultAudioEndpoint
            missing = False
            for role in (E_CONSOLE, E_MULTIMEDIA):
                device = ctypes.c_void_p()
                hr = default(enum, E_RENDER, role, ctypes.byref(device))
                if hr == E_NOTFOUND:
                    missing = True
                    continue
                if hr < 0 or not device:
                    return None
                try:
                    state = ctypes.c_ulong()
                    if _method(device, 6, ctypes.POINTER(ctypes.c_ulong))(device, ctypes.byref(state)) < 0:   # GetState
                        return True
                    if state.value == DEVICE_STATE_ACTIVE:
                        return True
                    missing = True
                finally:
                    _release(device)
            return False if missing else None
        finally:
            _release(enum)
    finally:
        if initialised:
            ole32.CoUninitialize()


def default_audio_output(timeout=2.0):
    """True when Windows has an active default playback device, False when it has none, None when it cannot tell
    (not Windows, COM refused, no answer in time)."""
    if os.name != "nt":
        return None
    answer = [None]

    def work():
        try:
            answer[0] = _probe()
        except (OSError, ValueError, AttributeError):
            answer[0] = None

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    thread.join(timeout)
    return answer[0] if not thread.is_alive() else None
