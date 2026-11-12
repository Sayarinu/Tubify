from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication, QObject, Signal

from tubify.catalog.actions import Actions
from tubify.catalog.browse import Browse
from tubify.catalog.catalog_view import CatalogView
from tubify.catalog.library import Library
from tubify.shell import ShellController


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
    player = SimpleNamespace(resetSession=lambda: None, updateTrack=lambda *args: updated.append(args), hasTrack=False, manualQueueCleared=account.sessionChanged)
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


def test_successful_mutation_marks_remembered_sections_dirty(tmp_path):
    app, shell, worker, view, actions, library, updated = setup(tmp_path)
    library.select("Songs")
    worker.succeeded.emit(len(worker.requests), {"items": [{"videoId": "abcdefghijk", "rating": "INDIFFERENT"}], "cursor": None})
    library.select("Albums")
    worker.succeeded.emit(len(worker.requests), {"items": [], "cursor": None})
    library.rate({"videoId": "abcdefghijk", "rating": "INDIFFERENT"}, "LIKE")
    worker.succeeded.emit(len(worker.requests), {"action": "song_rating", "id": "abcdefghijk", "value": "LIKE"})
    before = len(worker.requests)
    library.select("Songs")
    assert len(worker.requests) == before + 1 and view.revalidating
    operation, payload = worker.requests[-1]
    assert operation == "catalog" and payload["route"] == "library_songs" and payload["refresh"]
    assert view.data["items"][0]["videoId"] == "abcdefghijk"


def test_song_sections_offer_number_orders_and_other_sections_do_not(tmp_path):
    app, shell, worker, view, actions, library, updated = setup(tmp_path)
    assert "Number descending" not in library.orders  # Playlists is selected first.
    library.select("Liked songs")
    assert library.orders[-2:] == ["Number ascending", "Number descending"]
    library.sort("Number descending")
    assert worker.requests[-1][1]["params"]["order"] == "number_descending"
    assert worker.requests[-1][1]["offset"] == 0
    worker.succeeded.emit(len(worker.requests), {"items": [{"title": "a"}, {"title": "b"}], "cursor": 2})
    # The last song comes first, so every page loads before sorting.
    assert worker.requests[-1][1]["offset"] == 2 and worker.requests[-1][1]["page_size"] == 100000
    worker.succeeded.emit(len(worker.requests), {"items": [{"title": "c"}], "cursor": None})
    assert [item["title"] for item in view.data["items"]] == ["c", "b", "a"]
    assert [item["position"] for item in view.data["items"]] == [2, 1, 0]
    assert library.selectedOrder == "Number descending"
    library.select("Songs")
    assert library.selectedOrder == "Number descending" and view.sortDescending and view.sortKey == "number"
    worker.succeeded.emit(len(worker.requests), {"items": [{"title": "a"}, {"title": "b"}], "cursor": None})
    assert [item["position"] for item in view.data["items"]] == [1, 0]
    library.sort("Number ascending")
    requests = len(worker.requests)
    worker.succeeded.emit(requests, {"items": [{"title": "a"}, {"title": "b"}], "cursor": 2})
    assert len(worker.requests) == requests and [item["position"] for item in view.data["items"]] == [0, 1]
    # Sections without numbers fall back rather than keep an order they cannot show.
    library.select("Albums")
    assert library.selectedOrder == "Recently added" and "Number ascending" not in library.orders
    assert worker.requests[-1][1]["params"]["order"] == "recently_added"


def test_playlist_edits_keep_row_numbers_in_order():
    from tubify.catalog.playlist_ops import apply_change

    def tracks(*numbers):
        return [{"setVideoId": str(number), "position": number} for number in numbers]

    def positions(data):
        return [(track["setVideoId"], track["position"]) for track in data["items"]]

    data = {"items": tracks(0, 1, 2, 3)}
    apply_change(data, {"action": "playlist_move", "id": "PL", "setVideoId": "3", "successor": "1"}, "PL")
    assert positions(data) == [("0", 0), ("3", 1), ("1", 2), ("2", 3)]
    data = {"items": tracks(0, 1, 2, 3)}
    apply_change(data, {"action": "playlist_remove", "id": "PL", "setVideoId": "1"}, "PL")
    assert positions(data) == [("0", 0), ("2", 1), ("3", 2)]
    # Removing while sorted descending keeps the rows shown and numbers from the playlist's own order.
    data = {"items": tracks(3, 2, 1, 0)}
    apply_change(data, {"action": "playlist_remove", "id": "PL", "setVideoId": "1"}, "PL")
    assert positions(data) == [("3", 2), ("2", 1), ("0", 0)]
    data = {"items": tracks(0, 1), "cursor": None}
    apply_change(data, {"action": "playlist_add", "id": "PL", "addedEntries": [{"setVideoId": "new", "videoId": "abcdefghijk"}]}, "PL", {"title": "New"})
    assert positions(data) == [("0", 0), ("1", 1), ("new", 2)]
    # Cached pages have no numbers yet; the view adds them when it shows the page.
    data = {"items": [{"setVideoId": "0"}, {"setVideoId": "1"}]}
    apply_change(data, {"action": "playlist_remove", "id": "PL", "setVideoId": "0"}, "PL")
    assert data["items"] == [{"setVideoId": "1"}]

