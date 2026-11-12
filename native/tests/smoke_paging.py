"""Lists load more by themselves while scrolling and stay where they are when rows arrive."""

import tempfile
import traceback

from PySide6.QtCore import QMetaObject, QObject, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from tubify import app


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


def songs(start, end):
    return [{"kind": "song", "title": f"Song {number}", "videoId": f"{number:011d}", "duration": 60, "artists": [{"name": "Artist"}]} for number in range(start, end)]


def shelves(start, end):
    return [{"title": f"Shelf {number}", "layout": "cards", "items": [{**song, "kind": "album", "id": f"MPRE{number}"} for song in songs(number * 10, number * 10 + 6)]} for number in range(start, end)]


def visual_items(item):
    yield item
    for child in item.childItems():
        yield from visual_items(child)


def main():
    original, passed = app.load_window, []

    def load(*args, **kwargs):
        engine = original(*args, **kwargs)
        window = engine.rootObjects()[0]
        shell, view, browse, library = args[0], args[3], args[5], args[9]

        def wait(condition=lambda: False, milliseconds=1500):
            for _ in range(milliseconds // 10):
                if condition():
                    return True
                QTest.qWait(10)
            return condition()

        def verify():
            try:
                window.resize(1280, 820)
                QTest.qWait(100)
                worker = Worker()
                view.worker = worker
                worker.succeeded.connect(view._succeeded)
                worker.failed.connect(view._failed)
                find = lambda name: window.findChild(QObject, name)

                # Partway down a playlist nothing loads, and arriving rows leave the list alone.
                view.showLocal("playlist", {"title": "Long", "items": songs(0, 100), "cursor": 100}, {"id": "PLlong"})
                assert wait(lambda: find("collectionSongs") and find("collectionSongs").property("count") == 100)
                rows = find("collectionSongs")
                QTest.qWait(100)
                assert not worker.requests, worker.requests
                rows.setProperty("contentY", 1000.0)
                QTest.qWait(100)
                assert not worker.requests
                view.more()
                worker.succeeded.emit(len(worker.requests), {"title": "Long", "items": songs(100, 140), "cursor": 140})
                assert wait(lambda: rows.property("count") == 140)
                QTest.qWait(100)
                assert rows.property("contentY") == 1000.0, rows.property("contentY")

                # Scrolling near the end loads the next page without any action, and keeps the place.
                near_end = rows.property("originY") + rows.property("contentHeight") - 1.5 * rows.property("height")
                rows.setProperty("contentY", near_end)
                assert wait(lambda: len(worker.requests) == 2 and view.busy), worker.requests
                assert worker.requests[-1]["offset"] == 140
                worker.succeeded.emit(2, {"title": "Long", "items": songs(140, 180), "cursor": None})
                assert wait(lambda: rows.property("count") == 180)
                QTest.qWait(100)
                assert rows.property("contentY") == near_end, rows.property("contentY")
                # The list has no more pages, so reaching its end asks for nothing.
                rows.setProperty("contentY", rows.property("originY") + rows.property("contentHeight") - rows.property("height"))
                QTest.qWait(100)
                assert len(worker.requests) == 2

                # Edits refresh rows in place rather than sending the list back to the top.
                position = rows.property("contentY")
                view.data["items"][0]["title"] = "Renamed"
                view.patch({})
                QTest.qWait(100)
                assert rows.property("contentY") == position

                # A first page too short to scroll keeps loading.
                worker.requests.clear()
                view.showLocal("playlist", {"title": "Short", "items": songs(0, 2), "cursor": 2}, {"id": "PLshort"})
                assert wait(lambda: len(worker.requests) == 1), worker.requests
                worker.succeeded.emit(1, {"title": "Short", "items": songs(2, 4), "cursor": 4})
                assert wait(lambda: len(worker.requests) == 2), worker.requests
                # A failed page does not retry by itself.
                worker.failed.emit(2, {"message": "offline"})
                assert view.error == "offline"
                QTest.qWait(200)
                assert len(worker.requests) == 2, worker.requests
                worker.succeeded.emit(2, {"items": [], "cursor": None})

                # Home pages through shelves, keeping the place the same way.
                worker.requests.clear()
                view.showLocal("home", {"title": "Home", "items": [], "shelves": shelves(0, 12), "cursor": 12}, {})
                assert wait(lambda: find("browseSections") and find("browseSections").property("count") == 12)
                home = find("browseSections")
                QTest.qWait(100)
                worker.requests.clear()
                view._busy = False
                view._request = None
                home.setProperty("contentY", 500.0)
                QTest.qWait(50)
                assert not worker.requests
                near_end = home.property("originY") + home.property("contentHeight") - 1.5 * home.property("height")
                home.setProperty("contentY", near_end)
                assert wait(lambda: worker.requests), "Home did not load more"
                position = home.property("contentY")
                worker.succeeded.emit(len(worker.requests), {"title": "Home", "items": [], "shelves": shelves(12, 18), "cursor": None})
                assert wait(lambda: home.property("count") == 18)
                QTest.qWait(100)
                assert home.property("contentY") == position, (home.property("contentY"), position)

                # Library song rows use the same paging.
                worker.requests.clear()
                shell.navigate("Library")
                library._selected = "Songs"
                view.showLocal("library_songs", {"title": "Songs", "items": songs(0, 60), "cursor": 60}, {"order": "recently_added"})
                assert wait(lambda: find("librarySongs") and find("librarySongs").property("count") == 60)
                library_rows = find("librarySongs")
                QTest.qWait(100)
                worker.requests.clear()
                library_rows.setProperty("contentY", library_rows.property("originY") + library_rows.property("contentHeight") - 1.5 * library_rows.property("height"))
                assert wait(lambda: worker.requests), "Library did not load more"
                position = library_rows.property("contentY")
                worker.succeeded.emit(len(worker.requests), {"title": "Songs", "items": songs(60, 100), "cursor": None})
                assert wait(lambda: library_rows.property("count") == 100)
                QTest.qWait(100)
                assert library_rows.property("contentY") == position

                # Filtered search results page too, and their rows show the right songs.
                shell.navigate("Search")
                view.showLocal("search", {"title": "Query", "items": songs(0, 60), "cursor": 60}, {"query": "Query"})
                assert wait(lambda: find("searchResults") and find("searchResults").property("count") == 60)
                results = find("searchResults")
                QTest.qWait(100)
                worker.requests.clear()
                results.setProperty("contentY", results.property("originY") + results.property("contentHeight") - 1.5 * results.property("height"))
                assert wait(lambda: worker.requests), "Search did not load more"
                position = results.property("contentY")
                worker.succeeded.emit(len(worker.requests), {"title": "Query", "items": songs(60, 80), "cursor": None})
                assert wait(lambda: results.property("count") == 80)
                QTest.qWait(100)
                assert results.property("contentY") == position

                # Selecting the current landing page scrolls smoothly to the top and keeps its rows.
                shell.navigate("Home")
                worker.requests.clear()
                browse.fixture = None
                view.showLocal("home", {"title": "Home", "items": [], "shelves": shelves(0, 12), "cursor": None}, {})
                assert wait(lambda: find("browseSections") and find("browseSections").property("count") == 12)
                home = find("browseSections")
                QTest.qWait(100)
                home.setProperty("contentY", 1500.0)
                button = next(item for item in visual_items(window.contentItem()) if item.objectName() == "navigationButton-Home")
                assert QMetaObject.invokeMethod(button, "clicked")
                QTest.qWait(60)
                top = home.property("originY") - home.property("topMargin")
                assert top < home.property("contentY") < 1500.0, home.property("contentY")  # Partway there: animated.
                assert wait(lambda: home.property("contentY") == top), home.property("contentY")
                assert worker.requests[-1]["refresh"] and worker.requests[-1]["route"] == "home" and view.revalidating
                assert home.property("count") == 12
                worker.succeeded.emit(len(worker.requests), {"title": "Home", "items": [], "shelves": shelves(0, 6), "cursor": 6})
                assert wait(lambda: home.property("count") == 6)
                QTest.qWait(100)
                assert home.property("contentY") == top
                # Scrolling and the sidebar replace the buttons that used to do this.
                visible = [item.property("text") for item in visual_items(window.contentItem()) if item.isVisible()]
                assert not {"Refresh", "Load More", "More Music"} & {text for text in visible if isinstance(text, str)}, visible

                assert not engine.property("qmlWarnings"), engine.property("qmlWarnings")
                passed.append(True)
            except Exception:
                traceback.print_exc()
            finally:
                window.close()
                QGuiApplication.instance().exit(0 if passed else 1)

        QTimer.singleShot(300, verify)
        QTimer.singleShot(40000, window.close)
        return engine

    app.load_window = load
    with tempfile.TemporaryDirectory(prefix="tubify-paging-") as folder:
        result = app.main(["--fixture", "--data-dir", folder])
    app.load_window = original
    assert result == 0 and passed
    print("Paging kept the scroll position in playlists, Home, Library and search; selecting Home returned to the top and refreshed.")


if __name__ == "__main__":
    main()
