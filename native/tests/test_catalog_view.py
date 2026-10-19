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
