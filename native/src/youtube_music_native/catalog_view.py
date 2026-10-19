"""QML catalog state with request identity checks for rapid navigation/search."""

from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot


class CatalogView(QObject):
    changed = Signal()

    def __init__(self, worker, cache_path, account, parent=None):
        super().__init__(parent)
        self.worker, self.account = worker, account
        self.cache_path = str(Path(cache_path))
        self._request = None
        self._route, self._params = "home", {}
        self._data = {}
        self._busy, self._error, self._append = False, "", False
        self._revision, self._scroll = 0, None
        if worker:
            worker.succeeded.connect(self._succeeded)
            worker.failed.connect(self._failed)

    @Property("QVariantMap", notify=changed)
    def data(self):
        return self._data

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy

    @Property(str, notify=changed)
    def error(self):
        return self._error

    @Property(str, notify=changed)
    def route(self):
        return self._route

    @Property("QVariantMap", notify=changed)
    def parameters(self):
        return self._params

    @Property(int, notify=changed)
    def revision(self):
        return self._revision

    @Property(float, notify=changed)
    def scrollPosition(self):
        return self._scroll if self._scroll is not None else 0.

    @Property(bool, notify=changed)
    def hasScrollPosition(self):
        return self._scroll is not None

    @Slot(float)
    def saveScroll(self, value):
        self._scroll = float(value)

    @Slot(str, "QVariantMap")
    def load(self, route, params):
        self._route, self._params = route, dict(params)
        self._data = {}
        self._revision, self._scroll = self._revision + 1, None
        self._send()

    def showLocal(self, route, data, params=None, scroll=None):
        if self.worker and self._request is not None:
            self.worker.cancelQueued(self._request)
        self._request, self._busy, self._error = None, False, ""
        self._route, self._data = route, dict(data)
        self._params = dict(params or {})
        self._revision, self._scroll = self._revision + 1, scroll
        self.changed.emit()

    def snapshot(self):
        return {"route": self._route, "params": self._params, "data": self._data, "scroll": self._scroll}

    def patch(self, values):
        self._data.update(values)
        self.changed.emit()

    @Slot()
    def refresh(self):
        self._send(refresh=True)

    @Slot()
    def more(self):
        if not self._busy and self._data.get("cursor") is not None:
            self._send(offset=self._data["cursor"])

    def _send(self, offset=0, refresh=False):
        if not self.worker:
            return
        if self._request is not None:
            self.worker.cancelQueued(self._request)
        self._busy, self._error, self._append = True, "", offset > 0
        self._request = self.worker.request("catalog", {"cache_path": self.cache_path, "route": self._route, "params": self._params, "offset": offset, "refresh": refresh})
        self.changed.emit()

    def _succeeded(self, identifier, result):
        if identifier != self._request:
            return
        if self._append:
            result["items"] = self._data.get("items", []) + result.get("items", [])
            result["shelves"] = self._data.get("shelves", []) + result.get("shelves", [])
        self._data, self._busy, self._request = result, False, None
        if result.get("warning") == "reconnect":
            self.account.requireReconnect("Your session needs reconnecting. Cached music remains available.")
        self.changed.emit()

    def _failed(self, identifier, error):
        if identifier != self._request:
            return
        self._busy, self._request = False, None
        self._error = error.get("message", "This page could not be loaded. Retry.")
        if error.get("code") in {"reconnect", "AuthError"}:
            self.account.requireReconnect(self._error)
        self.changed.emit()
