from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication, QObject, Signal

from youtube_music_native.catalog_view import CatalogView


class FakeWorker(QObject):
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


def test_stale_search_responses_and_failures_cannot_replace_current_page(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    reconnects = []
    view = CatalogView(worker, tmp_path / "cache.sqlite3", SimpleNamespace(requireReconnect=reconnects.append))
    view.load("search", {"query": "first"})
    view.load("search", {"query": "second"})
    worker.succeeded.emit(1, {"title": "First", "items": []})
    assert view.busy and not view.data
    worker.failed.emit(1, {"code": "reconnect", "message": "Old failure"})
    assert not reconnects and not view.error
    worker.succeeded.emit(2, {"title": "Second", "items": [{"id": "one"}], "cursor": 40})
    view.more()
    worker.succeeded.emit(3, {"title": "Second", "items": [{"id": "two"}], "cursor": None})
    assert [i["id"] for i in view.data["items"]] == ["one", "two"]
    view.refresh()
    worker.failed.emit(4, {"code": "reconnect", "message": "Reconnect"})
    assert reconnects == ["Reconnect"] and view.error == "Reconnect" and not view.busy


def memory_view(tmp_path, profile=None):
    QCoreApplication.instance() or QCoreApplication([])
    worker = FakeWorker()
    account = SimpleNamespace(requireReconnect=lambda message: None, profile=profile or {"name": "One", "handle": "@one"})
    return worker, account, CatalogView(worker, tmp_path / "cache.sqlite3", account)


def songs(*identifiers):
    return [{"videoId": identifier, "title": identifier} for identifier in identifiers]


def test_fresh_library_memory_hit_renders_without_a_request(tmp_path):
    worker, account, view = memory_view(tmp_path)
    view.load("library_songs", {"order": "recently_added"})
    worker.succeeded.emit(1, {"title": "Songs", "items": songs("a", "b"), "cursor": None})
    view.load("library_albums", {"order": "recently_added"})
    revision = view.revision
    view.load("library_songs", {"order": "recently_added"})
    assert len(worker.requests) == 2
    assert not view.busy and not view.revalidating and view.revision == revision + 1
    assert [item["videoId"] for item in view.data["items"]] == ["a", "b"]
    assert [item["position"] for item in view.data["items"]] == [0, 1]


def test_dirty_or_expired_entries_render_and_revalidate_once_in_the_background(tmp_path, monkeypatch):
    from youtube_music_native import catalog_view

    worker, account, view = memory_view(tmp_path)
    view.load("library_songs", {})
    worker.succeeded.emit(1, {"items": songs("a", "b"), "cursor": None})
    view.invalidate(["library_songs"])
    view.load("library_songs", {})
    assert len(worker.requests) == 2
    payload = worker.requests[-1][1]
    assert payload["refresh"] and payload["page_size"] == 2
    assert view.revalidating and not view.busy and len(view.data["items"]) == 2
    worker.succeeded.emit(2, {"items": songs("a", "b", "c"), "cursor": None})
    assert not view.revalidating and len(view.data["items"]) == 3

    later = catalog_view.time.monotonic() + catalog_view.MEMORY_TTL + 1
    monkeypatch.setattr(catalog_view.time, "monotonic", lambda: later)
    view.load("library_songs", {})
    assert len(worker.requests) == 3 and not worker.requests[-1][1]["refresh"]
    assert view.revalidating and len(view.data["items"]) == 3


def test_identical_revalidation_keeps_the_page_without_emitting_changed(tmp_path):
    worker, account, view = memory_view(tmp_path)
    view.load("history", {})
    worker.succeeded.emit(1, {"items": songs("a", "b"), "cursor": None})
    view.load("history", {})
    assert len(worker.requests) == 2 and view.revalidating
    emitted = []
    view.changed.connect(lambda: emitted.append(True))
    worker.succeeded.emit(2, {"items": songs("a", "b"), "cursor": None})
    assert not emitted and not view.revalidating
    view.load("history", {})
    revision = view.revision
    view.saveScroll(320)
    worker.succeeded.emit(3, {"items": songs("b", "a"), "cursor": None})
    assert emitted and view.revision == revision and view.scrollPosition == 320
    assert [item["videoId"] for item in view.data["items"]] == ["b", "a"]


def test_failed_revalidation_keeps_the_remembered_page(tmp_path):
    worker, account, view = memory_view(tmp_path)
    view.load("history", {})
    worker.succeeded.emit(1, {"items": songs("a"), "cursor": None})
    view.load("history", {})
    worker.failed.emit(2, {"code": "offline", "message": "Offline"})
    assert not view.revalidating and not view.error and view.data["items"][0]["videoId"] == "a"


def test_clear_memory_and_accounts_do_not_share_entries(tmp_path):
    worker, account, view = memory_view(tmp_path)
    view.load("library_songs", {})
    worker.succeeded.emit(1, {"items": songs("a"), "cursor": None})
    account.profile = {"name": "Two", "handle": "@two"}
    view.load("library_songs", {})
    assert len(worker.requests) == 2 and view.busy and not view.data
    worker.succeeded.emit(2, {"items": songs("z"), "cursor": None})
    account.profile = {"name": "One", "handle": "@one"}
    view.load("library_songs", {})
    assert len(worker.requests) == 2 and view.data["items"][0]["videoId"] == "a"
    view.clearMemory()
    view.load("library_songs", {})
    assert len(worker.requests) == 3 and view.busy and not view.data


def test_routes_outside_the_library_are_not_remembered(tmp_path):
    worker, account, view = memory_view(tmp_path)
    view.load("search", {"query": "x"})
    worker.succeeded.emit(1, {"items": songs("a"), "cursor": None})
    view.load("search", {"query": "x"})
    assert len(worker.requests) == 2 and view.busy
