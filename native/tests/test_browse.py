from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication, QObject, Signal

from tubify.catalog.browse import Browse
from tubify.catalog.catalog_view import CatalogView
from tubify.shell import ShellController


class Worker(QObject):
    succeeded = Signal(int, dict)
    failed = Signal(int, dict)

    def __init__(self):
        super().__init__()
        self.requests = []
        self.cancelled = []

    def request(self, operation, payload):
        self.requests.append((operation, payload))
        return len(self.requests)

    def cancelQueued(self, identifier):
        pass

    def cancel(self, identifier):
        self.cancelled.append(identifier)


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
    player = SimpleNamespace(play=played.append, playTracks=lambda values, index=0, source_label="": played.append(values), enqueue=lambda tracks, next=False: queued.append(tracks), appendContext=queued.append, resetSession=lambda: resets.append(True), manualQueueCleared=account.sessionChanged)
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


def test_collection_title_is_used_once_and_pagination_does_not_replace_it(tmp_path):
    app, browse, worker, account, view, played, queued, resets = setup(tmp_path)
    titles = []
    browse.player.playTracks = lambda values, index=0, source_label="": titles.append(source_label)
    browse.playCollection({"kind": "playlist", "id": "PLfixture", "title": "Selected collection"}, False)
    worker.succeeded.emit(1, {"title": "Resolved collection", "items": [{"kind": "song"}], "cursor": 1})
    worker.succeeded.emit(2, {"title": "Later page", "items": [{"kind": "song"}]})
    assert titles == ["Resolved collection"] and len(queued) == 1


def test_source_selection_does_not_cancel_unfinished_manual_collection(tmp_path):
    app, browse, worker, account, view, played, queued, resets = setup(tmp_path)
    browse.enqueue({"kind": "playlist", "id": "PLqueued"}, False)
    browse.play({"kind": "song", "videoId": "newsource01", "title": "New source"})
    worker.succeeded.emit(1, {"items": [{"kind": "song", "videoId": "manualsong1"}]})
    assert played[0]["title"] == "New source" and queued[0][0]["videoId"] == "manualsong1"


def test_failed_sidebar_playlists_retry_and_reload_on_reconnect(tmp_path):
    app, browse, worker, account, view, played, queued, resets = setup(tmp_path)
    account.connectedChanged.emit()
    playlist_request = next(index + 1 for index, (_, payload) in enumerate(worker.requests) if payload.get("route") == "library_playlists")
    worker.failed.emit(playlist_request, {"code": "timeout", "message": "timed out"})
    assert browse.playlist_retry.isActive() and not browse.shell.playlists
    browse.playlist_retry.timeout.emit()
    assert worker.requests[-1][1]["route"] == "library_playlists"
    worker.failed.emit(len(worker.requests), {"code": "provider_error", "message": "stopped"})
    # A renewal with the same identity must still load playlists that never arrived.
    account.connectedChanged.emit()
    assert worker.requests[-1][1]["route"] == "library_playlists"
    worker.succeeded.emit(len(worker.requests), {"items": [{"id": "PLfixture", "title": "Playlist"}]})
    assert browse.shell.playlists[0]["title"] == "Playlist" and not browse.playlist_retry.isActive()
    requests = len(worker.requests)
    account.connectedChanged.emit()
    assert len(worker.requests) == requests


def test_sidebar_snapshot_renders_before_the_account_restores(tmp_path):
    app, browse, worker, account, view, played, queued, resets = setup(tmp_path)
    account.connectedChanged.emit()
    playlist_request = next(index + 1 for index, (_, payload) in enumerate(worker.requests) if payload.get("route") == "library_playlists")
    worker.succeeded.emit(playlist_request, {"items": [{"id": "PLfixture", "title": "Saved"}]})
    app2, restarted, *_ = setup(tmp_path)
    assert restarted.shell.playlists[0]["title"] == "Saved"


def test_sorting_loads_every_page_plays_in_order_and_is_remembered(tmp_path):
    from tubify.catalog.catalog_view import CatalogView

    from PySide6.QtCore import QSettings

    app, browse, worker, account, view, played, queued, resets = setup(tmp_path)
    account.settings = view._settings = QSettings(str(tmp_path / "account.ini"), QSettings.Format.IniFormat)
    view.load("playlist", {"id": "PLsort"})
    first = [{"kind": "song", "title": "b", "artist": "Zed", "duration": 30, "videoId": "aaaaaaaaaaa"},
             {"kind": "song", "title": "C", "artist": "", "duration": 10, "videoId": "bbbbbbbbbbb"}]
    worker.succeeded.emit(len(worker.requests), {"title": "Mix", "items": first, "cursor": 2})
    view.sortBy("title")
    # The rest of the playlist is fetched before sorting so the order is complete.
    assert worker.requests[-1][1]["offset"] == 2 and worker.requests[-1][1]["page_size"] == 100000
    worker.succeeded.emit(len(worker.requests), {"items": [{"kind": "song", "title": "a", "artist": "Abe", "duration": 20, "videoId": "ccccccccccc"}], "cursor": None})
    assert [item["title"] for item in view.data["items"]] == ["a", "b", "C"] and view.sortKey == "title"
    view.sortBy("title")
    assert [item["title"] for item in view.data["items"]] == ["C", "b", "a"] and view.sortDescending
    view.setSort("artist", False)
    assert [item["title"] for item in view.data["items"]] == ["a", "b", "C"]
    view.setSort("duration", False)
    assert [item["duration"] for item in view.data["items"]] == [10, 20, 30]
    browse.playView()
    assert [track["title"] for track in played[-1]] == ["C", "a", "b"]
    restored = CatalogView(worker, tmp_path / "metadata.sqlite3", account)
    restored.showLocal("playlist", {"items": [dict(item) for item in first]}, {"id": "PLsort"})
    assert restored.sortKey == "duration" and restored.data["items"][0]["title"] == "C"
    view.sortBy("")
    assert [item["position"] for item in view.data["items"]] == [0, 1, 2]


def test_library_title_order_is_applied_client_side_for_liked_songs(tmp_path):
    app, browse, worker, account, view, played, queued, resets = setup(tmp_path)
    view.load("library_liked", {"order": "z_to_a"})
    worker.succeeded.emit(len(worker.requests), {"items": [{"title": "a"}, {"title": "c"}, {"title": "b"}], "cursor": None})
    assert [item["title"] for item in view.data["items"]] == ["c", "b", "a"]


def test_collections_sort_by_number_both_ways_and_remember_it(tmp_path):
    from PySide6.QtCore import QSettings

    app, browse, worker, account, view, played, queued, resets = setup(tmp_path)
    account.settings = view._settings = QSettings(str(tmp_path / "account.ini"), QSettings.Format.IniFormat)
    browse.open({"kind": "playlist", "id": "PLnumbers"})
    worker.succeeded.emit(len(worker.requests), {"title": "Numbers", "items": [{"title": "a"}, {"title": "b"}, {"title": "c"}], "cursor": 3})
    positions = lambda: [item["position"] for item in view.data["items"]]
    assert view.sortKey == "number" and not view.sortDescending and not view.reordered
    requests = len(worker.requests)
    # Ascending is the collection's own order, so it keeps paging as you scroll.
    view.setSort("number", False)
    assert positions() == [0, 1, 2] and len(worker.requests) == requests and not view.reordered
    # Descending needs the last song first, so it fetches the rest before sorting.
    view.sortBy("number")
    assert view.sortDescending and view.reordered and worker.requests[-1][1]["page_size"] == 100000
    worker.succeeded.emit(len(worker.requests), {"items": [{"title": "d"}], "cursor": None})
    assert positions() == [3, 2, 1, 0]
    restored = type(view)(worker, tmp_path / "other.sqlite", account)
    restored.showLocal("playlist", {"items": [{"title": "a"}, {"title": "b"}]}, {"id": "PLnumbers"})
    assert restored.sortKey == "number" and restored.sortDescending
    assert [item["title"] for item in restored.data["items"]] == ["b", "a"]
    # Moves stay disabled, and the view plays as shown, until it is back in its own order.
    view.sortBy("number")
    assert positions() == [0, 1, 2, 3] and view.sortKey == "number" and not view.sortDescending and not view.reordered
    view.setSort("title", True)
    assert view.reordered
    view.setSort("number", False)
    assert positions() == [0, 1, 2, 3] and view._scope() not in view._sorts


def test_selecting_the_tab_already_shown_is_a_no_op_only_at_its_root(tmp_path):
    app, browse, worker, account, view, played, queued, resets = setup(tmp_path)
    browse.shell.navigate("Explore")
    assert browse.atTabRoot("Explore")  # Selecting it again while it loads does not restart the load.
    explore = len(worker.requests)
    worker.succeeded.emit(explore, {"title": "Explore", "shelves": [{"title": "New albums", "items": []}]})
    assert view.route == "explore" and browse.atTabRoot("Explore")
    assert not browse.atTabRoot("Home")  # A different tab always navigates.
    browse.showShelf({"title": "Charts", "items": []})
    assert not browse.atTabRoot("Explore")  # A view opened from the tab goes back to the tab.
    browse.shell.navigate("Downloads")
    assert browse.atTabRoot("Downloads")
    browse.shell.navigate("Home")
    worker.failed.emit(len(worker.requests), {"message": "offline"})
    assert view.error and not browse.atTabRoot("Home")  # An error can be retried by selecting the tab.


def test_selecting_home_or_explore_shows_fresh_data_and_startup_does_not(tmp_path):
    app, browse, worker, account, view, played, queued, resets = setup(tmp_path)
    shelves = [{"title": "One", "items": []}]
    # Reaching a page some other way, such as at startup, may use saved data.
    browse.shell.navigate("Home")
    assert worker.requests[-1][1]["route"] == "home" and not worker.requests[-1][1]["refresh"]
    worker.succeeded.emit(len(worker.requests), {"title": "Home", "items": [], "shelves": shelves, "cursor": 6})
    # Selecting another tab has nothing saved to show, so it loads fresh while busy.
    browse.selectTab("Explore")
    assert browse.shell.page == "Explore" and worker.requests[-1][1]["route"] == "explore" and worker.requests[-1][1]["refresh"]
    assert view.busy and not view.data
    worker.succeeded.emit(len(worker.requests), {"title": "Explore", "items": [{"title": "a"}], "shelves": [], "cursor": None})
    # Back on Home, what was there shows at once and refreshes behind it.
    browse.selectTab("Home")
    assert view.route == "home" and view.data["shelves"] == shelves and not view.busy and view.revalidating
    assert worker.requests[-1][1]["route"] == "home" and worker.requests[-1][1]["refresh"]
    assert worker.requests[-1][1]["page_size"] == 1
    fresh = [{"title": "Fresh", "items": []}]
    worker.succeeded.emit(len(worker.requests), {"title": "Home", "items": [], "shelves": fresh, "cursor": None})
    assert view.data["shelves"] == fresh and not view.revalidating
    # Saved rows do not count as fresh for a later ordinary visit.
    browse.shell.navigate("Explore")
    assert not view.busy and worker.requests[-1][1]["route"] == "home"


def test_selecting_the_current_landing_tab_goes_to_the_top_and_refreshes(tmp_path):
    app, browse, worker, account, view, played, queued, resets = setup(tmp_path)
    tops = []
    view.scrollToTopRequested.connect(lambda: tops.append(True))
    browse.shell.navigate("Home")
    worker_requests = len(worker.requests)
    # Selecting it while it first loads asks for nothing more.
    browse.selectTab("Home")
    assert len(worker.requests) == worker_requests
    tops.clear()
    worker.succeeded.emit(len(worker.requests), {"title": "Home", "items": [], "shelves": [{"title": "One", "items": []}], "cursor": 6})
    view.saveScroll(500.)
    revision = view.revision
    browse.selectTab("Home")
    assert tops == [True] and view.scrollPosition == 0. and not view.hasScrollPosition
    # The page stays on screen, at its first results, keeping the same revision and so its place.
    request = worker.requests[-1][1]
    assert request["refresh"] and request["offset"] == 0 and request["page_size"] is None
    assert view.revalidating and not view.busy and view.data["shelves"] and view.revision == revision
    # Selecting it again during that refresh returns to the top without a second request.
    requests = len(worker.requests)
    browse.selectTab("Home")
    assert len(tops) == 2 and len(worker.requests) == requests
    worker.succeeded.emit(requests, {"title": "Home", "items": [], "shelves": [{"title": "Fresh", "items": []}], "cursor": 6})
    assert view.data["shelves"][0]["title"] == "Fresh" and not view.revalidating
    # A failed refresh keeps what is on screen.
    browse.selectTab("Home")
    worker.failed.emit(len(worker.requests), {"message": "offline"})
    assert view.data["shelves"][0]["title"] == "Fresh" and not view.error and not view.revalidating
    # An error page has nothing to refresh behind, so selecting the tab reloads it.
    browse.shell.navigate("Explore")
    worker.failed.emit(len(worker.requests), {"message": "offline"})
    assert view.error
    requests = len(worker.requests)
    browse.selectTab("Explore")
    assert len(worker.requests) == requests + 1 and worker.requests[-1][1]["refresh"] and view.busy


def test_selecting_library_or_downloads_keeps_their_own_updates(tmp_path):
    app, browse, worker, account, view, played, queued, resets = setup(tmp_path)
    browse.selectTab("Downloads")
    assert browse.shell.page == "Downloads" and view.route == "downloads"
    requests = len(worker.requests)
    tops = []
    view.scrollToTopRequested.connect(lambda: tops.append(True))
    browse.selectTab("Downloads")
    browse.selectTab("Library")
    assert browse.shell.page == "Library" and not tops
    assert all(not payload.get("refresh") for _, payload in worker.requests[requests:])


def test_artist_top_songs_show_all_opens_the_songs_playlist_and_albums_keep_their_route(tmp_path):
    app, browse, worker, account, view, played, queued, resets = setup(tmp_path)
    browse.openSection({"title": "Top songs", "layout": "rows", "browseId": "VLOLAKsongs", "params": "", "items": []})
    assert worker.requests[-1][1]["route"] == "playlist" and worker.requests[-1][1]["params"]["id"] == "OLAKsongs"
    browse.openSection({"title": "Albums", "browseId": "UCartist", "params": "albums", "items": []})
    assert worker.requests[-1][1]["route"] == "artist_albums" and worker.requests[-1][1]["params"]["params"] == "albums"


class PagesWorker(Worker):
    def __init__(self):
        super().__init__()
        self.resets = 0

    def reset(self):
        self.resets += 1


class Downloads(QObject):
    collectionFound = Signal(int, dict)
    collectionReady = Signal(dict)
    playRequested = Signal(dict, bool)

    def __init__(self, keys):
        super().__init__()
        self.keys, self.lookups = keys, []

    def known(self, kind, identifier):
        return None if self.keys is None else kind + ":" + identifier in self.keys

    def lookup(self, kind, identifier):
        self.lookups.append((kind, identifier))
        return len(self.lookups)

    def cancelLookup(self, request):
        pass


def test_rest_of_playlist_loads_once_on_its_own_lane_and_new_click_stops_it(tmp_path):
    app, browse, worker, account, view, played, queued, resets = setup(tmp_path)
    pages = PagesWorker()
    browse = Browse(browse.shell, account, view, browse.player, tmp_path / "metadata.sqlite3", pages=pages)
    browse.play({"kind": "playlist", "id": "PLlong"})
    first = len(worker.requests)
    assert worker.requests[-1][1]["offset"] == 0
    worker.succeeded.emit(first, {"items": [{"kind": "song", "title": "First"}], "cursor": 40})
    # One request for everything after the first page, not one per 40 tracks.
    assert pages.requests == [("catalog", {**pages.requests[0][1], "offset": 40, "page_size": 100000})]
    # A provider-worker answer that reuses the same number is not the rest of the playlist.
    worker.succeeded.emit(1, {"items": [{"kind": "song", "title": "Wrong lane"}]})
    assert not queued
    browse.play({"kind": "playlist", "id": "PLother"})
    assert pages.resets == 1
    pages.succeeded.emit(1, {"items": [{"kind": "song", "title": "Old tail"}], "cursor": None})
    assert not queued


def test_rest_of_playlist_appends_after_the_first_page(tmp_path):
    app, browse, worker, account, view, played, queued, resets = setup(tmp_path)
    pages = PagesWorker()
    browse = Browse(browse.shell, account, view, browse.player, tmp_path / "metadata.sqlite3", pages=pages)
    browse.play({"kind": "playlist", "id": "PLlong"})
    worker.succeeded.emit(len(worker.requests), {"items": [{"kind": "song", "title": "First"}], "cursor": 40})
    pages.succeeded.emit(1, {"items": [{"kind": "song", "title": "Rest"}, {"kind": "video", "title": "Skip"}], "cursor": None})
    assert [track["title"] for track in queued[0]] == ["Rest"] and pages.resets == 0


def test_play_skips_the_downloads_lookup_for_collections_never_downloaded(tmp_path):
    app, browse, worker, account, view, played, queued, resets = setup(tmp_path)
    for keys, looked_up in ((set(), False), ({"playlist:PLsaved"}, True), (None, True)):
        downloads = Downloads(keys)
        browse = Browse(browse.shell, account, view, browse.player, tmp_path / "metadata.sqlite3", downloads=downloads)
        before = len(worker.requests)
        browse.play({"kind": "playlist", "id": "PLsaved"})
        assert bool(downloads.lookups) is looked_up
        assert (len(worker.requests) > before) is not looked_up


def test_sidebar_playlists_from_a_lapsed_session_renew_it_and_reload_instead_of_emptying(tmp_path):
    app, browse, worker, account, view, played, queued, resets = setup(tmp_path)
    account.connectedChanged.emit()
    first = next(index + 1 for index, (_, payload) in enumerate(worker.requests) if payload.get("route") == "library_playlists")
    worker.succeeded.emit(first, {"items": [{"id": "PLfixture", "title": "Saved"}]})
    browse.refreshPlaylists()
    # A signed-out reply falls back to the cache and says so; the sidebar keeps its playlists.
    worker.succeeded.emit(len(worker.requests), {"items": [], "warning": "reconnect"})
    assert browse.shell.playlists[0]["title"] == "Saved" and not account.connected
    # The renewed session, still the same account, reloads them.
    account.connected = True
    account.connectedChanged.emit()
    assert worker.requests[-1][1]["route"] == "library_playlists"


def test_sidebar_playlists_that_fail_on_a_lapsed_session_renew_it_instead_of_retrying(tmp_path):
    app, browse, worker, account, view, played, queued, resets = setup(tmp_path)
    account.connectedChanged.emit()
    request = next(index + 1 for index, (_, payload) in enumerate(worker.requests) if payload.get("route") == "library_playlists")
    worker.failed.emit(request, {"code": "AuthError", "message": "Your session needs reconnecting."})
    assert not account.connected and not browse.playlist_retry.isActive()
    account.connected = True
    account.connectedChanged.emit()
    assert worker.requests[-1][1]["route"] == "library_playlists"
