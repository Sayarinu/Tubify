"""Debounced suggestions and supported music-only search filters."""

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot


FILTERS = {"All": None, "Songs": "songs", "Albums": "albums", "Artists": "artists", "Playlists": "playlists"}


class Search(QObject):
    changed = Signal()

    def __init__(self, shell, account, view, cache_path, fixture=None, parent=None):
        super().__init__(parent)
        self.shell, self.worker, self.view = shell, account.worker, view
        self.cache_path, self.fixture = str(cache_path), fixture
        self._query, self._typed, self._filter = "", "", "All"
        self._suggestions, self._request = [], None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(180)
        self.timer.timeout.connect(self._suggest)
        shell.searchRequested.connect(self.submit)
        view.changed.connect(self._restore_filter)
        if self.worker:
            self.worker.succeeded.connect(self._suggested)
            self.worker.failed.connect(self._failed)

    @Property("QVariantList", notify=changed)
    def suggestions(self):
        return self._suggestions

    @Property("QVariantList", constant=True)
    def filters(self):
        return list(FILTERS)

    @Property(str, notify=changed)
    def selectedFilter(self):
        return self._filter

    @Slot(str)
    def suggest(self, query):
        self._typed = query.strip()
        self.clearSuggestions()
        if len(self._typed) >= 2:
            self.timer.start()

    @Slot()
    def clearSuggestions(self):
        self.timer.stop()
        if self.worker and self._request is not None:
            self.worker.cancelQueued(self._request)
        self._request, self._suggestions = None, []
        self.changed.emit()

    def _suggest(self):
        if self.fixture:
            self._suggestions = [self._typed, self._typed + " music", self._typed + " songs"]
            self.changed.emit()
        elif self.worker:
            self._request = self.worker.request("catalog", {"cache_path": self.cache_path, "route": "suggestions", "params": {"query": self._typed}})

    def _suggested(self, identifier, result):
        if identifier == self._request:
            self._request = None
            self._suggestions = [value[:512] for value in result.get("suggestions", []) if isinstance(value, str) and value.strip()][:10]
            self.changed.emit()

    def _failed(self, identifier, error):
        if identifier == self._request:
            self._request, self._suggestions = None, []
            self.changed.emit()

    @Slot(str)
    def submit(self, query):
        self.clearSuggestions()
        self._query = query.strip()
        params = {"query": self._query, "filter": FILTERS[self._filter]}
        if self.fixture:
            values = [value for section in self.fixture.get("shelves", []) for value in section.get("items", [])]
            self.view.showLocal("search", {"title": self._query, "items": values, "shelves": [], "cursor": None}, params)
        else:
            self.view.load("search", params)

    @Slot(str)
    def selectFilter(self, value):
        if value in FILTERS and value != self._filter:
            self._filter = value
            self.changed.emit()
            if self._query:
                self.submit(self._query)

    def _restore_filter(self):
        if self.view.route != "search":
            return
        params = self.view.parameters
        query = params.get("query", "")
        selected = next((label for label, value in FILTERS.items() if value == params.get("filter")), "All")
        if query != self._query or selected != self._filter:
            self._query, self._filter = query, selected
            self.changed.emit()
