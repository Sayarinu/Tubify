from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication, QObject, Signal

from youtube_music_native.catalog_view import CatalogView
from youtube_music_native.search import Search
from youtube_music_native.shell import ShellController


class Worker(QObject):
    succeeded = Signal(int, dict)
    failed = Signal(int, dict)

    def __init__(self):
        super().__init__()
        self.requests = []

    def request(self, operation, payload):
        self.requests.append(payload)
        return len(self.requests)

    def cancelQueued(self, identifier):
        pass


def test_fast_suggestions_and_search_discard_stale_results_and_restore_filter(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = Worker()
    account = SimpleNamespace(worker=worker, requireReconnect=lambda value: None)
    view = CatalogView(worker, tmp_path / "cache.sqlite3", account)
    shell = ShellController(tmp_path / "settings.ini")
    search = Search(shell, account, view, tmp_path / "cache.sqlite3")
    search.suggest("first")
    assert not worker.requests
    search.timer.stop()
    search._suggest()
    search.suggest("second")
    search.timer.stop()
    search._suggest()
    worker.succeeded.emit(1, {"suggestions": ["old"]})
    worker.succeeded.emit(2, {"suggestions": ["second song", None]})
    assert search.suggestions == ["second song"]
    shell.search("second")
    assert not search.suggestions and view.route == "search"
    search.selectFilter("Albums")
    assert worker.requests[-1]["params"] == {"query": "second", "filter": "albums"}
    worker.succeeded.emit(3, {"title": "Old result", "items": []})
    worker.succeeded.emit(4, {"title": "New result", "items": []})
    assert view.data["title"] == "New result"
    view.showLocal("search", {"items": []}, {"query": "saved query", "filter": "artists"})
    assert search.selectedFilter == "Artists"
