"""Native Windows and macOS hotkeys, loaded only on their target platform."""

import ctypes as C
from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Signal


class NativeShortcuts(QObject):
    activated = Signal(str)
    result = Signal(dict, dict, str, bool)

    def configure(self):
        pass

    def report(self, accepted, errors):
        self.result.emit(accepted, errors, f"{len(accepted)} global shortcuts active." + (" Some bindings need attention." if errors else ""), False)


def windows_key(binding):
    parts = binding.split("+")
    modifiers = sum({"Alt": 1, "Ctrl": 2, "Shift": 4, "Meta": 8}[part] for part in parts[:-1]) | 0x4000
    keys = {"Space": 0x20, "Left": 0x25, "Up": 0x26, "Right": 0x27, "Down": 0x28, "Home": 0x24, "End": 0x23, "PageUp": 0x21, "PageDown": 0x22, "Insert": 0x2D, "Delete": 0x2E, "Escape": 0x1B, "Tab": 9, "Enter": 13, "Backspace": 8, "MediaToggle": 0xB3, "MediaPlay": 0xB3, "MediaPause": 0xB3, "MediaStop": 0xB2, "MediaNext": 0xB0, "MediaPrevious": 0xB1}
    keys.update({f"F{i}": 0x6F + i for i in range(1, 25)})
    key = parts[-1]
    return modifiers, ord(key) if len(key) == 1 else keys[key]


class WinMessage(C.Structure):
    _fields_ = [("hwnd", C.c_void_p), ("message", C.c_uint32), ("wParam", C.c_size_t), ("lParam", C.c_ssize_t), ("time", C.c_uint32), ("x", C.c_int32), ("y", C.c_int32)]


class WindowsFilter(QAbstractNativeEventFilter):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) not in {b"windows_generic_MSG", b"windows_dispatcher_MSG"}:
            return False, 0
        event = WinMessage.from_address(int(message))
        if event.message == 0x0312 and event.wParam in self.owner.ids:
            self.owner.activated.emit(self.owner.ids[event.wParam])
            return True, 0
        return False, 0


class WindowsShortcuts(NativeShortcuts):
    def __init__(self, parent=None, api=None, application=None):
        super().__init__(parent)
        self.api = api or C.WinDLL("user32", use_last_error=True)
        if api is None:
            self.api.RegisterHotKey.argtypes = [C.c_void_p, C.c_int, C.c_uint, C.c_uint]
            self.api.RegisterHotKey.restype = C.c_int
            self.api.UnregisterHotKey.argtypes = [C.c_void_p, C.c_int]
            self.api.UnregisterHotKey.restype = C.c_int
        self.application = application or QCoreApplication.instance()
        self.ids, self.filter = {}, WindowsFilter(self)
        self.application.installNativeEventFilter(self.filter)

    def register(self, rows):
        accepted, errors = {}, {}
        physical = set()
        for index, (key, _, binding) in enumerate(rows):
            modifiers, code = windows_key(binding)
            identifier = 0x5900 + index
            if (modifiers, code) in physical:
                errors[key] = "Another action resolves to the same physical key."
            elif self.api.RegisterHotKey(None, identifier, modifiers, code):
                self.ids[identifier] = key
                physical.add((modifiers, code))
                accepted[key] = binding
            else:
                errors[key] = "Windows could not register this combination. It may be reserved or used by another app."
        self.report(accepted, errors)

    def close(self):
        for identifier in self.ids:
            self.api.UnregisterHotKey(None, identifier)
        self.ids.clear()
        self.application.removeNativeEventFilter(self.filter)
        self.deleteLater()


class HotKeyID(C.Structure):
    _fields_ = [("signature", C.c_uint32), ("id", C.c_uint32)]


class EventType(C.Structure):
    _fields_ = [("eventClass", C.c_uint32), ("eventKind", C.c_uint32)]


CALLBACK = C.CFUNCTYPE(C.c_int32, C.c_void_p, C.c_void_p, C.c_void_p)
SIGNATURE = int.from_bytes(b"YTMN", "big")
KEYBOARD = int.from_bytes(b"keyb", "big")


def mac_key(binding, layout):
    parts = binding.split("+")
    modifiers = sum({"Meta": 1 << 8, "Shift": 1 << 9, "Alt": 1 << 11, "Ctrl": 1 << 12}[part] for part in parts[:-1])
    keys = {"Space": 49, "Left": 123, "Right": 124, "Down": 125, "Up": 126, "Home": 115, "End": 119, "PageUp": 116, "PageDown": 121, "Insert": 114, "Delete": 117, "Escape": 53, "Tab": 48, "Enter": 36, "Backspace": 51}
    keys.update(dict(zip((f"F{i}" for i in range(1, 21)), [122, 120, 99, 118, 96, 97, 98, 100, 101, 109, 103, 111, 105, 107, 113, 106, 64, 79, 80, 90])))
    keys.update(layout)
    return modifiers, keys.get(parts[-1])


def mac_layout(carbon, core=None, property_key=None):
    """Translate the active keyboard layout instead of assuming US letter positions."""
    core = core or C.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    carbon.TISCopyCurrentKeyboardLayoutInputSource.restype = C.c_void_p
    carbon.TISGetInputSourceProperty.argtypes = [C.c_void_p, C.c_void_p]
    carbon.TISGetInputSourceProperty.restype = C.c_void_p
    core.CFDataGetBytePtr.argtypes, core.CFDataGetBytePtr.restype = [C.c_void_p], C.c_void_p
    core.CFRelease.argtypes = [C.c_void_p]
    carbon.LMGetKbdType.restype = C.c_uint8
    carbon.UCKeyTranslate.argtypes = [C.c_void_p, C.c_uint16, C.c_uint16, C.c_uint32, C.c_uint32, C.c_uint32, C.POINTER(C.c_uint32), C.c_ulong, C.POINTER(C.c_ulong), C.POINTER(C.c_uint16)]
    carbon.UCKeyTranslate.restype = C.c_int32
    source = carbon.TISCopyCurrentKeyboardLayoutInputSource()
    if not source:
        return {}
    try:
        if property_key is None:
            property_key = C.c_void_p.in_dll(carbon, "kTISPropertyUnicodeKeyLayoutData")
        data = carbon.TISGetInputSourceProperty(source, property_key)
        layout = core.CFDataGetBytePtr(data) if data else None
        if not layout:
            return {}
        keys = {}
        for code in range(128):
            dead, length, chars = C.c_uint32(), C.c_ulong(), (C.c_uint16 * 4)()
            if carbon.UCKeyTranslate(layout, code, 0, 0, carbon.LMGetKbdType(), 1, C.byref(dead), 4, C.byref(length), chars) == 0 and length.value == 1:
                letter = chr(chars[0]).upper()
                if len(letter) == 1 and letter.isascii() and letter.isalnum():
                    keys.setdefault(letter, code)
        return keys
    finally:
        core.CFRelease(source)


class MacShortcuts(NativeShortcuts):
    def __init__(self, parent=None, api=None, layout=None):
        super().__init__(parent)
        self.api = api or C.CDLL("/System/Library/Frameworks/Carbon.framework/Carbon")
        if api is None:
            self.api.GetApplicationEventTarget.restype = C.c_void_p
            self.api.InstallEventHandler.argtypes = [C.c_void_p, CALLBACK, C.c_uint32, C.POINTER(EventType), C.c_void_p, C.POINTER(C.c_void_p)]
            self.api.InstallEventHandler.restype = C.c_int32
            self.api.RegisterEventHotKey.argtypes = [C.c_uint32, C.c_uint32, HotKeyID, C.c_void_p, C.c_uint32, C.POINTER(C.c_void_p)]
            self.api.RegisterEventHotKey.restype = C.c_int32
            self.api.UnregisterEventHotKey.argtypes = [C.c_void_p]
            self.api.RemoveEventHandler.argtypes = [C.c_void_p]
            self.api.GetEventParameter.argtypes = [C.c_void_p, C.c_uint32, C.c_uint32, C.c_void_p, C.c_ulong, C.c_void_p, C.c_void_p]
            self.api.GetEventParameter.restype = C.c_int32
        self.layout = layout if layout is not None else mac_layout(self.api)
        self.target, self.handler = self.api.GetApplicationEventTarget(), C.c_void_p()
        self.ids, self.refs = {}, []
        self.callback = CALLBACK(self._event)
        event = EventType(KEYBOARD, 6)  # kEventHotKeyPressed
        status = self.api.InstallEventHandler(self.target, self.callback, 1, C.byref(event), None, C.byref(self.handler))
        if status:
            raise RuntimeError("macOS global hotkey handler unavailable")

    def _event(self, _, event, __):
        identifier = HotKeyID()
        status = self.api.GetEventParameter(event, int.from_bytes(b"----", "big"), int.from_bytes(b"hkid", "big"), None, C.sizeof(identifier), None, C.byref(identifier))
        if not status and identifier.signature == SIGNATURE and identifier.id in self.ids:
            self.activated.emit(self.ids[identifier.id])
            return 0
        return -9874

    def register(self, rows):
        accepted, errors, physical = {}, {}, set()
        for index, (key, _, binding) in enumerate(rows):
            modifiers, code = mac_key(binding, self.layout)
            reference = C.c_void_p()
            if code is None:
                errors[key] = "This key is unavailable to macOS hotkeys on the current keyboard layout. Choose another key."
            elif (modifiers, code) in physical:
                errors[key] = "Another action resolves to the same physical key."
            elif self.api.RegisterEventHotKey(code, modifiers, HotKeyID(SIGNATURE, index), self.target, 0, C.byref(reference)) == 0:
                self.refs.append(reference)
                self.ids[index] = key
                physical.add((modifiers, code))
                accepted[key] = binding
            else:
                errors[key] = "macOS could not register this combination. It may be reserved or used by another app."
        self.report(accepted, errors)

    def close(self):
        for reference in self.refs:
            self.api.UnregisterEventHotKey(reference)
        self.refs.clear()
        self.ids.clear()
        if self.handler:
            self.api.RemoveEventHandler(self.handler)
            self.handler = C.c_void_p()
        self.deleteLater()
