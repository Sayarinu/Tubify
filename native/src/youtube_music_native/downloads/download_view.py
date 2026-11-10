"""Local download controls stay independent of online planning and transfers."""

from pathlib import Path
import json
import time

from PySide6.QtCore import QObject, Property, QProcess, QTimer, Signal, Slot

from ..jobs import Worker


class DownloadView(QObject):
    """Download state for QML, split so a progress tick only repaints what it changes.

    `changed` covers the lists and storage; per-song and per-collection state,
    live progress, artwork and the message each have their own signal. QML reads
    single entries through slots (songState, collectionEntry, artworkFor, ...)
    that depend on a revision counter, instead of copying a whole map per read.
    """
    changed = Signal()
    statesChanged = Signal()
    progressChanged = Signal()
    artworkChanged = Signal()
    messageChanged = Signal()
    storageChanged = Signal()
    collectionReady = Signal(dict)
    collectionFound = Signal(int, dict)
    playRequested = Signal(dict, bool)

    def __init__(self, data_dir, fixture=False, parent=None):
        super().__init__(parent)
        self.data_dir, self.fixture = str(Path(data_dir)), fixture
        self.control = None if fixture else Worker(self, idle_ms=30000)
        # Planning and transfers stay up between collections: a whole library queued at
        # once used to relaunch the app as a new worker process for every playlist.
        self.planner = None if fixture else Worker(self, idle_ms=30000)
        self.transfer = None if fixture else Worker(self, idle_ms=30000)
        self._planning = set()
        self._collections, self._pending, self._stopped = [], {}, []
        self._songs, self._entries = [], {}
        self._revision, self._progress_revision, self._artwork_revision = 0, 0, 0
        self._track_states, self._track_progress, self._open_request = {}, {}, None
        self._artwork, self._initialized = {}, fixture
        self._large_artwork, self._artwork_requests, self._artwork_attempts = {}, {}, {}
        self._artwork_times = {}
        self.artwork_worker = None
        self._fixture_bodies = {}
        self._active, self._transfer_request, self._next = None, None, None
        self._bytes, self._free, self._message = 0, 0, ""
        # A planning outcome kept until the next download request replaces it.
        self._notice = ""
        self._minimum_request, self._status_pending = 0, False
        self._allow_network, self._resetting, self._closed = False, False, False
        # Collections shown from memory until something may have changed them.
        self._stale = True
        if fixture:
            tracks = json.loads((Path(__file__).parents[1] / "assets" / "visual-fixture.json").read_text())["shelves"][0]["items"]
            for index, (kind, title, state) in enumerate((("playlist", "Evening focus", "complete"), ("album", "Somewhere quiet", "downloading"), ("playlist", "Long way home", "damaged"), ("song", "A familiar tune", "cancelled"))):
                key = kind + ":fixture-" + str(index)
                values = [{**track, "kind": "song", "duration": 180, "downloadState": "ready" if state == "complete" else "missing"} for track in tracks[:1 if kind == "song" else 6]]
                self._fixture_bodies[key] = {"kind": kind, "id": key.split(":", 1)[1], "title": title, "items": values, "downloadKey": key, "cursor": None, "trackCount": len(values), "duration": sum(track["duration"] for track in values)}
                self._collections.append({"key": key, "id": key.split(":", 1)[1], "kind": kind, "title": title, "state": state, "ready": len(values) if state == "complete" else 1, "total": len(values), "progress": 0.42 if state == "downloading" else 1., "error": ""})
            self._bytes, self._free = 127000000, 32000000000
            self._index()
        if self.control:
            self.control.succeeded.connect(self._result)
            self.control.failed.connect(self._failed)
            self.planner.succeeded.connect(self._scheduled)
            self.planner.failed.connect(self._schedule_failed)
            self.planner.progress.connect(self._planned_one)
            self.transfer.succeeded.connect(self._transferred)
            self.transfer.failed.connect(self._transfer_failed)
            self.transfer.progress.connect(self._progress)
            self.transfer.process.finished.connect(self._flush_stopped)
            QTimer.singleShot(0, lambda: self._send("initialize"))

    @Property("QVariantList", notify=changed)
    def collections(self):
        return self._collections

    @Property("QVariantList", notify=changed)
    def songs(self):
        return self._songs

    @Property("QVariantMap", notify=statesChanged)
    def trackStates(self):
        return self._track_states

    @Property("QVariantMap", notify=progressChanged)
    def trackProgress(self):
        return self._track_progress

    @Property("QVariantMap", notify=artworkChanged)
    def artwork(self):
        return self._artwork

    @Property("QVariantMap", notify=artworkChanged)
    def largeArtwork(self):
        return self._large_artwork

    @Property(int, notify=statesChanged)
    def revision(self):
        return self._revision

    @Property(int, notify=progressChanged)
    def progressRevision(self):
        return self._progress_revision

    @Property(int, notify=artworkChanged)
    def artworkRevision(self):
        return self._artwork_revision

    @Slot(str, result=str)
    def songState(self, video_id):
        return self._track_states.get(video_id, "")

    @Slot(str, result=float)
    def songProgress(self, video_id):
        return float(self._track_progress.get(video_id, 0))

    @Slot(str, result="QVariantMap")
    def collectionEntry(self, key):
        return self._entries.get(key, {})

    @Slot(str, result=str)
    def artworkFor(self, key):
        return self._artwork.get(key, "") if key else ""

    @Slot(str, result=bool)
    def hasArtwork(self, key):
        return key in self._artwork

    @Slot(str, result="QVariantMap")
    def largeArtworkFor(self, key):
        return self._large_artwork.get(key, {})

    def _index(self):
        self._entries = {entry["key"]: entry for entry in self._collections}

    def _states_changed(self):
        self._revision += 1
        self.statesChanged.emit()

    def _artwork_changed(self):
        self._artwork_revision += 1
        self.artworkChanged.emit()

    def _set_message(self, message):
        if message != self._message:
            self._message = message
            self.messageChanged.emit()

    @Slot("QVariantMap", int, result=str)
    def artworkSource(self, media, pixels):
        from ..artwork.artwork_sources import choose, media_variants, with_resized
        return choose(with_resized(media_variants(media), pixels), pixels).get("url", "")

    @Slot("QVariantMap", int)
    @Slot("QVariantMap", int, bool)
    def ensureArtwork(self, media, pixels, retry=False):
        from ..artwork.artwork_sources import choose, media_variants, quality, with_resized
        video_id = media.get("videoId") or media.get("id", "")
        if self.fixture or self._closed or not video_id or not self._initialized:
            return
        pixels = max(1, min(4096, pixels))
        downloaded = video_id in self._artwork or video_id in self._track_states
        if not downloaded and quality(choose(with_resized(media_variants(media), pixels), pixels)) >= pixels:
            # artworkSource already gives QML this exact resizable URL; the worker would
            # only start a process to return the same answer.
            return
        signature = (pixels, self._allow_network, json.dumps(media_variants(media), sort_keys=True), self._artwork.get(video_id, ""))
        if self._artwork_attempts.get(video_id) == signature:
            if not retry or time.monotonic() - self._artwork_times.get(video_id, 0) < 30:
                return
        if not self.artwork_worker:
            # Kept for a minute so consecutive songs do not each pay a process start.
            self.artwork_worker = Worker(self, idle_ms=60000)
            self.artwork_worker.succeeded.connect(self._artwork_ready)
            self.artwork_worker.failed.connect(self._artwork_failed)
        for request, (key, _) in list(self._artwork_requests.items()):
            if key == video_id:
                self.artwork_worker.cancelQueued(request)
                self._artwork_requests.pop(request)
        self._artwork_attempts[video_id] = signature
        self._artwork_times[video_id] = time.monotonic()
        request = self.artwork_worker.request("artwork", {"data_dir": self.data_dir, "media": dict(media), "pixels": pixels, "online": self._allow_network})
        self._artwork_requests[request] = (video_id, signature)
        while len(self._artwork_attempts) > 128:
            removed = next(iter(self._artwork_attempts))
            self._artwork_attempts.pop(removed)
            self._artwork_times.pop(removed, None)

    def _artwork_ready(self, request, result):
        pending = self._artwork_requests.pop(request, None)
        if not pending or result.get("videoId") != pending[0] or self._artwork_attempts.get(pending[0]) != pending[1]:
            return
        before = self._large_artwork.get(pending[0], {})
        if result.get("url") and min(result.get("width", 0), result.get("height", 0)) >= min(before.get("width", 0), before.get("height", 0)):
            self._large_artwork[pending[0]] = result
            while len(self._large_artwork) > 128:
                self._large_artwork.pop(next(iter(self._large_artwork)))
            self._artwork_changed()
        if result.get("upgraded"):
            self._stale = True
            self.refresh()

    def _artwork_failed(self, request, error):
        self._artwork_requests.pop(request, None)
        # Artwork failures leave the visible local cover and playback untouched.

    @Property(bool, notify=changed)
    def initialized(self):
        return self._initialized

    @Property(str, notify=messageChanged)
    def message(self):
        return self._message

    @Property(float, notify=storageChanged)
    def usedBytes(self):
        return float(self._bytes)

    @Property(float, notify=storageChanged)
    def freeBytes(self):
        return float(self._free)

    @Slot(bool)
    def setAccountAvailable(self, available):
        self._allow_network = available
        self._stale = True
        self._pump()

    def _send(self, operation, payload=None, authoritative=False):
        if not self.control or self._closed:
            return None
        request = self.control.request("downloads_" + operation, {"data_dir": self.data_dir, **(payload or {})})
        self._pending[request] = operation
        if operation == "status":
            self._status_pending = True
        if authoritative:
            self._minimum_request = request
        return request

    @Slot("QVariantMap")
    def download(self, media):
        if self.fixture:
            self._set_message("Download preview")
            return
        self._notice = ""
        self._planning.add(self.planner.request("downloads_schedule", {"data_dir": self.data_dir, "media": dict(media)}))
        self._set_message("Preparing download…")

    @Slot("QVariantList")
    def downloadAll(self, playlists):
        if self.fixture:
            self._set_message("Download preview")
            return
        values = [{"kind": "playlist", "id": media.get("id", ""), "title": media.get("title", ""), "thumbnail": media.get("thumbnail", "")}
                  for media in playlists if isinstance(media, dict) and media.get("id")]
        if not values:
            return
        self._notice = ""
        self._planning.add(self.planner.request("downloads_schedule_all", {"data_dir": self.data_dir, "playlists": values}))
        self._set_message("Preparing downloads for every playlist…")

    def _planned_one(self, identifier, progress):
        # Start downloading the first playlists while the rest are still being listed.
        if identifier in self._planning and progress.get("scheduled") and not self._active:
            self.refresh()

    def _clear_notice(self):
        if self._notice:
            self._notice = ""
            if not self._planning:
                self._set_message("")

    def _scheduled(self, identifier, result):
        if identifier not in self._planning:
            return
        self._planning.remove(identifier)
        if result.get("failed"):
            count = result["failed"]
            self._notice = f"{count} playlist{'s' if count != 1 else ''} could not be prepared. Download {'them' if count != 1 else 'it'} from {'their menus' if count != 1 else 'its menu'} to retry."
            QTimer.singleShot(10000, self._clear_notice)
        self._send("status", authoritative=True)

    def _schedule_failed(self, identifier, error):
        if identifier not in self._planning:
            return
        self._planning.remove(identifier)
        if not self._resetting:
            self._set_message(error.get("message", "This download could not be prepared. Retry."))

    @Slot()
    def refresh(self):
        if not self._status_pending:
            self._send("status")

    @Slot()
    def refreshIfStale(self):
        if self._stale:
            self.refresh()

    @Slot(str)
    def open(self, identifier):
        if self.fixture:
            if identifier in self._fixture_bodies:
                self.collectionReady.emit(self._fixture_bodies[identifier])
            return
        if self._open_request is not None:
            self.control.cancelQueued(self._open_request)
        self._open_request = self._send("collection", {"id": identifier})

    @Slot(str, bool)
    def play(self, identifier, shuffle):
        kind, _, media_id = identifier.partition(":")
        self.playRequested.emit({"kind": kind, "id": media_id}, shuffle)

    def lookup(self, kind, identifier):
        return self._send("lookup", {"kind": kind, "id": identifier})

    def known(self, kind, identifier):
        """Whether the downloads list holds this collection; None until it has loaded."""
        if not self._initialized:
            return None
        return kind + ":" + identifier in self._entries

    def cancelLookup(self, request):
        if self.control and request is not None:
            self.control.cancelQueued(request)

    def cancelOpen(self):
        self.cancelLookup(self._open_request)
        self._open_request = None

    @Slot(str)
    def retry(self, identifier):
        if self.fixture:
            self._fixture_update(identifier, "complete")
            return
        self._send("retry", {"id": identifier}, authoritative=True)

    @Slot(str)
    def cancel(self, identifier):
        if self.fixture:
            self._fixture_update(identifier, "cancelled")
            return
        self._stop_and_send("cancel", identifier)

    @Slot(str)
    def remove(self, identifier):
        if self.fixture:
            self._collections = [entry for entry in self._collections if entry["key"] != identifier]
            self._fixture_bodies.pop(identifier, None)
            self._index()
            self.changed.emit()
            self._states_changed()
            return
        self._stop_and_send("remove", identifier)

    def _fixture_update(self, identifier, state):
        for entry in self._collections:
            if entry["key"] == identifier:
                entry.update(state=state, ready=entry["total"] if state == "complete" else entry["ready"])
        self.changed.emit()
        self._states_changed()

    def _stop_and_send(self, operation, identifier):
        # The transfer notices a cancelled or removed song by itself and moves on to the
        # next one, so songs other collections still want keep downloading.
        self._send(operation, {"id": identifier}, authoritative=True)

    def _flush_stopped(self, *args):
        if self.transfer.process.state() == QProcess.ProcessState.NotRunning:
            pending, self._stopped = self._stopped, []
            for operation, payload in pending:
                self._send(operation, payload, authoritative=True)

    @Slot(int, dict)
    def _result(self, identifier, result):
        operation = self._pending.pop(identifier, None)
        if operation == "status":
            self._status_pending = False
        if operation == "collection":
            if identifier == self._open_request:
                self._open_request = None
                self.collectionReady.emit(result)
            return
        if operation == "lookup":
            self.collectionFound.emit(identifier, result)
            return
        if identifier < self._minimum_request or operation is None:
            return
        self._set_message("Preparing download…" if self._planning else self._notice)
        self._stale = False
        # Only what differs is announced, so an unchanged status repaints nothing.
        collections, songs = result.get("collections", []), result.get("songs", [])
        listed_changed = (collections, songs, True) != (self._collections, self._songs, self._initialized)
        states_changed = listed_changed or result.get("trackStates", {}) != self._track_states
        self._track_states = result.get("trackStates", {})
        storage = (result.get("bytes", 0), result.get("freeBytes", 0))
        if storage != (self._bytes, self._free):
            self._bytes, self._free = storage
            self.storageChanged.emit()
        if listed_changed:
            self._collections, self._songs, self._initialized = collections, songs, True
            self._index()
            self.changed.emit()
        if states_changed:
            self._states_changed()
        if result.get("trackProgress", {}) != self._track_progress:
            self._track_progress = result.get("trackProgress", {})
            self._progress_revision += 1
            self.progressChanged.emit()
        if result.get("artwork", {}) != self._artwork:
            self._artwork = result.get("artwork", {})
            self._artwork_changed()
        self._next = result.get("next")
        self._pump()

    def _pump(self):
        mutations = {"remove", "cancel", "retry", "initialize", "fail"}
        if self._closed or self._resetting or self._stopped or not self._allow_network or self._active or not self._next or any(op in mutations for op in self._pending.values()):
            return
        self._active, self._next = self._next, None
        self._transfer_request = self.transfer.request("downloads_run", {"data_dir": self.data_dir, "id": self._active})

    @Slot(int, dict)
    def _progress(self, identifier, progress):
        if identifier != self._transfer_request:
            return
        video_id = progress.get("videoId", "")
        if video_id and not progress.get("done"):
            # Only this song's state and ring change; lists and other rows stay put.
            self._track_progress[video_id] = progress.get("fraction", 0)
            self._progress_revision += 1
            self.progressChanged.emit()
            if self._track_states.get(video_id) != "downloading":
                self._track_states[video_id] = "downloading"
                self._states_changed()
        if progress.get("done"):
            # A finished song changes the collections that hold it and the song list; a
            # status already on its way may predate it, so ask again.
            self._send("status")

    @Slot(int, dict)
    def _transferred(self, identifier, result):
        if identifier != self._transfer_request:
            return
        self._active, self._transfer_request = None, None
        self._send("status", authoritative=True)

    @Slot(int, dict)
    def _transfer_failed(self, identifier, error):
        if identifier != self._transfer_request:
            return
        active = self._active
        self._active, self._transfer_request = None, None
        self._set_message(error.get("message", "Download stopped. Retry to continue."))
        self._send("fail", {"id": active}, authoritative=True)

    @Slot(int, dict)
    def _failed(self, identifier, error):
        operation = self._pending.pop(identifier, None)
        if operation == "initialize":
            self._initialized = True
            self.changed.emit()
        if operation == "lookup":
            self.collectionFound.emit(identifier, {})
        if operation == "status":
            self._status_pending = False
            self._stale = True
        if not self._resetting:
            self._set_message(error.get("message", "This download operation failed. Retry."))

    def resetSession(self):
        if not self.control:
            return
        self._resetting, self._stale = True, True
        if self.artwork_worker:
            self.artwork_worker.reset()
        self._artwork_requests.clear()
        self._artwork_attempts.clear()
        self._artwork_times.clear()
        self._large_artwork.clear()
        self._planning.clear()
        self.planner.reset()
        self._active, self._transfer_request, self._next = None, None, None
        self.control.reset()
        self._stopped.append(("initialize", {}))
        self.transfer.reset()
        self._resetting = False
        self._flush_stopped()

    def close(self):
        self._closed = True
        if self.artwork_worker:
            self.artwork_worker.close()
        if self.control:
            self.control.close()
            self.planner.close()
            self.transfer.close()
