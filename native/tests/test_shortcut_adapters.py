"""OS adapters are isolated and tested with deterministic native API results."""
import ctypes as C
from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication

from youtube_music_native.shortcut_native import HotKeyID, MacShortcuts, SIGNATURE, WinMessage, WindowsShortcuts, mac_key, mac_layout, windows_key


def test_windows_hotkey_flags_conflicts_native_event_and_cleanup():
    app = QCoreApplication.instance() or QCoreApplication([])
    calls, removed, filters = [], [], []
    api = SimpleNamespace(RegisterHotKey=lambda hwnd, identifier, modifiers, code: calls.append((identifier, modifiers, code)) or code != ord('X'), UnregisterHotKey=lambda hwnd, identifier: removed.append(identifier))
    application = SimpleNamespace(installNativeEventFilter=filters.append, removeNativeEventFilter=filters.remove)
    adapter = WindowsShortcuts(api=api, application=application)
    results, triggered = [], []
    adapter.result.connect(lambda *args: results.append(args))
    adapter.activated.connect(triggered.append)
    adapter.register([('toggle', 'Play / pause', 'Ctrl+Alt+Space'), ('next', 'Next', 'Ctrl+Alt+X'), ('media', 'Media play', 'MediaPlay'), ('duplicate', 'Media pause', 'MediaPause')])
    accepted, errors, _, _ = results[-1]
    assert accepted == {'toggle': 'Ctrl+Alt+Space', 'media': 'MediaPlay'}
    assert 'next' in errors and 'duplicate' in errors
    assert calls[0] == (0x5900, 0x4000 | 3, 0x20)
    message = WinMessage()
    message.message, message.wParam = 0x312, 0x5900
    assert adapter.filter.nativeEventFilter(b'windows_dispatcher_MSG', C.addressof(message)) == (True, 0)
    assert triggered == ['toggle']
    assert adapter.filter.nativeEventFilter(b'unknown', C.addressof(message)) == (False, 0)
    adapter.close()
    assert removed == [0x5900, 0x5902] and not filters
    assert windows_key('Shift+F24') == (0x4000 | 4, 0x87)


class FakeCarbon:
    def __init__(self):
        self.registered, self.unregistered, self.removed = [], [], []
        self.event_id = 0

    def GetApplicationEventTarget(self):
        return 42

    def InstallEventHandler(self, target, callback, count, event_type, data, output):
        C.cast(output, C.POINTER(C.c_void_p))[0] = C.c_void_p(13)
        return 0

    def RegisterEventHotKey(self, code, modifiers, identifier, target, options, output):
        if code == 7:
            return -9878
        self.registered.append((code, modifiers, identifier.id))
        C.cast(output, C.POINTER(C.c_void_p))[0] = C.c_void_p(identifier.id + 100)
        return 0

    def UnregisterEventHotKey(self, reference):
        self.unregistered.append(reference.value)

    def RemoveEventHandler(self, handler):
        self.removed.append(handler.value)

    def GetEventParameter(self, event, name, kind, actual, size, result, output):
        C.cast(output, C.POINTER(HotKeyID))[0] = HotKeyID(SIGNATURE, self.event_id)
        return 0


def test_mac_layout_mapping_conflicts_events_and_cleanup():
    app = QCoreApplication.instance() or QCoreApplication([])
    api = FakeCarbon()
    adapter = MacShortcuts(api=api, layout={'P': 35, 'X': 7, 'Q': 35})
    results, triggered = [], []
    adapter.result.connect(lambda *args: results.append(args))
    adapter.activated.connect(triggered.append)
    adapter.register([('toggle', 'Play / pause', 'Ctrl+Alt+P'), ('next', 'Next', 'Ctrl+Alt+X'), ('media', 'Media play', 'MediaPlay'), ('duplicate', 'Same key', 'Ctrl+Alt+Q')])
    accepted, errors, _, _ = results[-1]
    assert accepted == {'toggle': 'Ctrl+Alt+P'}
    assert set(errors) == {'next', 'media', 'duplicate'}
    assert api.registered == [(35, (1 << 12) | (1 << 11), 0)]
    assert adapter._event(None, None, None) == 0 and triggered == ['toggle']
    api.event_id = 99
    assert adapter._event(None, None, None) == -9874
    adapter.close()
    assert api.unregistered == [100] and api.removed == [13]
    assert mac_key('Meta+F20', {}) == (1 << 8, 90)


def test_mac_layout_uses_native_character_count_width_and_releases_source():
    class Function:
        def __init__(self, callback):
            self.callback = callback
        def __call__(self, *args):
            return self.callback(*args)
    released = []
    core = SimpleNamespace(CFDataGetBytePtr=Function(lambda data: 3), CFRelease=Function(released.append))
    def translate(layout, code, action, modifiers, keyboard, options, dead, capacity, length, chars):
        assert isinstance(length._obj, C.c_ulong) and capacity == 4 and options == 1
        length._obj.value = 1 if code == 0 else 0
        chars[0] = ord('a')
        return 0
    carbon = SimpleNamespace(TISCopyCurrentKeyboardLayoutInputSource=Function(lambda: 1), TISGetInputSourceProperty=Function(lambda source, key: 2), LMGetKbdType=Function(lambda: 0), UCKeyTranslate=Function(translate))
    assert mac_layout(carbon, core=core, property_key=C.c_void_p(4)) == {'A': 0}
    assert carbon.UCKeyTranslate.argtypes[7] is C.c_ulong
    assert carbon.UCKeyTranslate.argtypes[8] is C.POINTER(C.c_ulong)
    assert released == [1]
