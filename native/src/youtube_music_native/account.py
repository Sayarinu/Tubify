"""Non-blocking account state exposed to QML; credentials remain in the worker."""

import json
from pathlib import Path
import sys

from PySide6.QtCore import QObject, Property, QSettings, QStandardPaths, QTimer, QUrl, Signal, Slot

from .jobs import Worker


class Account(QObject):
    changed = Signal()
    connectedChanged = Signal()

    def __init__(self, settings_path, fixture=False, worker=None, parent=None):
        super().__init__(parent)
        self.settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
        self._fixture = fixture
        self.worker = None if fixture else (worker if worker is not None else Worker(self))
        self._request = None
        self._operation = ""
        self._busy = False
        self._connected = False
        self._reconnect = False
        self._message = ""
        try:
            self._profile = json.loads(self.settings.value("accountProfile", "{}"))
            if not isinstance(self._profile, dict):
                self._profile = {}
        except (ValueError, TypeError):
            self._profile = {}
        if fixture:
            self._profile = {"name": "Your music", "handle": "", "avatar": ""}
        else:
            self.worker.succeeded.connect(self._succeeded)
            self.worker.failed.connect(self._failed)
            QTimer.singleShot(0, self.restore)

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy

    @Property(bool, notify=connectedChanged)
    def connected(self):
        return self._connected and not self._reconnect

    @Property(bool, notify=changed)
    def reconnect(self):
        return self._reconnect

    @Property(str, notify=changed)
    def message(self):
        return self._message

    @Property("QVariantMap", notify=changed)
    def profile(self):
        return self._profile

    @Property(bool, constant=True)
    def fixtureMode(self):
        return self._fixture

    @Property(bool, constant=True)
    def tauriAvailable(self):
        return sys.platform == "linux" and self._tauri_path().is_file()

    def _tauri_path(self):
        return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)) / "com.carter.youtube-music" / "cookies"

    def _send(self, operation, payload=None):
        if self.worker is None or self._busy:
            return
        self._operation = operation
        self._busy = True
        self._message = ""
        self._request = self.worker.request(operation, payload)
        self.changed.emit()

    @Slot()
    def restore(self):
        self._send("restore")

    @Slot()
    def importTauri(self):
        self._send("import_session", {"path": str(self._tauri_path()), "tauri": True})

    @Slot(QUrl)
    def importFile(self, url):
        if url.isLocalFile():
            self._send("import_session", {"path": url.toLocalFile()})

    @Slot()
    def signOut(self):
        self._send("sign_out")

    @Slot(str)
    def requireReconnect(self, message):
        self._reconnect = True
        self._message = message
        self.changed.emit()
        self.connectedChanged.emit()

    def _succeeded(self, identifier, result):
        if identifier != self._request:
            return
        self._request = None
        self._busy = False
        self._connected = bool(result.get("connected"))
        self._reconnect = False
        self._profile = result.get("profile") or {}
        self._message = "Connected to YouTube Music." if self._connected else ""
        self.settings.setValue("accountProfile", json.dumps(self._profile))
        self.settings.sync()
        self.changed.emit()
        self.connectedChanged.emit()

    def _failed(self, identifier, error):
        if identifier != self._request:
            return
        self._request = None
        self._busy = False
        self._message = error.get("message", "Reconnect YouTube Music.")
        if self._operation == "restore":
            self._reconnect = True
        self.changed.emit()
        self.connectedChanged.emit()

    def close(self):
        if self.worker:
            self.worker.close()
