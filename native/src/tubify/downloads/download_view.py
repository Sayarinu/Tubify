"""Local download controls stay independent of online planning and transfers."""

from pathlib import Path
import json
import time

from PySide6.QtCore import QObject, Property, QProcess, QSettings, QTimer, Signal, Slot

from ..catalog.catalog_view import searchable, sorted_items
from ..catalog.page_model import PageModel
from ..jobs import Worker

# Chips on the Downloads page, as in Library; Songs lists every downloaded song, wherever it came from.
FILTERS = {"Playlists": "playlist", "Albums": "album", "Songs": "song"}
ORDERS = ["Recently added", "A to Z", "Z to A"]
STYLES = ("tubify", "files")
# How long transfers wait after a failure before trying the queue again.
RESUME_MS = 5 * 60 * 1000
SONG_ORDERS = ORDERS + ["Artist"]


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
    pageChanged = Signal()
    removalRequested = Signal("QVariantMap")
    # Asks to confirm deleting one download's audio files, or every saved file when the entry is empty.
    filesDeletionRequested = Signal("QVariantMap")
    tracksRequested = Signal(list, int)
    collectionReady = Signal(dict)
    collectionFound = Signal(int, dict)
    playRequested = Signal(dict, bool)
    filesChanged = Signal()
    retryableChanged = Signal()
    # A collection's audio files finished saving to this folder.
    filesSaved = Signal(str)

    def __init__(self, data_dir, fixture=False, parent=None, settings_path=None):
        super().__init__(parent)
        self._settings = QSettings(str(settings_path), QSettings.Format.IniFormat) if settings_path else None
        self._filter, self._query = "Playlists", ""
        # Typing filters after a short pause, so each key press doesn't re-sort every download.
        self.query_timer = QTimer(self, singleShot=True, interval=150)
        self.query_timer.timeout.connect(self._show)
        from .saved_files import default_folder
        # Downloads are kept either as private copies inside Tubify, or as audio files in a folder.
        style = str(self._settings.value("downloadStyle", "tubify")) if self._settings else "tubify"
        self._style = style if style in STYLES else "tubify"
        # Music videos take roughly ten times a song's space, so they're downloaded only when asked for.
        self._videos = str(self._settings.value("downloadVideos", "false")).lower() == "true" if self._settings else False
        self._files_folder = str(self._settings.value("audioFilesFolder", "") or "") if self._settings else ""
        self._files_folder = self._files_folder or default_folder()
        self._saved_folders = {}
        saved = self._settings.value("downloadOrders", "{}") if self._settings else "{}"
        try:
            self._orders = {key: value for key, value in json.loads(saved).items() if key in FILTERS and value in SONG_ORDERS}
        except (TypeError, ValueError, AttributeError):
            self._orders = {}
        self.collectionsModel_, self.songsModel_ = PageModel(self), PageModel(self)
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
        self._bytes, self._file_bytes, self._free, self._message = 0, 0, 0, ""
        self._saved_count = 0
        # Downloads Retry Failed would pick up, and whether transfers wait after a failure.
        self._retryable, self._paused = 0, False
        self.resume_timer = QTimer(self, singleShot=True, interval=RESUME_MS)
        self.resume_timer.timeout.connect(self._resume)
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
            songs = {}
            for key, value in self._fixture_bodies.items():
                for track in value["items"]:
                    songs.setdefault(track.get("videoId") or track.get("id"), {**track, "added": 0.})
            self._songs = list(songs.values())
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

    @Property("QVariantList", constant=True)
    def filters(self):
        return list(FILTERS)

    @Property(str, notify=pageChanged)
    def filter(self):
        return self._filter

    @Property("QVariantList", notify=pageChanged)
    def orders(self):
        return SONG_ORDERS if self._filter == "Songs" else ORDERS

    @Property(str, notify=pageChanged)
    def order(self):
        return self._orders.get(self._filter, ORDERS[0])

    @Property(QObject, constant=True)
    def collectionsModel(self):
        return self.collectionsModel_

    @Property(QObject, constant=True)
    def songsModel(self):
        return self.songsModel_

    @Property(int, notify=pageChanged)
    def count(self):
        return (self.songsModel_ if self._filter == "Songs" else self.collectionsModel_).rowCount()

    @Slot(str)
    def setFilter(self, name):
        if name in FILTERS and name != self._filter:
            self._filter = name
            self._show()

    @Property(str, notify=pageChanged)
    def query(self):
        return self._query

    @Slot(str)
    def setQuery(self, text):
        text = str(text)[:200]
        if text != self._query:
            self._query = text
            self.query_timer.start()

    @Slot(str)
    def sort(self, order):
        if order in (SONG_ORDERS if self._filter == "Songs" else ORDERS) and order != self.order:
            self._orders[self._filter] = order
            if self._settings is not None:
                self._settings.setValue("downloadOrders", json.dumps(self._orders))
            self._show()

    def _rows(self):
        if self._filter == "Songs":
            rows = [song for song in self._songs if song.get("downloadState") != "unavailable"]
        else:
            rows = [entry for entry in self._collections if entry.get("kind") == FILTERS[self._filter]]
        words = self._query.casefold().split()
        if words:
            rows = [row for row in rows if all(word in searchable(row) for word in words)]
        order = self.order
        if order == "A to Z" or order == "Z to A":
            return sorted_items(rows, "title", order == "Z to A")
        if order == "Artist":
            return sorted_items(rows, "artist")
        # Newest first; ties keep the order the store listed them in.
        return sorted(rows, key=lambda row: -row.get("added", 0))

    def _show(self):
        """Feed the visible chip's rows to its model, changing only rows that differ."""
        rows = self._rows()
        if self._filter == "Songs":
            self.songsModel_.sync(rows)
        else:
            self.collectionsModel_.sync(rows)
        self.pageChanged.emit()

    @Slot(int)
    def playSongs(self, index):
        """Play the Songs list as shown, from this row; each song is queued once."""
        rows, places, tracks, start = self._rows(), {}, [], 0
        for position, song in enumerate(rows):
            video_id = song.get("videoId") or song.get("id")
            if not video_id:
                continue
            if video_id not in places:
                places[video_id] = len(tracks)
                tracks.append({key: value for key, value in song.items() if key not in {"added", "downloadState"}})
            if position == index:
                start = places[video_id]
        if tracks:
            self.tracksRequested.emit(tracks, start)

    @Slot(str)
    def requestRemoval(self, key):
        if key in self._entries:
            self.removalRequested.emit(self._entries[key])

    def _index(self):
        self._entries = {entry["key"]: entry for entry in self._collections}
        self._show()

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
        if self.fixture or self._closed or not video_id or not self._initialized or str(video_id).startswith("local:"):
            # Local songs already carry their cached artwork.
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

    @Property(float, notify=storageChanged)
    def fileBytes(self):
        return float(self._file_bytes)

    @Property(int, notify=storageChanged)
    def savedFileCount(self):
        """How many audio files Tubify has saved, so the page can offer to delete them."""
        return self._saved_count

    @Slot(str)
    def requestFilesDeletion(self, key):
        if key in self._entries:
            self.filesDeletionRequested.emit(self._entries[key])

    @Slot()
    def requestAllFilesDeletion(self):
        if self._saved_count or self.fixture:
            self.filesDeletionRequested.emit({})

    @Slot(str)
    def deleteFiles(self, key):
        """Delete the audio files Tubify saved for this download."""
        if self.fixture:
            self._set_message("Deleting audio files preview")
            return
        self._send("delete_files", {"id": key}, authoritative=True)
        self._set_message("Deleting audio files…")

    @Slot()
    def deleteAllFiles(self):
        if self.fixture:
            self._set_message("Deleting audio files preview")
            return
        self._send("delete_all_files", {}, authoritative=True)
        self._set_message("Deleting every saved audio file…")

    @Property(int, notify=retryableChanged)
    def retryableCount(self):
        return self._retryable

    @Slot()
    def retryFailed(self):
        """Queue every failed download and audio-file save again, and start transferring."""
        if self.fixture:
            for entry in list(self._collections):
                if entry["state"] in {"failed", "damaged"}:
                    self._fixture_update(entry["key"], "complete")
            return
        self._resume(send=False)
        self._send("retry_failed", authoritative=True)

    def _resume(self, send=True):
        """Let transfers start again after a failure paused them."""
        self.resume_timer.stop()
        if self._paused:
            self._paused = False
            if send:
                self._send("status", authoritative=True)

    @Property(bool, notify=filesChanged)
    def downloadVideos(self):
        return self._videos

    @Slot(bool)
    def setDownloadVideos(self, value):
        if bool(value) != self._videos:
            self._videos = bool(value)
            if self._settings is not None:
                self._settings.setValue("downloadVideos", "true" if self._videos else "false")
            self.filesChanged.emit()

    @Property(str, notify=filesChanged)
    def downloadStyle(self):
        """"tubify" for private offline copies, "files" for audio files in the chosen folder."""
        return self._style

    @Property(str, notify=filesChanged)
    def filesFolder(self):
        return self._files_folder

    @Slot(str)
    def setDownloadStyle(self, style):
        """Keep downloads in the chosen style, converting the ones already downloaded."""
        if style not in STYLES or style == self._style:
            return
        self._style = style
        if self._settings is not None:
            self._settings.setValue("downloadStyle", style)
        self.filesChanged.emit()
        if self.fixture:
            return
        self._send("convert", {"style": style, "folder": self._files_folder}, authoritative=True)
        self._set_message("Saving your downloads as audio files in " + self._files_folder + "…" if style == "files" else "Copying your downloads back into Tubify…")

    @Slot("QVariant")
    def setFilesFolder(self, value):
        from PySide6.QtCore import QUrl

        path = value.toLocalFile() if isinstance(value, QUrl) else QUrl(value).toLocalFile() if str(value).startswith("file:") else str(value or "")
        # QUrl gives forward slashes on Windows; keep the system's own spelling.
        path = str(Path(path)) if path else ""
        # A folder inside Tubify's own data would be cleaned up with it, so it can't hold the person's files.
        if path and Path(path).is_absolute() and Path(path).resolve().is_relative_to(Path(self.data_dir).resolve()):
            self._set_message("Choose a folder outside Tubify's own data.")
            return
        if path and Path(path).is_absolute() and path != self._files_folder:
            self._files_folder = path
            if self._settings is not None:
                self._settings.setValue("audioFilesFolder", path)
            self.filesChanged.emit()

    @Slot()
    def openFilesFolder(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        if Path(self._files_folder).is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._files_folder))
        else:
            self._set_message("No audio files have been saved yet.")

    @Slot("QVariantMap")
    def saveFiles(self, media):
        """Download this music if needed, then save it as audio files in the chosen folder."""
        if self.fixture:
            self._set_message("Saving audio files preview")
            return
        key = media.get("downloadKey") or media.get("key") or ""
        if not key:
            kind, identifier = media.get("kind", "song"), media.get("id") or media.get("videoId") or ""
            key = kind + ":" + identifier if kind + ":" + identifier in self._entries else ""
        if key:
            self._send("save_files", {"id": key, "folder": self._files_folder, "move": self._style == "files"}, authoritative=True)
        else:
            self._planning.add(self.planner.request("downloads_schedule", {"data_dir": self.data_dir, "media": dict(media), "files": self._files_folder, "move": self._style == "files", "videos": self._videos}))
        self._set_message("Saving audio files to " + self._files_folder + "…")

    @Slot(bool)
    def setAccountAvailable(self, available):
        self._allow_network = available
        self._stale = True
        if available:
            self._resume(send=False)
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
        self._resume(send=False)
        files = self._files_folder if self._style == "files" else ""
        self._planning.add(self.planner.request("downloads_schedule", {"data_dir": self.data_dir, "media": dict(media), "files": files, "move": bool(files), "videos": self._videos}))
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
        self._resume(send=False)
        self._planning.add(self.planner.request("downloads_schedule_all", {"data_dir": self.data_dir, "playlists": values, "files": self._files_folder if self._style == "files" else "", "move": self._style == "files", "videos": self._videos}))
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
        self._resume(send=False)
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
        self._resume(send=False)
        self._send("retry", {"id": identifier}, authoritative=True)

    @Slot(str)
    def cancel(self, identifier):
        if self.fixture:
            self._fixture_update(identifier, "cancelled")
            return
        self._stop_and_send("cancel", identifier)

    @Slot(str)
    @Slot(str, bool)
    def remove(self, identifier, files=False):
        if self.fixture:
            self._collections = [entry for entry in self._collections if entry["key"] != identifier]
            self._fixture_bodies.pop(identifier, None)
            self._index()
            self.changed.emit()
            self._states_changed()
            return
        self._send("remove", {"id": identifier, "files": bool(files)}, authoritative=True)

    def _fixture_update(self, identifier, state):
        self._collections = [{**entry, "state": state, "ready": entry["total"] if state == "complete" else entry["ready"]} if entry["key"] == identifier else entry for entry in self._collections]
        self._index()
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
        storage = (result.get("bytes", 0), result.get("fileBytes", 0), result.get("freeBytes", 0), result.get("savedFiles", 0))
        if result.get("retryable", 0) != self._retryable:
            self._retryable = result.get("retryable", 0)
            self.retryableChanged.emit()
        if storage != (self._bytes, self._file_bytes, self._free, self._saved_count):
            self._bytes, self._file_bytes, self._free, self._saved_count = storage
            self.storageChanged.emit()
        for entry in collections:
            files = entry.get("files") or {}
            if files.get("state") == "saved" and self._saved_folders.get(entry["key"]) not in {None, "saved"}:
                self.filesSaved.emit(files.get("folder", ""))
            self._saved_folders[entry["key"]] = files.get("state", "")
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
        mutations = {"remove", "cancel", "retry", "initialize", "fail", "save_files", "convert", "delete_files", "delete_all_files", "retry_failed"}
        # Saving and copying files back need no connection, so they run offline too.
        offline_ok = self._next in {"save", "internalize"}
        if self._closed or self._resetting or self._stopped or self._paused or not (self._allow_network or offline_ok) or self._active or not self._next or any(op in mutations for op in self._pending.values()):
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
        # Starting again straight away would fail the same way, so wait a while or for the person.
        self._paused = True
        self.resume_timer.start()
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
        self._resume(send=False)
        self.control.reset()
        self._stopped.append(("initialize", {}))
        self.transfer.reset()
        self._resetting = False
        self._flush_stopped()

    def close(self):
        self._closed = True
        self.resume_timer.stop()
        self.query_timer.stop()
        if self.artwork_worker:
            self.artwork_worker.close()
        if self.control:
            self.control.close()
            self.planner.close()
            self.transfer.close()
