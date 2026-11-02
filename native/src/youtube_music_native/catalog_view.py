"""QML catalog state with request identity checks for rapid navigation/search."""

import json
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot

SORT_KEYS = ("title", "artist", "album", "duration")
SORTABLE_ROUTES = {"album", "playlist"}
# The provider ignores `order` for these library sections, so it is applied here.
CLIENT_ORDER_ROUTES = {"library_playlists", "library_liked"}
ORDER_SORTS = {"a_to_z": ("title", False), "z_to_a": ("title", True)}


def sort_value(item, key):
    if key == "duration":
        value = item.get("duration")
        return (not isinstance(value, (int, float)) or value <= 0, value if isinstance(value, (int, float)) else 0)
    if key == "artist":
        value = item.get("artist") or ", ".join(artist.get("name", "") for artist in item.get("artists") or [] if isinstance(artist, dict))
    elif key == "album":
        album = item.get("album")
        value = album.get("name", "") if isinstance(album, dict) else ""
    else:
        value = item.get("title", "")
    value = str(value or "").casefold()
    return (not value, value)


def sorted_items(items, key, descending=False):
    """Sort a stable copy; empty values always sink to the end, ties keep source order."""
    if key not in SORT_KEYS:
        return sorted(items, key=lambda item: item.get("position", 0))
    present = [item for item in items if not sort_value(item, key)[0]]
    missing = [item for item in items if sort_value(item, key)[0]]
    present.sort(key=lambda item: item.get("position", 0))
    present.sort(key=lambda item: sort_value(item, key)[1], reverse=descending)
    return present + sorted(missing, key=lambda item: item.get("position", 0))


class CatalogView(QObject):
    changed = Signal()
    navigationStarted = Signal()

    def __init__(self, worker, cache_path, account, parent=None):
        super().__init__(parent)
        self.worker, self.account = worker, account
        self.cache_path = str(Path(cache_path))
        self._request = None
        self._route, self._params = "home", {}
        self._data = {}
        self._busy, self._error, self._append = False, "", False
        self._revision, self._scroll = 0, None
        self._loading_all = False
        settings = getattr(account, "settings", None)
        self._settings = settings
        try:
            stored = json.loads(settings.value("collectionSorts", "{}")) if settings is not None else {}
            self._sorts = {key: (value[0], bool(value[1])) for key, value in stored.items()
                           if isinstance(value, list) and len(value) == 2 and value[0] in SORT_KEYS}
        except (ValueError, TypeError, AttributeError):
            self._sorts = {}
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

    @Property(str, notify=changed)
    def sortKey(self):
        return self._effective_sort()[0]

    @Property(bool, notify=changed)
    def sortDescending(self):
        return self._effective_sort()[1]

    @Property(bool, notify=changed)
    def sortable(self):
        return self._route in SORTABLE_ROUTES

    def _scope(self):
        return f"{self._route}:{self._params.get('id', '')}" if self._route in SORTABLE_ROUTES else None

    def _effective_sort(self):
        if self._route in CLIENT_ORDER_ROUTES:
            return ORDER_SORTS.get(self._params.get("order"), ("", False))
        scope = self._scope()
        return self._sorts.get(scope, ("", False)) if scope else ("", False)

    @Slot(str)
    def sortBy(self, key):
        """Pick a column: first ascending, then descending, then back to the original order."""
        scope = self._scope()
        if not scope or key and key not in SORT_KEYS:
            return
        current, descending = self._sorts.get(scope, ("", False))
        if not key or key == current and descending:
            self._sorts.pop(scope, None)
        elif key == current:
            self._sorts[scope] = (key, True)
        else:
            self._sorts[scope] = (key, False)
        self._save_sorts()
        self._apply_sort()
        self.changed.emit()

    @Slot(str, bool)
    def setSort(self, key, descending):
        scope = self._scope()
        if not scope or key and key not in SORT_KEYS:
            return
        if key:
            self._sorts[scope] = (key, bool(descending))
        else:
            self._sorts.pop(scope, None)
        self._save_sorts()
        self._apply_sort()
        self.changed.emit()

    def _save_sorts(self):
        self._sorts = dict(list(self._sorts.items())[-200:])
        if self._settings is not None:
            self._settings.setValue("collectionSorts", json.dumps({name: list(value) for name, value in self._sorts.items()}))

    def _number(self, items, start=0):
        """Return copies carrying their source position; callers' dicts stay untouched."""
        return [{**item, "position": start + index} if isinstance(item, dict) and "position" not in item else item
                for index, item in enumerate(items)]

    def _apply_sort(self):
        key, descending = self._effective_sort()
        items = self._data.get("items")
        if not isinstance(items, list):
            return
        if key and self._data.get("cursor") is not None and self.worker:
            # A sort must cover the whole collection, so fetch every remaining page first.
            if not self._loading_all:
                self._loading_all = True
                self._send(offset=self._data["cursor"], page_size=100000)
            return
        self._data = {**self._data, "items": sorted_items(items, key, descending)}

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
        self.navigationStarted.emit()
        self._route, self._params = route, dict(params)
        self._data = {}
        self._revision, self._scroll = self._revision + 1, None
        self._loading_all = False
        self._send()

    def showLocal(self, route, data, params=None, scroll=None):
        self.navigationStarted.emit()
        if self.worker and self._request is not None:
            self.worker.cancelQueued(self._request)
        self._request, self._busy, self._error = None, False, ""
        self._route, self._data = route, dict(data)
        self._params = dict(params or {})
        self._revision, self._scroll = self._revision + 1, scroll
        self._loading_all = False
        if isinstance(self._data.get("items"), list):
            self._data["items"] = self._number(self._data["items"])
            self._apply_sort()
        self.changed.emit()

    def snapshot(self):
        return {"route": self._route, "params": self._params, "data": self._data, "scroll": self._scroll}

    def patch(self, values):
        self._data.update(values)
        self.changed.emit()

    @Slot()
    def refresh(self):
        count = max(len(self._data.get("items", [])), len(self._data.get("shelves", [])))
        self._revision += 1
        self._send(refresh=True, page_size=count or None)

    @Slot()
    def more(self):
        if not self._busy and self._data.get("cursor") is not None:
            self._send(offset=self._data["cursor"])

    def _send(self, offset=0, refresh=False, page_size=None):
        if not self.worker:
            return
        if self._request is not None:
            self.worker.cancelQueued(self._request)
        self._busy, self._error, self._append = True, "", offset > 0
        self._request = self.worker.request("catalog", {"cache_path": self.cache_path, "route": self._route, "params": self._params, "offset": offset, "refresh": refresh, "page_size": page_size})
        self.changed.emit()

    def _succeeded(self, identifier, result):
        if identifier != self._request:
            return
        if self._append:
            existing = self._data.get("items", [])
            start = max((item.get("position", -1) for item in existing if isinstance(item, dict)), default=-1) + 1
            result["items"] = existing + self._number(result.get("items", []), start)
            result["shelves"] = self._data.get("shelves", []) + result.get("shelves", [])
        elif isinstance(result.get("items"), list):
            result["items"] = self._number(result["items"])
        self._data, self._busy, self._request = result, False, None
        self._loading_all = False
        self._apply_sort()
        if result.get("warning") == "reconnect":
            self.account.requireReconnect("Your session needs reconnecting. Cached music remains available.")
        self.changed.emit()

    def _failed(self, identifier, error):
        if identifier != self._request:
            return
        self._busy, self._request, self._loading_all = False, None, False
        self._error = error.get("message", "This page could not be loaded. Retry.")
        if error.get("code") in {"reconnect", "AuthError"}:
            self.account.requireReconnect(self._error)
        self.changed.emit()
