"""On-demand lyrics state, with an isolated worker and lightweight timing updates."""

from bisect import bisect_right

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot

from .jobs import Worker


class LyricView(QObject):
    changed = Signal()
    currentLineChanged = Signal()

    def __init__(self, account, player, data_dir, worker=None, fixture=False, parent=None):
        super().__init__(parent)
        self.account, self.player, self.data_dir, self.fixture = account, player, str(data_dir), fixture
        self.worker = None if fixture else worker if worker is not None else Worker(self, idle_ms=15000)
        self._active, self._loaded, self._busy, self._closed = False, False, False, False
        self._video, self._error, self._request = "", "", None
        self._data, self._starts, self._current = {}, [], -1
        player.changed.connect(self._track_changed)
        player.positionChanged.connect(self._position_changed)
        account.sessionChanged.connect(self._reset_session)
        if self.worker:
            self.worker.succeeded.connect(self._succeeded)
            self.worker.failed.connect(self._failed)
        self._track_changed()

    @Property("QVariantMap", notify=changed)
    def data(self):
        return self._data

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy

    @Property(str, notify=changed)
    def error(self):
        return self._error

    @Property(int, notify=currentLineChanged)
    def currentLine(self):
        return self._current

    @Slot(bool)
    def setActive(self, value):
        self._active = value
        if value and not self._loaded and not self._busy and self._video and not self._closed:
            self._fetch()

    def _track_changed(self):
        video = self.player.currentTrack.get("videoId") or self.player.currentTrack.get("id", "")
        if video == self._video:
            return
        if self.worker and self._request is not None:
            self.worker.cancelQueued(self._request)
        self._video, self._request, self._busy, self._loaded = video, None, False, False
        self._data, self._starts, self._error, self._current = {}, [], "", -1
        self.changed.emit()
        self.currentLineChanged.emit()
        if self._active and video:
            self._fetch()

    @Slot()
    def refresh(self):
        if self._video and not self._closed:
            self._fetch(refresh=True)

    def _fetch(self, refresh=False):
        if self._closed:
            return
        if self.fixture:
            self._data = {"videoId": self._video, "available": True, "timed": True, "source": "Original visual fixture", "lines": [{"text": text, "start": index * 5., "end": (index + 1) * 5.} for index, text in enumerate(("A familiar tune", "A quiet moment in the evening", "The music carries on"))]}
            self._accept()
            return
        if self._request is not None:
            self.worker.cancelQueued(self._request)
        self._busy, self._error = True, ""
        self._request = self.worker.request("lyrics", {"data_dir": self.data_dir, "videoId": self._video, "refresh": refresh})
        self.changed.emit()

    def _succeeded(self, identifier, result):
        if identifier != self._request or result.get("videoId") != self._video:
            return
        self._data, self._request, self._busy = result, None, False
        self._accept()

    def _accept(self):
        self._loaded, self._error = True, ""
        self._starts = [row["start"] for row in self._data.get("lines", [])] if self._data.get("timed") else []
        self.changed.emit()
        self._position_changed()

    def _failed(self, identifier, error):
        if identifier == self._request:
            self._request, self._busy = None, False
            self._error = error.get("message", "Lyrics could not be loaded. Retry when connected.")
            self.changed.emit()

    def _position_changed(self):
        current = bisect_right(self._starts, self.player.position) - 1 if self._starts else -1
        if current >= 0 and self.player.position >= self._data["lines"][current]["end"]:
            current = -1
        if current != self._current:
            self._current = current
            self.currentLineChanged.emit()

    @Slot(int)
    def seekLine(self, index):
        if self._data.get("timed") and 0 <= index < len(self._starts):
            self.player.seek(self._starts[index])

    def _reset_session(self):
        if self.worker:
            self._request, self._busy = None, False
            self.worker.reset()
            if self._active and self._video:
                QTimer.singleShot(0, self._fetch)

    def close(self):
        self._closed = True
        if self.worker:
            self.worker.close()
