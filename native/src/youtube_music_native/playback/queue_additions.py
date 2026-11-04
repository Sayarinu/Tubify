"""Gather manual additions in action order, committing each collection atomically."""

from collections import deque

from PySide6.QtCore import QObject, Signal


class QueueAdditions(QObject):
    changed = Signal()

    def __init__(self, account, player, cache_path, downloads=None, fixture=None, parent=None):
        super().__init__(parent)
        self.worker, self.player = account.worker, player
        self.cache_path, self.downloads, self.fixture = str(cache_path), downloads, fixture
        self.jobs = deque()
        self.request, self.lookup = None, None
        self.message = ""
        account.sessionChanged.connect(self.cancel)
        player.manualQueueCleared.connect(self.cancel)
        if self.worker:
            self.worker.succeeded.connect(self._result)
            self.worker.failed.connect(self._failed)
        if downloads:
            downloads.collectionFound.connect(self._local_result)

    def add(self, media, next=False):
        if media.get("kind", "song") not in {"song", "album", "playlist"}:
            return
        self.jobs.append({"media": dict(media), "next": next, "tracks": [], "offset": 0})
        self.message = ""
        if len(self.jobs) == 1:
            self._start()
        self.changed.emit()

    def _start(self):
        # Drain immediate song/fixture additions without recursively growing the stack.
        while self.jobs:
            job = self.jobs[0]
            media, kind = job["media"], job["media"].get("kind", "song")
            if kind == "song":
                self.player.enqueue([media], job["next"])
                self.jobs.popleft()
            elif self.fixture:
                tracks = [{**track, "kind": "song"} for track in self.fixture.get("shelves", [{}])[0].get("items", [])]
                self.player.enqueue(tracks, job["next"])
                self.jobs.popleft()
            else:
                if self.downloads:
                    self.lookup = self.downloads.lookup(kind, media.get("id", ""))
                else:
                    self._page()
                break
        self.changed.emit()

    def _page(self):
        if not self.worker:
            self._finish(error=True)
            return
        job = self.jobs[0]
        media = job["media"]
        params = {"id": media.get("id", "")}
        if media["kind"] == "album":
            params["allTracks"] = True
        self.request = self.worker.request("catalog", {"cache_path": self.cache_path, "route": media["kind"], "params": params, "offset": job["offset"]})

    def _local_result(self, identifier, collection):
        if self.lookup is None or identifier != self.lookup or not self.jobs:
            return
        self.lookup = None
        if collection:
            self.jobs[0]["tracks"] = collection.get("items", [])
            self._finish()
        else:
            self._page()

    def _result(self, identifier, result):
        if self.request is None or identifier != self.request or not self.jobs:
            return
        self.request = None
        job = self.jobs[0]
        job["tracks"].extend(track for track in result.get("items", []) if track.get("kind") == "song")
        cursor = result.get("cursor")
        if len(job["tracks"]) > 100000 or (cursor is not None and (not isinstance(cursor, int) or cursor <= job["offset"])):
            self._finish(error=True)
        elif cursor is not None:
            job["offset"] = cursor
            self._page()
        else:
            self._finish()

    def _failed(self, identifier, error):
        if self.request is not None and identifier == self.request and self.jobs:
            self.request = None
            self._finish(error=True)

    def _finish(self, error=False):
        job = self.jobs.popleft()
        if error:
            self.message = "Could not add the collection to your queue. Retry from its menu."
        elif not job["tracks"]:
            self.message = "This collection has no songs to queue."
        else:
            self.player.enqueue(job["tracks"], job["next"])
        self._start()

    def cancel(self):
        if self.request is not None and self.worker:
            self.worker.cancel(self.request)
        if self.lookup is not None and self.downloads:
            self.downloads.cancelLookup(self.lookup)
        self.request, self.lookup = None, None
        self.jobs.clear()
        self.message = ""
        self.changed.emit()
