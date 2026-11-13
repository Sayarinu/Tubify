import time

from PySide6.QtCore import QCoreApplication, Signal

from tubify.local.local_view import LocalView
from test_playback import FakeWorker


class ProgressWorker(FakeWorker):
    progress = Signal(int, dict)


def song(index, **values):
    identifier = f"local:{index:020}"
    base = {"id": identifier, "localId": identifier, "videoId": identifier, "kind": "song", "local": True, "folder": 1,
            "path": f"/music/{index}.flac", "title": f"Song {index:05}", "artist": "Artist", "albumName": "Album",
            "album": {"id": "", "name": "Album"}, "albumArtist": "Artist", "track": index, "disc": 1, "year": 2020,
            "duration": 100., "codec": "FLAC", "sampleRate": 44100, "thumbnail": "", "tagsReadable": True,
            "state": "ready", "available": True, "added": float(index), "size": 1}
    return {**base, **values}


FOLDERS = [{"id": 1, "path": "/music", "name": "music", "state": "ready", "scanned": time.time(), "added": 1., "songs": 0, "missing": 0}]


def make(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    control, scanner = FakeWorker(), ProgressWorker()
    view = LocalView(tmp_path, control=control, scanner=scanner, settings_path=tmp_path / "settings.ini")
    QCoreApplication.processEvents()
    return view, control, scanner


def reply(view, worker, result, index=-1):
    identifier = len(worker.requests) + 1 + index if index < 0 else index
    worker.succeeded.emit(identifier, result)


class Counter:
    def __init__(self, model):
        self.resets = self.inserts = self.removes = self.changes = 0
        model.modelReset.connect(lambda: setattr(self, "resets", self.resets + 1))
        model.rowsInserted.connect(lambda *args: setattr(self, "inserts", self.inserts + 1))
        model.rowsRemoved.connect(lambda *args: setattr(self, "removes", self.removes + 1))
        model.dataChanged.connect(lambda *args: setattr(self, "changes", self.changes + 1))


def rows(model):
    return [model.data(model.index(row), model.ROW) for row in range(model.rowCount())]


def test_starts_without_an_account_and_scans_a_stale_library(tmp_path):
    view, control, scanner = make(tmp_path)
    assert control.requests == [("local_changes", {"data_dir": str(tmp_path), "since": 0})]
    stale = [{**FOLDERS[0], "scanned": 0}]
    reply(view, control, {"full": True, "revision": 3, "folders": stale, "songs": [song(1)], "removed": []})
    assert view.initialized and view.songCount == 1
    assert scanner.requests == [("local_scan", {"data_dir": str(tmp_path)})]
    view.close()


def test_large_library_updates_rows_in_place(tmp_path):
    view, control, scanner = make(tmp_path)
    library = [song(index) for index in range(20000)]
    reply(view, control, {"full": True, "revision": 1, "folders": FOLDERS, "songs": library, "removed": []})
    model = view.songsModel
    assert model.rowCount() == 20000
    counter = Counter(model)
    # A scan reports progress, and the view fetches only what changed.
    view.rescan(-1)
    scanner.progress.emit(len(scanner.requests), {"folder": 1, "phase": "reading", "scanned": 100, "total": 20000, "revision": 2})
    assert control.requests[-1] == ("local_changes", {"data_dir": str(tmp_path), "since": 1})
    started = time.monotonic()
    changed = [song(index, state="missing", available=False) for index in range(19990, 20000)]
    reply(view, control, {"full": False, "revision": 2, "folders": FOLDERS, "songs": changed, "removed": []})
    assert time.monotonic() - started < 2
    assert model.rowCount() == 20000 and counter.resets == 0 and counter.inserts == 0 and counter.removes == 0
    assert counter.changes >= 1
    assert rows(model)[0]["state"] == "missing"
    # Progress ticks don't refetch more than about once a second.
    requests = len(control.requests)
    scanner.progress.emit(len(scanner.requests), {"folder": 1, "phase": "reading", "scanned": 200, "total": 20000, "revision": 3})
    assert len(control.requests) == requests
    assert view.scanning and "200 of 20,000" in view.scanLabel
    # A new song arrives as one inserted row; removed songs leave as removed rows.
    reply(view, scanner, {"full": False, "revision": 4, "folders": FOLDERS, "songs": [song(20001)], "removed": [song(0)["id"]], "added": 1, "waiting": 1})
    assert counter.resets == 0 and model.rowCount() == 20000
    assert not view.scanning and view.message.startswith("Scan finished") and view.settle_timer.isActive()
    view.close()


def test_filters_groups_and_never_merges_unrelated_songs(tmp_path):
    view, control, scanner = make(tmp_path)
    library = [song(1, title="Home", artist="First", albumArtist="First", albumName="Shared title", album={"id": "", "name": "Shared title"}),
               song(2, title="Home", artist="Second", albumArtist="Second", albumName="Shared title", album={"id": "", "name": "Shared title"}, path="/music/other.flac"),
               song(3, title="Loose", artist="Second", albumArtist="", albumName="", album={"id": "", "name": ""}, thumbnail="file:///art.jpg")]
    reply(view, control, {"full": True, "revision": 1, "folders": FOLDERS, "songs": library, "removed": []})
    # Two files with the same title stay two songs.
    assert [row["artist"] for row in rows(view.songsModel)] == ["Second", "Second", "First"]
    view.setFilter("Albums")
    albums = rows(view.cardsModel)
    assert sorted(album["artist"] for album in albums) == ["First", "Second"] and all(album["songs"] == 1 for album in albums)
    view.setFilter("Artists")
    view.sort("Most songs")
    assert [(artist["title"], artist["songs"]) for artist in rows(view.cardsModel)] == [("Second", 2), ("First", 1)]
    view.setFilter("Songs")
    view.setQuery("first")
    view._show()
    assert [row["artist"] for row in rows(view.songsModel)] == ["First"]
    view.setQuery("")
    view.sort("A to Z")
    view._show()
    assert [row["title"] for row in rows(view.songsModel)] == ["Home", "Home", "Loose"]
    view.setFilter("Folders")
    assert rows(view.cardsModel)[0]["kind"] == "folder" and rows(view.cardsModel)[0]["thumbnail"] == "file:///art.jpg"
    view.close()


def test_playing_opening_and_queueing_use_only_available_files(tmp_path):
    view, control, scanner = make(tmp_path)
    library = [song(1, track=2), song(2, track=1), song(3, state="offline", available=False)]
    reply(view, control, {"full": True, "revision": 1, "folders": FOLDERS, "songs": library, "removed": []})
    played, opened, queued = [], [], []
    view.tracksRequested.connect(lambda tracks, start: played.append(([track["id"] for track in tracks], start)))
    view.collectionReady.connect(opened.append)
    view.queueRequested.connect(lambda tracks, next: queued.append((len(tracks), next)))
    # Newest first: song 3 (disconnected), then 2, then 1.
    view.playSongs(0)
    assert not played and "Drive not connected" in view.message
    view.playSongs(2)
    assert played == [([song(2)["id"], song(1)["id"]], 1)]
    view.openAlbum(song(1)["id"])
    body = opened[-1]
    assert body["local"] and body["localKind"] == "album" and body["title"] == "Album"
    assert [item["track"] for item in body["items"]] == [1, 2, 3]
    view.openArtistNamed("ARTIST")
    assert opened[-1]["localKind"] == "artist" and len(opened[-1]["items"]) == 3
    view.open("folder:1")
    assert opened[-1]["localKind"] == "folder" and opened[-1]["subtitle"] == "/music"
    view.enqueue(body["id"], True)
    assert queued == [(2, True)]
    view.close()


def test_folder_actions(tmp_path):
    chosen = str(tmp_path / "Music" / "Library")
    view, control, scanner = make(tmp_path)
    reply(view, control, {"full": True, "revision": 1, "folders": FOLDERS, "songs": [], "removed": []})
    view.addFolder(chosen)
    assert control.requests[-1] == ("local_add_folder", {"data_dir": str(tmp_path), "path": chosen})
    added = {**FOLDERS[0], "id": 2, "path": chosen, "name": "Library", "state": "new"}
    reply(view, control, {"folder": 2, "full": True, "revision": 2, "folders": FOLDERS + [added], "songs": [], "removed": []})
    assert scanner.requests[-1] == ("local_scan", {"data_dir": str(tmp_path), "id": 2})
    # A second scan request waits for the first.
    view.rescan(1)
    assert len(scanner.requests) == 1
    reply(view, scanner, {"full": False, "revision": 3, "folders": FOLDERS + [added], "songs": [], "removed": [], "watch": {"1": ["/music", "/music/Artist"]}})
    assert scanner.requests[-1] == ("local_scan", {"data_dir": str(tmp_path), "id": 1})
    removals = []
    view.folderRemovalRequested.connect(removals.append)
    view.requestFolderRemoval(2)
    assert removals[0]["path"] == chosen
    view.removeFolder(2)
    assert control.requests[-1] == ("local_remove_folder", {"data_dir": str(tmp_path), "id": 2})
    assert "weren't changed" in view.message
    view.close()


def test_watcher_rescans_only_the_changed_folder(tmp_path):
    (tmp_path / "A" / "Artist").mkdir(parents=True)
    (tmp_path / "B").mkdir()
    view, control, scanner = make(tmp_path)
    folders = [{**FOLDERS[0], "id": 1, "path": str(tmp_path / "A")}, {**FOLDERS[0], "id": 2, "path": str(tmp_path / "B")}]
    reply(view, control, {"full": True, "revision": 1, "folders": folders, "songs": [], "removed": [],
                          "watch": {"1": [str(tmp_path / "A"), str(tmp_path / "A" / "Artist")], "2": [str(tmp_path / "B")]}})
    assert sorted(view.watcher.directories()) == sorted([str(tmp_path / "A"), str(tmp_path / "A" / "Artist"), str(tmp_path / "B")])
    view._folder_changed(str(tmp_path / "A" / "Artist"))
    assert view.watch_timer.isActive()
    view._rescan_changed()
    assert scanner.requests[-1] == ("local_scan", {"data_dir": str(tmp_path), "id": 1})
    view.close()


def test_fixture_has_every_state(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    view = LocalView(tmp_path, fixture=True)
    states = {row["state"] for row in rows(view.songsModel)}
    assert states == {"ready", "missing", "offline"}
    assert view.stateLabel("missing") == "File missing" and view.stateLabel("ready") == ""
    view.close()
