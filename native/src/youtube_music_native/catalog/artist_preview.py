"""The first artist of the current song, for the queue dock's now-playing view."""

from collections import OrderedDict

from PySide6.QtCore import Property, QObject, QTimer, Signal

CACHE_SIZE = 32
SETTLE_MS = 400


class ArtistPreview(QObject):
    changed = Signal()

    def __init__(self, player, shell, worker, cache_path, parent=None, fixture=False):
        super().__init__(parent)
        self.player, self.shell, self.worker, self.cache_path, self.fixture = player, shell, worker, str(cache_path), fixture
        self._artist_id = ""
        self._name = self._image = self._audience = self._description = ""
        self._request = None
        self._cache = OrderedDict()
        # Skipping through songs only looks up the one the listener stays on.
        self.settle = QTimer(self)
        self.settle.setSingleShot(True)
        self.settle.setInterval(SETTLE_MS)
        self.settle.timeout.connect(self._load)
        player.changed.connect(self._refresh)
        shell.panelChanged.connect(self._refresh)
        if worker:
            worker.succeeded.connect(self._succeeded)
            worker.failed.connect(self._failed)
        self._refresh()

    @Property(str, notify=changed)
    def name(self):
        return self._name

    @Property(str, notify=changed)
    def image(self):
        return self._image

    @Property(str, notify=changed)
    def audience(self):
        return self._audience

    @Property(str, notify=changed)
    def description(self):
        return self._description

    def _current_artist(self):
        track = self.player.currentTrack
        artists = track.get("artists") or []
        first = artists[0] if artists and isinstance(artists[0], dict) else {}
        identifier = str(first.get("id") or first.get("browseId") or first.get("channelId") or "")
        return identifier, str(first.get("name") or track.get("artist") or "")

    def _show(self, name, image="", audience="", description=""):
        values = (name, image, audience, description)
        if values != (self._name, self._image, self._audience, self._description):
            self._name, self._image, self._audience, self._description = values
            self.changed.emit()

    def _refresh(self):
        if not self.shell.nowPlayingOpen:
            self.settle.stop()
            return
        identifier, name = self._current_artist()
        if identifier == self._artist_id and name == self._name:
            return
        self._artist_id = identifier
        self._request = None
        cached = self._cache.get(identifier)
        self._show(*(cached or (name,)))
        if cached:
            self._cache.move_to_end(identifier)
            self.settle.stop()
        elif identifier:
            self.settle.start()

    def _load(self):
        if self.fixture:
            self._store(self._artist_id, (self._name, "", "1.2M", "A fixture artist description for the now-playing view."))
        elif self.worker and self._artist_id:
            self._request = self.worker.request("catalog", {"cache_path": self.cache_path, "route": "artist", "params": {"id": self._artist_id}})

    def _store(self, identifier, values):
        self._cache[identifier] = values
        self._cache.move_to_end(identifier)
        while len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)
        if identifier == self._artist_id:
            self._show(*values)

    def _succeeded(self, identifier, result):
        if identifier != self._request:
            return
        self._request = None
        self._store(self._artist_id, (str(result.get("title") or self._name), str(result.get("hero") or result.get("thumbnail") or ""),
                                      str(result.get("monthlyListeners") or ""), str(result.get("subtitle") or "")))

    def _failed(self, identifier, _error):
        if identifier == self._request:
            self._request = None
