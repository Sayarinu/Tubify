"""Validated account mutations and asynchronous feedback for native controls."""

from PySide6.QtCore import QObject, Property, Signal, Slot


class Actions(QObject):
    changed = Signal()
    applied = Signal(dict)

    def __init__(self, account, cache_path, fixture=False, parent=None):
        super().__init__(parent)
        self.account, self.worker, self.cache_path, self.fixture = account, account.worker, str(cache_path), fixture
        self._request, self._busy, self._message = None, False, ""
        if self.worker:
            self.worker.succeeded.connect(self._succeeded)
            self.worker.failed.connect(self._failed)

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy

    @Property(str, notify=changed)
    def message(self):
        return self._message

    @Slot()
    def dismiss(self):
        self._message = ""
        self.changed.emit()

    @Slot(str, str, bool, str)
    def set(self, action, identifier, value, context_id):
        self.run(action, {"id": identifier, "value": value, "contextId": context_id})

    @Slot(str, "QVariantMap")
    def run(self, action, payload):
        if self._busy or self.account.busy:
            return
        if self.fixture:
            self.applied.emit({**payload, "action": action, "id": payload.get("id") or "PLfixture-created"})
            return
        if not self.account.connected:
            self._message = "Reconnect YouTube Music to change your library."
            self.changed.emit()
            return
        self._busy, self._message = True, ""
        self._request = self.worker.request("account_action", {**payload, "action": action, "cache_path": self.cache_path})
        self.changed.emit()

    def _succeeded(self, identifier, result):
        if identifier == self._request:
            self._request, self._busy = None, False
            self.applied.emit(result)
            self.changed.emit()

    def _failed(self, identifier, error):
        if identifier == self._request:
            self._request, self._busy = None, False
            self._message = error.get("message", "Your library could not be updated. Retry.")
            if error.get("code") in {"reconnect", "AuthError"}:
                self.account.requireReconnect(self._message)
            self.changed.emit()
