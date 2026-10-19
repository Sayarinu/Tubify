from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication, QObject, Signal

from youtube_music_native.actions import Actions
from youtube_music_native.browse import Browse
from youtube_music_native.catalog_view import CatalogView
from youtube_music_native.library import Library
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
    connected, busy = True, False
    profile = {"name": "Fixture"}


def setup(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    shell, worker, account = ShellController(tmp_path / "settings.ini"), Worker(), Account()
    account.worker = worker
    account.requireReconnect = lambda message: None
    view = CatalogView(worker, tmp_path / "cache.sqlite3", account)
    updated = []
    player = SimpleNamespace(resetSession=lambda: None, updateTrack=lambda *args: updated.append(args), hasTrack=False)
    browse = Browse(shell, account, view, player, tmp_path / "cache.sqlite3")
    actions = Actions(account, tmp_path / "cache.sqlite3")
    actions.applied.connect(browse.applyAction)
    library = Library(shell, account, view, player, browse, actions, tmp_path / "cache.sqlite3")
    return app, shell, worker, view, actions, library, updated


def test_move_across_page_boundary_uses_the_actual_next_occurrence(tmp_path):
    app, shell, worker, view, actions, library, updated = setup(tmp_path)
    tracks = [{"videoId": "abcdefghijk", "setVideoId": f"occurrence-{i}"} for i in range(80)]
    view.showLocal("playlist", {"items": tracks[:40], "editable": True, "cursor": 40}, {"id": "PLfixture"})
    library.moveEntry(tracks[38], 1)
    assert worker.requests[-1][1]["offset"] == 40
    assert not actions.busy
    worker.succeeded.emit(1, {"items": tracks[40:], "cursor": None})
    operation, payload = worker.requests[-1]
    assert operation == "account_action" and payload["action"] == "playlist_move"
    assert payload["setVideoId"] == "occurrence-38" and payload["successor"] == "occurrence-40"


def test_account_error_does_not_change_metadata_and_retry_updates_matching_duplicates(tmp_path):
    app, shell, worker, view, actions, library, updated = setup(tmp_path)
    tracks = [{"kind": "song", "videoId": "abcdefghijk", "setVideoId": str(i), "rating": "INDIFFERENT"} for i in range(2)]
    view.showLocal("playlist", {"items": tracks, "editable": True, "cursor": None}, {"id": "PLfixture"})
    library.rate(tracks[0], "LIKE")
    worker.failed.emit(1, {"code": "offline", "message": "Connect to update your music."})
    assert not actions.busy and all(track["rating"] == "INDIFFERENT" for track in tracks)
    library.rate(tracks[1], "DISLIKE")
    worker.succeeded.emit(2, {"action": "song_rating", "id": "abcdefghijk", "value": "DISLIKE"})
    assert all(track["rating"] == "DISLIKE" for track in view.data["items"])
    assert updated == [("abcdefghijk", {"rating": "DISLIKE"})]


def test_refresh_retains_loaded_range_and_scroll_and_new_navigation_cancels_pending_move(tmp_path):
    app, shell, worker, view, actions, library, updated = setup(tmp_path)
    values = [{"videoId": "abcdefghijk", "setVideoId": str(i)} for i in range(80)]
    view.showLocal("playlist", {"items": values, "cursor": 80}, {"id": "PLfixture"})
    view.saveScroll(2500)
    view.refresh()
    assert worker.requests[-1][1]["page_size"] == 80 and view.scrollPosition == 2500
    worker.succeeded.emit(1, {"items": values[:40], "cursor": 40})
    library.moveEntry(values[39], 1)
    library.select("Songs")
    worker.succeeded.emit(2, {"items": values[40:], "cursor": None})
    worker.succeeded.emit(3, {"items": [], "cursor": None})
    assert view.route == "library_songs" and not actions.busy
    assert all(operation != "account_action" for operation, _ in worker.requests)
