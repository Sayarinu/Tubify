"""QML catalog state with request identity checks for rapid navigation/search."""

import json
import time
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot

from .library import SECTIONS
from .page_model import PageModel
from ..util import needs_reconnect

SORT_KEYS = ("number", "title", "artist", "album", "duration")
SORTABLE_ROUTES = {"album", "playlist"}
# The provider ignores `order` for these library sections, so it is applied here.
CLIENT_ORDER_ROUTES = {"library_playlists", "library_liked"}
# Song lists number their rows, so these orders apply to every section offering them.
NUMBER_ORDERS = {"number_ascending": ("number", False), "number_descending": ("number", True)}
ORDER_SORTS = {"a_to_z": ("title", False), "z_to_a": ("title", True), **NUMBER_ORDERS}
# Library sections and the landing pages are kept in memory so revisits render instantly, then revalidate.
MEMORY_ROUTES = set(SECTIONS.values()) | {"history", "home", "explore"}
MEMORY_TTL = 300
MEMORY_LIMIT = 48
ALWAYS_REVALIDATE = {"history"}


def _without_positions(data):
    """Compare results without the client-side numbering added to each item."""
    items = data.get("items")
    if not isinstance(items, list):
        return data
    return {**data, "items": [{key: value for key, value in item.items() if key != "position"} if isinstance(item, dict) else item for item in items]}


def sort_value(item, key):
    if key == "number":
        return (False, item.get("position", 0))
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
    revalidatingChanged = Signal()
    scrollToTopRequested = Signal()

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
        self._revalidating = False
        self._memory, self._request_key = OrderedDict(), None
        self._fresh_route = None
        self._items_model, self._shelves_model = PageModel(self), PageModel(self, snapshots=True)
        self._model_revision, self._reset_models, self._rows_touched = 0, False, False
        # Connected first, so the models are current before anything else hears of a change.
        self.changed.connect(self._sync_models)
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

    @Property(QObject, constant=True)
    def itemsModel(self):
        return self._items_model

    @Property(QObject, constant=True)
    def shelvesModel(self):
        return self._shelves_model

    @Slot()
    def _sync_models(self):
        # Another page or order starts afresh; anything else keeps the rows and the list's place.
        reset = self._reset_models or self._revision != self._model_revision
        touched, self._model_revision, self._reset_models, self._rows_touched = self._rows_touched, self._revision, False, False
        self._items_model.sync(self._data.get("items") or [], reset, touched)
        self._shelves_model.sync(self._data.get("shelves") or [], reset)

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy

    @Property(bool, notify=revalidatingChanged)
    def revalidating(self):
        """A background refresh of data that is already on screen."""
        return self._revalidating

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
    def reordered(self):
        """The rows differ from the collection's own order."""
        key, descending = self._effective_sort()
        return key not in {"", "number"} or descending

    def _scope(self):
        return f"{self._route}:{self._params.get('id', '')}" if self._route in SORTABLE_ROUTES else None

    def _effective_sort(self):
        order = self._params.get("order")
        if self._route in CLIENT_ORDER_ROUTES or order in NUMBER_ORDERS:
            return ORDER_SORTS.get(order, ("", False))
        scope = self._scope()
        return self._sorts.get(scope, ("number", False)) if scope else ("", False)

    @Slot(str)
    def sortBy(self, key):
        """Pick a column: first ascending, then descending, then back to the original order."""
        scope = self._scope()
        if not scope or key and key not in SORT_KEYS:
            return
        current, descending = self._sorts.get(scope, ("number", False))
        if not key or key == current and descending:
            self._sorts.pop(scope, None)
        elif key == current:
            self._sorts[scope] = (key, True)
        else:
            self._sorts[scope] = (key, False)
        self._save_sorts()
        self._apply_sort()
        self._reset_models = True
        self.changed.emit()

    @Slot(str, bool)
    def setSort(self, key, descending):
        scope = self._scope()
        if not scope or key and key not in SORT_KEYS:
            return
        if key and (key, bool(descending)) != ("number", False):
            self._sorts[scope] = (key, bool(descending))
        else:
            self._sorts.pop(scope, None)
        self._save_sorts()
        self._apply_sort()
        self._reset_models = True
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
        if self.reordered and self._data.get("cursor") is not None and self.worker:
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

    def _memory_key(self):
        profile = getattr(self.account, "profile", None)
        identity = (profile.get("name") or "", profile.get("handle") or "") if isinstance(profile, dict) else ("", "")
        return (identity, self._route, json.dumps(self._params, sort_keys=True, default=str))

    def _remember(self):
        # The key is captured at send time, so a reply for a previous account is never kept.
        key = self._request_key
        if key is None or self._route not in MEMORY_ROUTES or not isinstance(self._data.get("items"), list):
            return
        self._memory.pop(key, None)
        self._memory[key] = {"data": {**self._data, "items": list(self._data["items"])}, "saved": time.monotonic(), "dirty": False}
        while len(self._memory) > MEMORY_LIMIT:
            self._memory.popitem(last=False)

    @Slot()
    @Slot("QStringList")
    def invalidate(self, routes=None):
        """Mark remembered pages so the next visit revalidates them after rendering."""
        routes = None if routes is None else set(routes)
        for (identity, route, params), entry in self._memory.items():
            if routes is None or route in routes:
                entry["dirty"] = True

    @Slot()
    def clearMemory(self):
        self._memory.clear()
        self._request_key = None

    def _set_revalidating(self, value):
        if self._revalidating != value:
            self._revalidating = value
            self.revalidatingChanged.emit()

    @Slot(str, "QVariantMap")
    def load(self, route, params):
        self.navigationStarted.emit()
        self._route, self._params = route, dict(params)
        self._revision, self._scroll = self._revision + 1, None
        self._loading_all = False
        fresh, self._fresh_route = self._fresh_route == route, None
        key = self._memory_key()
        entry = self._memory.get(key) if route in MEMORY_ROUTES and self.worker else None
        if entry is None:
            self._data = {}
            self._send(refresh=fresh)
            return
        self._memory.move_to_end(key)
        if self._request is not None:
            self.worker.cancelQueued(self._request)
        self._request, self._busy, self._error = None, False, ""
        self._set_revalidating(False)
        self._data = {**entry["data"], "items": list(entry["data"]["items"])}
        self._apply_sort()
        stale = entry["dirty"] or time.monotonic() - entry["saved"] >= MEMORY_TTL or route in ALWAYS_REVALIDATE
        if stale and not self._loading_all:
            count = max(len(self._data.get("items", [])), len(self._data.get("shelves", [])))
            self._send(refresh=entry["dirty"], page_size=count or None, revalidate=True)
        else:
            self.changed.emit()

    def showLocal(self, route, data, params=None, scroll=None):
        self.navigationStarted.emit()
        if self.worker and self._request is not None:
            self.worker.cancelQueued(self._request)
        self._request, self._busy, self._error = None, False, ""
        self._set_revalidating(False)
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
        """Publish edits, including those callers already made in place on the rows."""
        self._data.update(values)
        self._rows_touched = True
        self.changed.emit()

    def expectFresh(self, route):
        """Have the next load of this route skip the caches, still showing remembered rows meanwhile."""
        self._fresh_route = route
        self.invalidate([route])

    def refreshFromTop(self):
        """Return to the top and reload the first page behind what is on screen."""
        self._scroll = None
        self.scrollToTopRequested.emit()
        if not self._busy and not self._revalidating:
            self._send(refresh=True, revalidate=True)

    @Slot()
    def refresh(self):
        count = max(len(self._data.get("items", [])), len(self._data.get("shelves", [])))
        self._revision += 1
        self._model_revision = self._revision
        self._send(refresh=True, page_size=count or None)

    @Slot()
    def more(self):
        if not self._busy and not self._revalidating and self._data.get("cursor") is not None:
            self._send(offset=self._data["cursor"])

    def _send(self, offset=0, refresh=False, page_size=None, revalidate=False):
        if not self.worker:
            return
        if self._request is not None:
            self.worker.cancelQueued(self._request)
        # Revalidation keeps the visible page interactive; only real loads are busy.
        self._busy, self._error, self._append = not revalidate, "", offset > 0
        self._set_revalidating(revalidate)
        self._request_key = self._memory_key()
        self._request = self.worker.request("catalog", {"cache_path": self.cache_path, "route": self._route, "params": self._params, "offset": offset, "refresh": refresh, "page_size": page_size})
        self.changed.emit()

    def _succeeded(self, identifier, result):
        if identifier != self._request:
            return
        if self._revalidating:
            self._revalidated(result)
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
        self._remember()
        if result.get("warning") == "reconnect":
            self.account.requireReconnect("Your session needs reconnecting. Cached music remains available.")
        self.changed.emit()

    def _revalidated(self, result):
        """Swap in fresh data in place: same revision and scroll, no signal if nothing changed."""
        previous = self._data
        if isinstance(result.get("items"), list):
            result["items"] = self._number(result["items"])
        self._data, self._busy, self._request = result, False, None
        self._loading_all = False
        self._set_revalidating(False)
        self._apply_sort()
        self._remember()
        if result.get("warning") == "reconnect":
            self.account.requireReconnect("Your session needs reconnecting. Cached music remains available.")
        if self._busy or _without_positions(self._data) != _without_positions(previous):
            self.changed.emit()
        else:
            self._data = previous

    def _failed(self, identifier, error):
        if identifier != self._request:
            return
        if self._revalidating:
            # The remembered page stays on screen; only a lost session needs attention.
            self._request = None
            self._set_revalidating(False)
            if needs_reconnect(error):
                self.account.requireReconnect(error.get("message", "Your session needs reconnecting."))
            return
        self._busy, self._request, self._loading_all = False, None, False
        self._error = error.get("message", "This page could not be loaded. Retry.")
        if needs_reconnect(error):
            self.account.requireReconnect(self._error)
        self.changed.emit()
