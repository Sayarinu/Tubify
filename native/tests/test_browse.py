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
