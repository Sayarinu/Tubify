"""Opt-in global bindings; platform registration never owns playback state."""

import json
import sys

from PySide6.QtCore import QObject, Property, QSettings, Signal, Slot, Qt
from PySide6.QtGui import QGuiApplication


ACTIONS = (
    ("toggle", "Play / pause", "Ctrl+Alt+Space"), ("play", "Play", ""),
    ("pause", "Pause", ""), ("stop", "Stop", "Ctrl+Alt+S"),
    ("previous", "Previous", "Ctrl+Alt+Left"), ("next", "Next", "Ctrl+Alt+Right"),
    ("seekBack", "Seek back 5 seconds", "Ctrl+Alt+J"), ("seekForward", "Seek forward 5 seconds", "Ctrl+Alt+K"),
    ("volumeDown", "Volume down", "Ctrl+Alt+Down"), ("volumeUp", "Volume up", "Ctrl+Alt+Up"),
    ("mute", "Mute / unmute", "Ctrl+Alt+M"), ("like", "Like / remove like", "Ctrl+Alt+L"),
    ("dislike", "Dislike / remove dislike", "Ctrl+Alt+D"),
    ("shuffle", "Shuffle", "Ctrl+Alt+H"), ("repeat", "Repeat mode", "Ctrl+Alt+R"),
)
DEFAULTS = {key: binding for key, _, binding in ACTIONS}
MODIFIERS = ("Ctrl", "Alt", "Shift", "Meta")
KEYS = {name.lower(): name for name in ("Space", "Left", "Right", "Up", "Down", "Home", "End", "PageUp", "PageDown", "Insert", "Delete", "Escape", "Tab", "Enter", "Backspace", "MediaPlay", "MediaPause", "MediaToggle", "MediaStop", "MediaNext", "MediaPrevious", *[f"F{i}" for i in range(1, 25)])}


def normalize(value, platform=sys.platform):
    """A portable single chord; Meta means Command on macOS and Super elsewhere."""
    if not isinstance(value, str) or len(value) > 80:
        raise ValueError("Enter one key combination.")
    if not value.strip():
        return ""
    parts = [part.strip().lower() for part in value.split("+")]
    aliases = {"control": "ctrl", "command": "meta", "cmd": "meta", "super": "meta", "win": "meta", "option": "alt"}
    modifiers = [aliases.get(part, part) for part in parts[:-1]]
    if any(part not in {m.lower() for m in MODIFIERS} for part in modifiers) or len(set(modifiers)) != len(modifiers):
        raise ValueError("Use Ctrl, Alt, Shift or Meta with one key (for example Ctrl+Alt+P).")
    key = parts[-1]
    key = key.upper() if len(key) == 1 and key.isascii() and key.isalnum() else KEYS.get(key)
    if not key:
        raise ValueError("Use a letter, digit, arrow, navigation, function or Media key.")
    chord = "+".join([m for m in MODIFIERS if m.lower() in modifiers] + [key])
    if not set(modifiers) & {"ctrl", "alt", "meta"} and not (key.startswith("Media") or key.startswith("F") and key[1:].isdigit()):
        raise ValueError("Include Ctrl, Alt or Meta so normal typing remains available.")
    reserved = {"Alt+Tab", "Alt+Shift+Tab", "Alt+F4", "Ctrl+Alt+Delete", "Ctrl+Escape"}
    if platform == "win32" and ("meta" in modifiers or key == "F12"):
        raise ValueError("This combination is reserved by Windows.")
    if platform == "darwin":
        reserved |= {"Meta+Space", "Shift+Meta+Space", "Meta+Tab", "Shift+Meta+Tab", "Meta+Q", "Meta+H", "Alt+Meta+Escape"}
    if chord in reserved:
        raise ValueError("This combination is reserved by the desktop.")
    return chord


def platform_adapter(parent):
    if sys.platform == "linux":
        from .shortcut_portal import PortalShortcuts
        return PortalShortcuts(parent)
    from .shortcut_native import WindowsShortcuts, MacShortcuts
    return (WindowsShortcuts if sys.platform == "win32" else MacShortcuts)(parent)


class GlobalShortcuts(QObject):
    changed = Signal()

    def __init__(self, shell, player, library, account, actions, path, parent=None, adapter_factory=platform_adapter):
        super().__init__(parent)
        self.shell, self.player, self.library, self.account, self.actions = shell, player, library, account, actions
        self.settings = QSettings(str(path), QSettings.Format.IniFormat)
        self.factory, self.adapter, self.window = adapter_factory, None, None
        self._enabled = self.settings.value("globalShortcutsEnabled", False, type=bool)
        self._bindings, self._results, self._errors = dict(DEFAULTS), {}, {}
        self._status, self._configure, self._closed = "Global shortcuts are disabled.", False, False
        self._generation = 0
        try:
            saved = json.loads(self.settings.value("globalShortcuts", "{}"))
            if not isinstance(saved, dict):
                raise ValueError("Invalid saved shortcut map")
            for key in DEFAULTS:
                if key in saved:
                    self._bindings[key] = normalize(saved[key])
        except (ValueError, TypeError):
            self._enabled = False
            self._status = "Saved shortcuts could not be read. Reset defaults before enabling."

    def start(self, window):
        self.window = window
        if self._enabled:
            self._register()

    @Property(bool, notify=changed)
    def enabled(self):
        return self._enabled

    @Property(str, notify=changed)
    def status(self):
        return self._status

    @Property(bool, notify=changed)
    def canConfigure(self):
        return self._configure

    @Property(str, constant=True)
    def help(self):
        return "Use one combination, such as Ctrl+Alt+P. Meta means Command on macOS or Super on Linux. On Linux the desktop chooses the final binding; accepted bindings appear below. Existing system media controls remain available."

    @Property("QVariantList", notify=changed)
    def bindings(self):
        return [{"id": key, "title": title, "binding": self._bindings[key], "error": self._errors.get(key, ""), "registered": self._results.get(key, "")} for key, title, _ in ACTIONS]

    def _persist(self):
        self.settings.setValue("globalShortcutsEnabled", self._enabled)
        self.settings.setValue("globalShortcuts", json.dumps(self._bindings))
        self.settings.sync()

    @Slot(bool)
    def setEnabled(self, value):
        if self._closed:
            return
        self._enabled = bool(value)
        self._persist()
        self._register()

    @Slot(str, str, result=bool)
    def setBinding(self, key, value):
        if key not in DEFAULTS or self._closed:
            return False
        try:
            chord = normalize(value)
            if chord and any(other != key and binding == chord for other, binding in self._bindings.items()):
                raise ValueError("Another action already uses this combination.")
        except ValueError as error:
            self._errors[key] = str(error)
            self.changed.emit()
            return False
        self._bindings[key] = chord
        self._persist()
        self._register()
        return True

    @Slot()
    def reset(self):
        self._bindings = dict(DEFAULTS)
        self._persist()
        self._register()

    @Slot()
    def retry(self):
        self._register()

    @Slot()
    def configure(self):
        if self.adapter and self._configure:
            self.adapter.configure()

    def _register(self):
        self._generation += 1
        generation = self._generation
        if self.adapter:
            self.adapter.close()
            self.adapter = None
        self._results, self._errors, self._configure = {}, {}, False
        if not self._enabled or self._closed:
            self._status = "Global shortcuts are disabled."
            self.changed.emit()
            return
        rows, seen = [], set()
        for key, title, _ in ACTIONS:
            binding = self._bindings[key]
            if binding in seen:
                self._errors[key] = "Another action already uses this combination."
            elif binding:
                rows.append((key, title, binding))
                seen.add(binding)
        if not rows:
            self._status = "No shortcuts assigned. Choose a combination below."
            self.changed.emit()
            return
        self._status = "Registering shortcuts with the desktop…"
        self.changed.emit()
        try:
            self.adapter = self.factory(self)
            self.adapter.activated.connect(self._activation, Qt.ConnectionType.QueuedConnection)
            self.adapter.result.connect(self._registration_result, Qt.ConnectionType.QueuedConnection)
            self.adapter.register(rows)
        except Exception:
            if self.adapter:
                self.adapter.close()
                self.adapter = None
            self._registered(generation, {}, {}, "Global shortcuts are unavailable on this desktop. Existing system media controls remain available.", False)

    @Slot(dict, dict, str, bool)
    def _registration_result(self, accepted, errors, message, configurable):
        if self.adapter is not None and self.sender() is self.adapter:
            self._registered(self._generation, accepted, errors, message, configurable)

    @Slot(str)
    def _activation(self, key):
        if self.adapter is not None and self.sender() is self.adapter:
            self._activate(self._generation, key)

    def _registered(self, generation, accepted, errors, message, configurable):
        if generation != self._generation or self._closed:
            return
        self._results = dict(accepted)
        self._errors.update(errors)
        self._status, self._configure = message, configurable
        self.changed.emit()

    def _activate(self, generation, key):
        if self._closed or not self._enabled or generation != self._generation or key not in self._results:
            return
        # Global registration must not bypass the focused window's typing/modal guards.
        focused = QGuiApplication.focusWindow()
        if focused and focused.property("playbackShortcuts") is not True:
            return
        if key == "volumeUp":
            self.shell.setVolume(self.shell.volume + 5)
        elif key == "volumeDown":
            self.shell.setVolume(self.shell.volume - 5)
        elif key == "mute":
            self.shell.toggleMute()
        elif self.player.hasTrack:
            if key in {"like", "dislike"}:
                if (self.account.connected or self.shell.fixtureMode) and not self.actions.busy:
                    self.library.rate(self.player.currentTrack, "LIKE" if key == "like" else "DISLIKE")
            elif key in {"seekBack", "seekForward"}:
                self.player.seek(self.player.position + (-5 if key == "seekBack" else 5))
            elif key in {"shuffle", "repeat"}:
                self.player.handleAction(key)
            else:
                method = {"toggle": "togglePlayback", "play": "resume", "pause": "pause", "stop": "stop", "previous": "previous", "next": "next"}.get(key)
                if method:
                    getattr(self.player, method)()

    def close(self):
        self._closed = True
        self._generation += 1
        if self.adapter:
            self.adapter.close()
            self.adapter = None
