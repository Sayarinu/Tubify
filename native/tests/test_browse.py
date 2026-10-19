from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication, QObject, Signal

from youtube_music_native.browse import Browse
from youtube_music_native.catalog_view import CatalogView
from youtube_music_native.shell import ShellController


class Worker(QObject):
    succeeded = Signal(int, dict)
    failed = Signal(int, dict)

    def __init__(self):
        super().__init__()
        self.requests = []

    def request(self, operation, payload):
        self.requests.append((operation, payload))
        return len(self.requests)

    def cancelQueued(self, identifier):
        pass


class Account(QObject):
    connectedChanged = Signal()
    sessionChanged = Signal()

    def __init__(self, worker):
        super().__init__()
        self.worker = worker
        self.profile = {"name": "Fixture"}
        self.connected = True

    def requireReconnect(self, message):
        self.connected = False
        self.connectedChanged.emit()


def setup(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    shell, worker = ShellController(tmp_path / "settings.ini"), Worker()
    account = Account(worker)
    view = CatalogView(worker, tmp_path / "metadata.sqlite3", account)
    played, queued, resets = [], [], []
    player = SimpleNamespace(play=played.append, playTracks=lambda values, index=0: played.append(values), enqueue=queued.append, resetSession=lambda: resets.append(True))
    browse = Browse(shell, account, view, player, tmp_path / "metadata.sqlite3")
    return app, browse, worker, account, view, played, queued, resets


def test_home_sidebar_and_sign_out_clear_account_views(tmp_path):
    app, browse, worker, account, view, played, queued, resets = setup(tmp_path)
    account.connectedChanged.emit()
    worker.succeeded.emit(1, {"title": "Home", "shelves": [{"title": "Listen again", "items": []}]})
    worker.succeeded.emit(2, {"items": [{"id": "PLfixture", "title": "Playlist"}]})
    assert browse.shell.playlists[0]["title"] == "Playlist"
    account.connected, account.profile = False, {}
    account.connectedChanged.emit()
    account.sessionChanged.emit()
    assert resets and not browse.shell.playlists and not view.data["shelves"]


def test_new_manual_song_invalidates_pending_collection_playback(tmp_path):
    app, browse, worker, account, view, played, queued, resets = setup(tmp_path)
    browse.play({"kind": "playlist", "id": "PLfixture"})
    browse.play({"kind": "song", "title": "New selection", "videoId": "abcdefghijk"})
    worker.succeeded.emit(1, {"items": [{"kind": "song", "title": "Old selection"}]})
    assert len(played) == 1 and played[0]["title"] == "New selection"
    assert not queued


def test_collection_begins_with_first_page_and_appends_subsequent_pages(tmp_path):
    app, browse, worker, account, view, played, queued, resets = setup(tmp_path)
    browse.play({"kind": "playlist", "id": "PLfixture"})
    worker.succeeded.emit(1, {"items": [{"kind": "song", "title": "First"}], "cursor": 40})
    assert played[0][0]["title"] == "First"
    worker.succeeded.emit(2, {"items": [{"kind": "song", "title": "Next"}], "cursor": None})
    assert queued[0][0]["title"] == "Next"


def test_old_mood_result_cannot_replace_new_navigation(tmp_path):
    app, browse, worker, account, view, played, queued, resets = setup(tmp_path)
    browse.homeMood("Relax")
    browse.navigate("Explore")
    worker.succeeded.emit(1, {"groups": {"Moods": [{"title": "Relax", "params": "fixture"}]}})
    worker.succeeded.emit(2, {"title": "Explore", "shelves": []})
    assert view.route == "explore" and view.data["title"] == "Explore"


def test_back_restores_results_query_filter_and_scroll_without_provider_request(tmp_path):
    app, browse, worker, account, view, played, queued, resets = setup(tmp_path)
    browse.shell.restoreNavigation("Search", "fixture query")
    view.showLocal("search", {"title": "Fixture", "items": [{"kind": "album", "id": "MPREfixture"}]}, {"query": "fixture query", "filter": "albums"})
    view.saveScroll(240)
    browse.open({"kind": "album", "id": "MPREfixture"})
    worker.succeeded.emit(1, {"title": "Album", "items": []})
    browse.back()
    assert view.route == "search" and view.parameters["filter"] == "albums"
    assert view.scrollPosition == 240 and browse.shell.query == "fixture query"
    assert len(worker.requests) == 1


def test_confirmed_playlist_edits_update_occurrences_without_waiting_for_stale_readback(tmp_path):
    app, browse, worker, account, view, played, queued, resets = setup(tmp_path)
    tracks = [{"videoId": "abcdefghijk", "setVideoId": key, "duration": 60} for key in ("one", "two", "three")]
    view.showLocal("playlist", {"title": "Original", "items": tracks, "trackCount": 3, "duration": 180, "cursor": None}, {"id": "PLfixture"})
    browse.updatePlaylist({"action": "playlist_move", "id": "PLfixture", "movedSetVideoId": "two", "successor": "one"})
    assert [track["setVideoId"] for track in view.data["items"]] == ["two", "one", "three"]
    browse.updatePlaylist({"action": "playlist_remove", "id": "PLfixture", "removedSetVideoId": "one"})
    assert [track["setVideoId"] for track in view.data["items"]] == ["two", "three"]
    assert view.data["duration"] == 120 and view.data["trackCount"] == 2
    assert not worker.requests


def test_removing_loaded_entry_adjusts_the_next_page_offset(tmp_path):
    app, browse, worker, account, view, played, queued, resets = setup(tmp_path)
    tracks = [{"kind": "song", "videoId": "abcdefghijk", "setVideoId": str(index)} for index in range(40)]
    view.showLocal("playlist", {"items": tracks, "cursor": 40, "trackCount": 80}, {"id": "PLfixture"})
    browse.updatePlaylist({"action": "playlist_remove", "id": "PLfixture", "removedSetVideoId": "10"})
    assert len(view.data["items"]) == 39 and view.data["cursor"] == 39
    view.more()
    assert worker.requests[-1][1]["offset"] == 39
