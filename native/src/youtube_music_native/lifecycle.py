"""Optional desktop lifecycle policy, separate from playback and OS registration."""

from PySide6.QtCore import QCoreApplication, QEvent, QObject, Property, QSettings, QTimer, Signal, Slot
from PySide6.QtWidgets import QSystemTrayIcon

from .startup import StartupError, StartupRegistration


class Lifecycle(QObject):
    changed = Signal()

    def __init__(self, path, player, tray, parent=None, startup=None):
        super().__init__(parent)
        self.settings = QSettings(str(path), QSettings.Format.IniFormat)
        self.player, self.tray = player, tray
        self.startup = startup if startup is not None else StartupRegistration()
        self.window = None
        self._autostart = self.settings.value("autostart", False, type=bool)
        self._startup_requested = self._autostart
        self._minimized = self.settings.value("startMinimized", False, type=bool)
        self._close_to_tray = self.settings.value("closeToTray", False, type=bool)
        self._notifications = self.settings.value("trackNotifications", False, type=bool)
        self._hidden, self._quitting, self._closed = False, False, False
        self._errors, self._status, self._notification_key = {}, "", None
        self.hidden_watch = QTimer(self)
        self.hidden_watch.setInterval(2000)
        self.hidden_watch.timeout.connect(self._check_hidden)
        self.status_timer = QTimer(self)
        self.status_timer.setSingleShot(True)
        self.status_timer.setInterval(4000)
        self.status_timer.timeout.connect(self._clear_status)
        self.tray.changed.connect(self._tray_changed)
        if self._notifications:
            self.player.changed.connect(self._track_changed)
        if QCoreApplication.instance():
            QCoreApplication.instance().installEventFilter(self)

    def eventFilter(self, watched, event):
        # Explicit Quit (including tray/MPRIS) must bypass close-to-tray policy.
        if watched == QCoreApplication.instance() and event.type() == QEvent.Type.Quit:
            self._quitting = True
        return False

    def start(self, window):
        self.window = window
        window.visibleChanged.connect(self._visibility_changed)
        self._notification_key = self._current_key()
        if self._autostart:
            try:
                if not self.startup.is_enabled():
                    self._errors["startup"] = "The login item is missing or outdated. Retry login startup to register this app location."
            except (OSError, StartupError):
                self._errors["startup"] = "Login startup could not be checked. Review your system startup settings, then retry."
        if self._minimized:
            window.showMinimized()
        else:
            window.show()
        self.changed.emit()

    @Property(bool, notify=changed)
    def autostart(self):
        return self._autostart

    @Property(bool, notify=changed)
    def startupAvailable(self):
        return self.startup.supported

    @Property(bool, notify=changed)
    def startMinimized(self):
        return self._minimized

    @Property(bool, notify=changed)
    def closeToTray(self):
        return self._close_to_tray

    @Property(bool, notify=changed)
    def trackNotifications(self):
        return self._notifications

    @Property(str, notify=changed)
    def error(self):
        return "\n".join(self._errors.values())

    @Property(bool, notify=changed)
    def startupError(self):
        return "startup" in self._errors

    @Property(str, notify=changed)
    def status(self):
        return self._status

    @Property(str, notify=changed)
    def capability(self):
        messages = []
        if not self.startupAvailable:
            messages.append(self.startup.disabled_reason or "Login startup is unavailable on this platform.")
        if (self._close_to_tray or self._notifications) and not self.tray.active:
            messages.append("Enable an available system tray to use close-to-tray or track notifications. Closing currently exits the app.")
        elif self._notifications and not self.tray.tray_factory.supportsMessages():
            messages.append("This desktop does not support tray notifications.")
        return "\n".join(messages)

    def _save(self, key, value, message):
        self.settings.setValue(key, value)
        self.settings.sync()
        self._status = message
        self.status_timer.start()
        self.changed.emit()

    def _clear_status(self):
        self._status = ""
        self.changed.emit()

    @Slot(bool)
    def setAutostart(self, enabled):
        if self._closed:
            return
        self._startup_requested = bool(enabled)
        try:
            self.startup.set_enabled(self._startup_requested)
        except (OSError, StartupError) as error:
            # Only our actionable validation messages are exposed; OS errors may contain paths.
            self._errors["startup"] = str(error) if isinstance(error, StartupError) else "Login startup could not be changed. Check your system startup permissions and retry."
            self._status = ""
            self.status_timer.stop()
            self.changed.emit()
            return
        self._errors.pop("startup", None)
        self._autostart = bool(enabled)
        self._save("autostart", self._autostart, "Login startup enabled." if enabled else "Login startup disabled.")

    @Slot()
    def retryAutostart(self):
        self.setAutostart(self._startup_requested)

    @Slot(bool)
    def setStartMinimized(self, enabled):
        self._minimized = bool(enabled)
        self._save("startMinimized", self._minimized, "Startup window preference saved.")

    @Slot(bool)
    def setCloseToTray(self, enabled):
        self._close_to_tray = bool(enabled)
        self._errors.pop("tray", None)
        if not enabled and self._hidden:
            self._restore_window()
        self._save("closeToTray", self._close_to_tray, "Close behavior saved.")

    @Slot(bool)
    def setTrackNotifications(self, enabled):
        enabled = bool(enabled)
        if enabled != self._notifications:
            if enabled:
                self.player.changed.connect(self._track_changed)
            else:
                self.player.changed.disconnect(self._track_changed)
        self._notifications = enabled
        self._notification_key = self._current_key()
        self._save("trackNotifications", enabled, "Track notification preference saved.")

    @Slot(result=bool)
    def hideOnClose(self):
        if self._closed or self._quitting or not self._close_to_tray or not self.window or not self.tray.active:
            return False
        self._hidden = True
        self.window.hide()
        self.hidden_watch.start()
        return True

    def _visibility_changed(self, *args):
        if self.window and self.window.isVisible():
            self._hidden = False
            self.hidden_watch.stop()

    def _restore_window(self):
        self._hidden = False
        self.hidden_watch.stop()
        self.tray.showMain()

    def _check_hidden(self):
        if self._hidden and not self.tray.active:
            self._restore_window()
            self._errors["tray"] = "The system tray became unavailable. The main window was restored."
            self.changed.emit()

    def _tray_changed(self):
        self._check_hidden()
        if self.tray.active:
            self._errors.pop("tray", None)
        self.changed.emit()

    def _current_key(self):
        return self.player.queue.current["key"] if self.player.queue.current else None

    def _track_changed(self):
        if self._closed or not self._notifications or not self.player.playing:
            return
        key = self._current_key()
        if not key or key == self._notification_key:
            return
        self._notification_key = key
        if self.tray.active and self.tray.tray_factory.supportsMessages():
            track = self.player.currentTrack
            title = str(track.get("title") or "Now playing")[:200]
            artist = str(track.get("artist") or " · ".join(str(item.get("name", "")) for item in track.get("artists", []) if isinstance(item, dict)))[:300]
            self.tray.tray.showMessage(title, artist, QSystemTrayIcon.MessageIcon.Information, 5000)
        self.changed.emit()

    def close(self):
        self._closed = True
        self.hidden_watch.stop()
        self.status_timer.stop()
        if self._notifications:
            self.player.changed.disconnect(self._track_changed)
        if QCoreApplication.instance():
            QCoreApplication.instance().removeEventFilter(self)
