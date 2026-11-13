"""Local Music for QML: chosen folders, scanned in a worker, shown without resetting lists."""

import json
import os
from pathlib import Path
import time

from PySide6.QtCore import QFileSystemWatcher, QObject, Property, QSettings, QTimer, QUrl, Signal, Slot

from ..catalog.page_model import PageModel
from ..jobs import Worker

FILTERS = ["Songs", "Albums", "Artists", "Folders"]
ORDERS = {
    "Songs": ["Recently added", "A to Z", "Z to A", "Artist", "Album"],
    "Albums": ["Recently added", "A to Z", "Z to A", "Artist"],
    "Artists": ["A to Z", "Z to A", "Most songs"],
    "Folders": ["Recently added", "A to Z"],
}
# A library last scanned longer ago than this is rescanned when the page opens or the app starts.
STALE_SECONDS = 600
# Folder changes are collected for this long before one rescan.
WATCH_DELAY_MS = 5000
WATCH_LIMIT = 256
# Rows on screen refresh at most this often while a scan reports progress.
PROGRESS_FETCH_SECONDS = 1.
STATE_LABELS = {"missing": "File missing", "offline": "Drive not connected", "unplayable": "Can't play this format"}


def folded(value):
    return str(value or "").casefold()


def album_key(song):
    return folded(song.get("albumArtist") or song.get("artist")) + "\0" + folded(song.get("albumName"))


def artist_key(song):
    return folded(song.get("albumArtist") or song.get("artist"))


class LocalView(QObject):
    changed = Signal()
    pageChanged = Signal()
    scanChanged = Signal()
    messageChanged = Signal()
    folderRemovalRequested = Signal("QVariantMap")
    tracksRequested = Signal(list, int)
    shuffleRequested = Signal(list, str)
    queueRequested = Signal(list, bool)
    collectionReady = Signal(dict)

    def __init__(self, data_dir, fixture=False, parent=None, settings_path=None, control=None, scanner=None):
        super().__init__(parent)
        self.data_dir, self.fixture = str(Path(data_dir)), fixture
        self._settings = QSettings(str(settings_path), QSettings.Format.IniFormat) if settings_path else None
        saved = self._settings.value("localOrders", "{}") if self._settings else "{}"
        try:
            self._orders = {key: value for key, value in json.loads(saved).items() if value in ORDERS.get(key, [])}
        except (TypeError, ValueError, AttributeError):
            self._orders = {}
        self._filter, self._query = "Songs", ""
        self._songs, self._folders, self._revision = {}, [], 0
        self._albums, self._artists = None, None
        self.songsModel_, self.cardsModel_ = PageModel(self), PageModel(self)
        self._count, self._message, self._initialized = 0, "", fixture
        self._scanning, self._scan_progress, self._scan_label = False, 0., ""
        self._scan_request, self._control_requests, self._pending_scans = None, set(), []
        self._last_fetch, self._fetching = 0., False
        self._closed = False
        # Scans run on their own worker, so adding or removing a folder never waits behind one.
        self.control = None if fixture else control or Worker(self, idle_ms=30000)
        self.scanner = None if fixture else scanner or Worker(self, idle_ms=30000)
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self._folder_changed)
        self._changed_paths, self._watches = set(), {}
        self.watch_timer = QTimer(self, singleShot=True, interval=WATCH_DELAY_MS)
        self.watch_timer.timeout.connect(self._rescan_changed)
        # Files still being written are picked up by one follow-up scan.
        self.settle_timer = QTimer(self, singleShot=True, interval=7000)
        self.settle_timer.timeout.connect(lambda: self.rescan(-1))
        self.query_timer = QTimer(self, singleShot=True, interval=150)
        self.query_timer.timeout.connect(self._show)
        if fixture:
            self._load_fixture()
        else:
            self.control.succeeded.connect(self._result)
            self.control.failed.connect(self._failed)
            self.scanner.succeeded.connect(self._scanned)
            self.scanner.failed.connect(self._scan_failed)
            self.scanner.progress.connect(self._scan_progressed)
            QTimer.singleShot(0, lambda: self._send("local_changes", {"since": 0}, initial=True))

    def _load_fixture(self):
        tracks = json.loads((Path(__file__).parents[1] / "assets" / "visual-fixture.json").read_text())["shelves"][0]["items"]
        folders = [{"id": 1, "path": "/fixture/Music", "name": "Music", "state": "ready", "scanned": 1., "songs": 0, "missing": 0},
                   {"id": 2, "path": "/fixture/External drive", "name": "External drive", "state": "offline", "scanned": 1., "songs": 0, "missing": 0}]
        songs = []
        for index, track in enumerate(tracks):
            state = "offline" if index == len(tracks) - 1 else "missing" if index == len(tracks) - 2 else "ready"
            identifier = f"local:fixture{index:015}"
            songs.append({"id": identifier, "localId": identifier, "videoId": identifier, "kind": "song", "local": True,
                          "folder": 2 if state == "offline" else 1, "path": f"/fixture/Music/{index:02} {track.get('title', '')}.flac",
                          "title": track.get("title", ""), "artist": track.get("artist", ""), "albumName": "Evening sessions" if index < 4 else "Quiet hours",
                          "album": {"id": "", "name": "Evening sessions" if index < 4 else "Quiet hours"}, "albumArtist": track.get("artist", ""),
                          "track": index + 1, "disc": 0, "year": 2026, "duration": 180 + index, "codec": "FLAC", "sampleRate": 44100,
                          "thumbnail": track.get("thumbnail", ""), "tagsReadable": index != 1, "state": state, "available": state == "ready",
                          "added": float(index), "size": 1})
        for folder in folders:
            folder["songs"] = sum(1 for song in songs if song["folder"] == folder["id"])
            folder["missing"] = sum(1 for song in songs if song["folder"] == folder["id"] and song["state"] == "missing")
        self._apply({"full": True, "revision": 1, "folders": folders, "songs": songs, "removed": []})

    # Properties
    @Property(bool, notify=changed)
    def initialized(self):
        return self._initialized

    @Property("QVariantList", notify=changed)
    def folders(self):
        return self._folders

    @Property(int, notify=changed)
    def songCount(self):
        return len(self._songs)

    @Property(str, notify=changed)
    def summary(self):
        songs, folders = len(self._songs), len(self._folders)
        text = f"{songs:,} song{'s' if songs != 1 else ''} · {folders} folder{'s' if folders != 1 else ''}"
        offline = sum(1 for folder in self._folders if folder["state"] == "offline")
        missing = sum(1 for song in self._songs.values() if song["state"] == "missing")
        if offline:
            text += f" · {offline} not connected"
        if missing:
            text += f" · {missing:,} missing"
        return text

    @Property(bool, notify=scanChanged)
    def scanning(self):
        return self._scanning

    @Property(float, notify=scanChanged)
    def scanProgress(self):
        return self._scan_progress

    @Property(str, notify=scanChanged)
    def scanLabel(self):
        return self._scan_label

    @Property(str, notify=messageChanged)
    def message(self):
        return self._message

    @Property("QVariantList", constant=True)
    def filters(self):
        return FILTERS

    @Property(str, notify=pageChanged)
    def filter(self):
        return self._filter

    @Property("QVariantList", notify=pageChanged)
    def orders(self):
        return ORDERS[self._filter]

    @Property(str, notify=pageChanged)
    def order(self):
        return self._orders.get(self._filter, ORDERS[self._filter][0])

    @Property(str, notify=pageChanged)
    def query(self):
        return self._query

    @Property(int, notify=pageChanged)
    def count(self):
        return self._count

    @Property(QObject, constant=True)
    def songsModel(self):
        return self.songsModel_

    @Property(QObject, constant=True)
    def cardsModel(self):
        return self.cardsModel_

    @Slot(str, result=str)
    def stateLabel(self, state):
        return STATE_LABELS.get(state, "")

    # Page controls
    @Slot(str)
    def setFilter(self, name):
        if name in FILTERS and name != self._filter:
            self._filter = name
            self._show(reset=True)

    @Slot(str)
    def sort(self, order):
        if order in ORDERS[self._filter] and order != self.order:
            self._orders[self._filter] = order
            if self._settings is not None:
                self._settings.setValue("localOrders", json.dumps(self._orders))
            self._show(reset=True)

    @Slot(str)
    def setQuery(self, text):
        text = str(text)[:200]
        if text != self._query:
            self._query = text
            # Typing filters after a short pause, so each key press doesn't re-sort a large library.
            self.query_timer.start()

    def _groups(self):
        if self._albums is None:
            albums, artists = {}, {}
            for song in self._songs.values():
                if song.get("albumName"):
                    key = album_key(song)
                    album = albums.get(key)
                    if album is None:
                        album = albums[key] = {"key": "album:" + key, "id": "album:" + key, "kind": "album", "local": True,
                                               "title": song["albumName"], "artist": song.get("albumArtist") or song.get("artist", ""),
                                               "thumbnail": "", "year": song.get("year", 0), "added": song["added"], "songs": 0}
                    album["songs"] += 1
                    album["added"] = max(album["added"], song["added"])
                    album["thumbnail"] = album["thumbnail"] or song.get("thumbnail", "")
                name = song.get("albumArtist") or song.get("artist")
                if name:
                    key = artist_key(song)
                    artist = artists.get(key)
                    if artist is None:
                        artist = artists[key] = {"key": "artist:" + key, "id": "artist:" + key, "kind": "artist", "local": True,
                                                 "title": name, "thumbnail": "", "songs": 0}
                    artist["songs"] += 1
                    artist["thumbnail"] = artist["thumbnail"] or song.get("thumbnail", "")
            self._albums, self._artists = albums, artists
        return self._albums, self._artists

    def _rows(self):
        words = folded(self._query).split()

        def matches(*values):
            text = " ".join(folded(value) for value in values)
            return all(word in text for word in words)

        order = self.order
        if self._filter == "Songs":
            rows = [song for song in self._songs.values() if not words or matches(song["title"], song["artist"], song.get("albumName"))]
            keys = {"A to Z": "title", "Z to A": "title", "Artist": "artist", "Album": "albumName"}
            if order in keys:
                field = keys[order]
                rows.sort(key=lambda song: (folded(song.get(field)) == "", folded(song.get(field)), song.get("disc", 0), song.get("track", 0), folded(song["title"])),
                          reverse=order == "Z to A")
            else:
                rows.sort(key=lambda song: -song["added"])
            return rows
        if self._filter == "Folders":
            rows, covers = [], {}
            for song in self._songs.values():
                if song.get("thumbnail"):
                    covers.setdefault(song.get("folder"), song["thumbnail"])
            for folder in self._folders:
                if words and not matches(folder["name"], folder["path"]):
                    continue
                state = "Not connected" if folder["state"] == "offline" else "Scanning" if folder["state"] == "scanning" else ""
                details = [f"{folder['songs']:,} songs"] + ([f"{folder['missing']:,} missing"] if folder["missing"] else []) + ([state] if state else [])
                rows.append({"key": "folder:" + str(folder["id"]), "id": folder["id"], "kind": "folder", "local": True, "title": folder["name"],
                             "artist": " · ".join(details), "path": folder["path"], "state": folder["state"], "missing": folder["missing"],
                             "thumbnail": covers.get(folder["id"], ""), "added": folder.get("added", 0)})
            if order == "A to Z":
                rows.sort(key=lambda row: folded(row["title"]))
            else:
                rows.sort(key=lambda row: -row["added"])
            return rows
        albums, artists = self._groups()
        if self._filter == "Albums":
            rows = [dict(album, label="Album") for album in albums.values() if not words or matches(album["title"], album["artist"])]
            if order in {"A to Z", "Z to A"}:
                rows.sort(key=lambda row: folded(row["title"]), reverse=order == "Z to A")
            elif order == "Artist":
                rows.sort(key=lambda row: (folded(row["artist"]), folded(row["title"])))
            else:
                rows.sort(key=lambda row: -row["added"])
            return rows
        rows = [dict(artist) for artist in artists.values() if not words or matches(artist["title"])]
        if order == "Most songs":
            rows.sort(key=lambda row: (-row["songs"], folded(row["title"])))
        else:
            rows.sort(key=lambda row: folded(row["title"]), reverse=order == "Z to A")
        return rows

    def _show(self, reset=False):
        """Feed the visible chip's rows to its model, changing only rows that differ."""
        rows = self._rows()
        self._count = len(rows)
        if self._filter == "Songs":
            self.songsModel_.sync(rows, reset=reset)
        else:
            self.cardsModel_.sync(rows, reset=reset)
        self.pageChanged.emit()

    # Worker results
    def _send(self, operation, payload=None, initial=False):
        if self._closed or not self.control:
            return None
        request = self.control.request(operation, {"data_dir": self.data_dir, **(payload or {})})
        self._control_requests.add(request)
        if operation == "local_changes":
            self._fetching = True
        if initial:
            self._initial_request = request
        return request

    def _result(self, identifier, result):
        if identifier not in self._control_requests:
            return
        self._control_requests.discard(identifier)
        self._fetching = False
        self._apply(result)
        if "folder" in result:
            # A newly added folder is scanned straight away.
            self.rescan(int(result["folder"]))
        if identifier == getattr(self, "_initial_request", None):
            self._initial_request = None
            self._initialized = True
            self.changed.emit()
            self._scan_if_stale()

    def _failed(self, identifier, error):
        if identifier not in self._control_requests:
            return
        self._control_requests.discard(identifier)
        self._fetching = False
        if identifier == getattr(self, "_initial_request", None):
            self._initial_request, self._initialized = None, True
            self.changed.emit()
        self._set_message(error.get("message", "Local Music couldn't be updated. Try again."))

    def _apply(self, result):
        if not isinstance(result, dict) or "folders" not in result:
            return
        if result.get("full"):
            self._songs = {song["id"]: song for song in result.get("songs", [])}
        else:
            for song_id in result.get("removed", []):
                self._songs.pop(song_id, None)
            for song in result.get("songs", []):
                self._songs[song["id"]] = song
        self._folders = result["folders"]
        self._revision = max(self._revision, int(result.get("revision", 0))) if not result.get("full") else int(result.get("revision", 0))
        self._albums = self._artists = None
        self._watch(result.get("watch"))
        self.changed.emit()
        self._show()

    def _set_message(self, message):
        if message != self._message:
            self._message = message
            self.messageChanged.emit()

    # Scanning
    def _scan_if_stale(self):
        now = time.time()
        if self._folders and any(now - folder.get("scanned", 0) > STALE_SECONDS or folder["state"] in {"new", "offline"} for folder in self._folders):
            self.rescan(-1)

    @Slot()
    def refreshIfStale(self):
        if self._initialized and not self._scanning:
            self._scan_if_stale()

    @Slot(int)
    def rescan(self, folder_id=-1):
        if self._closed or self.fixture:
            return
        target = None if folder_id is None or folder_id < 0 else int(folder_id)
        if self._scanning:
            if target not in self._pending_scans and None not in self._pending_scans:
                self._pending_scans.append(target)
            return
        self._scanning, self._scan_progress = True, 0.
        self._scan_label = "Looking for music…"
        self.scanChanged.emit()
        self._scan_request = self.scanner.request("local_scan", {"data_dir": self.data_dir, **({"id": target} if target is not None else {})})

    def _folder_name(self, folder_id):
        return next((folder["name"] for folder in self._folders if folder["id"] == folder_id), "music")

    def _scan_progressed(self, identifier, value):
        if identifier != self._scan_request:
            return
        total, scanned = int(value.get("total") or 0), int(value.get("scanned") or 0)
        name = self._folder_name(value.get("folder"))
        if value.get("phase") == "listing":
            self._scan_progress, self._scan_label = 0., f"Looking for music in {name}…"
        elif total:
            self._scan_progress = scanned / total
            self._scan_label = f"Scanning {name} · {scanned:,} of {total:,}"
        self.scanChanged.emit()
        # Show new songs as they are found, without waiting for the whole scan.
        if value.get("revision", 0) > self._revision and not self._fetching and time.monotonic() - self._last_fetch >= PROGRESS_FETCH_SECONDS:
            self._last_fetch = time.monotonic()
            self._send("local_changes", {"since": self._revision})

    def _scanned(self, identifier, result):
        if identifier != self._scan_request:
            return
        self._scan_request, self._scanning = None, False
        self._apply(result)
        added, missing, offline = result.get("added", 0), result.get("missing", 0), result.get("offline", 0)
        parts = ([f"{added:,} new song{'s' if added != 1 else ''}"] if added else []) + ([f"{missing:,} missing"] if missing else []) + \
            ([f"{offline} folder{'s' if offline != 1 else ''} not connected"] if offline else [])
        self._set_message("Scan finished · " + ", ".join(parts) if parts else "")
        self._scan_label = ""
        self.scanChanged.emit()
        if result.get("waiting"):
            self.settle_timer.start()
        self._next_scan()

    def _scan_failed(self, identifier, error):
        if identifier != self._scan_request:
            return
        self._scan_request, self._scanning, self._scan_label = None, False, ""
        self.scanChanged.emit()
        self._set_message(error.get("message", "Local Music couldn't be scanned. Try again."))
        self._next_scan()

    def _next_scan(self):
        if self._pending_scans:
            target = self._pending_scans.pop(0)
            self.rescan(-1 if target is None else target)

    # A bounded watcher: each folder and its first level of subfolders, so new albums and
    # finished downloads in an artist folder trigger one rescan of that folder.
    def _watch(self, paths):
        """paths maps folder ids to their watched paths; folders no longer chosen stop being watched."""
        if isinstance(paths, dict):
            self._watches.update({str(key): [path for path in value if isinstance(path, str)] for key, value in paths.items() if isinstance(value, list)})
        chosen = {str(folder["id"]) for folder in self._folders}
        self._watches = {key: value for key, value in self._watches.items() if key in chosen}
        wanted = list(dict.fromkeys(path for value in self._watches.values() for path in value))[:WATCH_LIMIT]
        current = set(self.watcher.directories())
        stale = [path for path in current if path not in wanted]
        if stale:
            self.watcher.removePaths(stale)
        fresh = [path for path in wanted if path not in current]
        if fresh:
            self.watcher.addPaths(fresh)

    def _folder_changed(self, path):
        self._changed_paths.add(path)
        self.watch_timer.start()

    def _rescan_changed(self):
        paths, self._changed_paths = self._changed_paths, set()
        targets = set()
        for path in paths:
            key = os.path.normcase(os.path.abspath(path))
            owner = max((folder for folder in self._folders if key == os.path.normcase(folder["path"]) or key.startswith(os.path.normcase(folder["path"]).rstrip(os.sep) + os.sep)),
                        key=lambda folder: len(folder["path"]), default=None)
            if owner:
                targets.add(owner["id"])
        for target in sorted(targets):
            self.rescan(target)

    # Folders
    @Slot("QVariant")
    def addFolder(self, value):
        path = value.toLocalFile() if isinstance(value, QUrl) else QUrl(value).toLocalFile() if str(value).startswith("file:") else str(value)
        if not path:
            return
        self._set_message("")
        self._send("local_add_folder", {"path": path})

    @Slot(str)
    def ensureFolder(self, path):
        """Show newly saved audio files: add their folder, or rescan the chosen folder that holds it."""
        if not path:
            return
        key = os.path.normcase(os.path.abspath(path))
        owner = next((folder for folder in self._folders if key == os.path.normcase(folder["path"])
                      or key.startswith(os.path.normcase(folder["path"]).rstrip(os.sep) + os.sep)), None)
        if owner:
            self.rescan(owner["id"])
        elif self._initialized:
            self.addFolder(path)

    @Slot(int)
    def requestFolderRemoval(self, folder_id):
        folder = next((folder for folder in self._folders if folder["id"] == folder_id), None)
        if folder:
            self.folderRemovalRequested.emit(folder)

    @Slot(int)
    def removeFolder(self, folder_id):
        if self.fixture:
            self._folders = [folder for folder in self._folders if folder["id"] != folder_id]
            self._songs = {key: song for key, song in self._songs.items() if song["folder"] != folder_id}
            self._albums = None
            self.changed.emit()
            self._show()
            return
        self._send("local_remove_folder", {"id": int(folder_id)})
        self._set_message("Folder removed from Local Music. Its files weren't changed.")

    @Slot(int)
    def forgetMissing(self, folder_id=-1):
        self._send("local_forget_missing", {"id": None if folder_id < 0 else int(folder_id)})

    @Slot(int)
    def showFolder(self, folder_id):
        from PySide6.QtGui import QDesktopServices

        folder = next((folder for folder in self._folders if folder["id"] == folder_id), None)
        if folder and os.path.isdir(folder["path"]):
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder["path"]))

    # Songs
    @Slot(str)
    def removeSong(self, song_id):
        if song_id in self._songs:
            self._send("local_remove_songs", {"ids": [song_id]})
            self._set_message("Removed from Local Music. The file wasn't changed.")

    @staticmethod
    def _playable(songs):
        return [song for song in songs if song.get("state") in {"ready", "unplayable"}]

    @Slot(int)
    def playSongs(self, index):
        """Play the Songs list as shown, from this row; songs whose files are unavailable are left out."""
        rows = self._rows() if self._filter == "Songs" else []
        if not 0 <= index < len(rows):
            return
        if rows[index].get("state") not in {"ready", "unplayable"}:
            self._set_message(STATE_LABELS.get(rows[index].get("state"), "This song is unavailable") + ". Rescan Local Music or reconnect its drive.")
            return
        tracks = self._playable(rows)
        self.tracksRequested.emit(tracks, tracks.index(rows[index]))

    def _collection_songs(self, key):
        kind, _, value = key.partition(":")
        if kind == "folder":
            songs = [song for song in self._songs.values() if str(song.get("folder")) == value]
            songs.sort(key=lambda song: folded(song.get("path")))
            return songs
        songs = [song for song in self._songs.values() if (album_key(song) if kind == "album" else artist_key(song)) == value
                 and (kind != "album" or song.get("albumName"))]
        songs.sort(key=lambda song: (folded(song.get("albumName")), song.get("disc", 0), song.get("track", 0), folded(song["title"])))
        return songs

    @Slot(str)
    def open(self, key):
        """Show a local album or artist as a collection page with Play and Shuffle."""
        songs = self._collection_songs(key)
        if not songs:
            return
        kind = key.partition(":")[0]
        artist = kind == "artist"
        first = songs[0]
        folder = next((folder for folder in self._folders if "folder:" + str(folder["id"]) == key), {})
        title = folder.get("name", "") if kind == "folder" else (first.get("albumArtist") or first.get("artist")) if artist else first["albumName"]
        albums = len({folded(song.get("albumName")) for song in songs if song.get("albumName")})
        subtitle = folder.get("path", "") if kind == "folder" else f"{albums} album{'s' if albums != 1 else ''} in Local Music" if artist else "In Local Music"
        body = {"kind": "album", "id": key, "local": True, "localKind": kind, "title": title,
                "thumbnail": next((song["thumbnail"] for song in songs if song.get("thumbnail")), ""),
                "artists": [{"name": first.get("albumArtist") or first.get("artist", ""), "local": True}] if kind == "album" else [],
                "subtitle": subtitle, "year": (first.get("year") or "") if kind == "album" else "", "trackCount": len(songs),
                "duration": sum(song.get("duration", 0) for song in songs), "items": songs, "cursor": None}
        self.collectionReady.emit(body)

    @Slot(str)
    def openAlbum(self, song_id):
        song = self._songs.get(song_id)
        if song and song.get("albumName"):
            self.open("album:" + album_key(song))

    @Slot(str)
    def openArtist(self, song_id):
        song = self._songs.get(song_id)
        if song and (song.get("albumArtist") or song.get("artist")):
            self.open("artist:" + artist_key(song))

    @Slot(str)
    def openArtistNamed(self, name):
        self.open("artist:" + folded(name))

    @Slot(str, bool)
    def play(self, key, shuffle):
        songs = self._playable(self._collection_songs(key))
        if not songs:
            self._set_message("None of these songs' files are available right now.")
            return
        if shuffle:
            self.shuffleRequested.emit(songs, "Local Music")
        else:
            self.tracksRequested.emit(songs, 0)

    @Slot(str, bool)
    def enqueue(self, key, next=False):
        songs = self._playable(self._collection_songs(key))
        if songs:
            self.queueRequested.emit(songs, next)

    def close(self):
        self._closed = True
        for timer in (self.watch_timer, self.settle_timer, self.query_timer):
            timer.stop()
        for worker in (self.control, self.scanner):
            if worker:
                worker.close()
