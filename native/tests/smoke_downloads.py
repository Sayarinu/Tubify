"""Exercise native Downloads navigation, repair controls and removal confirmation."""

import tempfile
import traceback

from PySide6.QtCore import QObject, QMetaObject, QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from tubify import app


def visual_items(item):
    yield item
    for child in item.childItems():
        yield from visual_items(child)


def main():
    original = app.load_window
    passed = []

    def load(*args, **kwargs):
        engine = original(*args, **kwargs)
        window = engine.rootObjects()[0]
        shell, player, view, browse, downloads = args[0], args[2], args[3], args[5], args[6]

        def verify():
            try:
                shell.navigate("Downloads")
                QTest.qWait(80)
                pane = window.findChild(QObject, "downloadsPane")
                grid = window.findChild(QObject, "downloadsGrid")
                songs = window.findChild(QObject, "downloadsSongs")
                # Playlists first, as in Library; there is no All chip.
                assert pane and downloads.filter == "Playlists" and grid.property("count") == 2
                assert downloads.filters == ["Playlists", "Albums", "Songs"]
                titles = lambda: [downloads.collectionsModel.data(downloads.collectionsModel.index(row), downloads.collectionsModel.ROW)["title"] for row in range(downloads.collectionsModel.rowCount())]
                downloads.sort("A to Z")
                assert titles() == sorted(titles(), key=str.casefold)
                downloads.sort("Z to A")
                assert titles() == sorted(titles(), key=str.casefold, reverse=True)
                downloads.setFilter("Albums")
                assert grid.property("count") == 1
                downloads.setFilter("Songs")
                QTest.qWait(50)
                assert songs.isVisible() and not grid.isVisible() and songs.property("count") == len(downloads.songs) > 0
                assert "Artist" in downloads.orders
                downloads.playSongs(0)
                assert len(player.entries) == len(downloads.songs) and len({entry.get("videoId") or entry["id"] for entry in player.entries}) == len(player.entries)
                downloads.setFilter("Playlists")
                # A queued download shows an empty ring, a downloading one fills it, and finishing
                # fills it the rest of the way before the check takes its place.
                finished = next(entry for entry in downloads.collections if entry["state"] == "complete")

                def show(state, progress):
                    downloads._collections = [{**entry, "state": state, "progress": progress} if entry["key"] == finished["key"] else entry for entry in downloads._collections]
                    downloads._index()
                    downloads.changed.emit()
                    downloads._states_changed()
                    QTest.qWait(400)

                def ring():
                    found = [item for item in visual_items(window.contentItem()) if item.objectName() == "downloadProgressRing" and item.isVisible()]
                    return found[0] if found else None

                show("queued", 0.)
                assert ring() and ring().parentItem().property("ringValue") == 0
                assert ring().parentItem().property("tip") == "Waiting to Download · Cancel Download"
                button = ring().parentItem()
                assert button.property("contentItem").property("opacity") == 0
                show("downloading", 0.5)
                assert abs(button.property("ringValue") - 0.5) < 0.01 and button.property("tip").startswith("Downloading 50%")
                motion = not window.property("reducedMotion") and not shell.reducedMotion
                downloads._collections = [{**entry, "state": "complete", "progress": 1.} if entry["key"] == finished["key"] else entry for entry in downloads._collections]
                downloads._index()
                downloads.changed.emit()
                downloads._states_changed()
                QTest.qWait(60)
                if motion:
                    assert button.property("finishing") and ring() and button.property("contentItem").property("opacity") == 0
                QTest.qWait(700)
                assert not ring() and not button.property("finishing")
                assert button.property("contentItem").property("opacity") == 1 and button.property("contentItem").property("scale") == 1
                assert button.property("iconName") == "circleCheck"
                pending = next(entry for entry in downloads.collections if entry["state"] == "downloading")
                downloads.cancel(pending["key"])
                assert next(entry for entry in downloads.collections if entry["key"] == pending["key"])["state"] == "cancelled"
                damaged = next(entry for entry in downloads.collections if entry["state"] == "damaged")
                downloads.retry(damaged["key"])
                assert next(entry for entry in downloads.collections if entry["key"] == damaged["key"])["state"] == "complete"
                first = downloads.collections[0]
                downloads.open(first["key"])
                QTest.qWait(80)
                assert view.data["downloadKey"] == first["key"]
                assert window.findChild(QObject, "collectionPane")
                browse.playView()
                assert len(player.entries) == first["total"]
                browse.back()
                QTest.qWait(80)
                pane = window.findChild(QObject, "downloadsPane")
                assert pane and view.route == "downloads"
                dialog = window.findChild(QObject, "downloadRemovalDialog")
                downloads.requestRemoval(first["key"])
                QTest.qWait(50)
                assert dialog.property("opened") and pane.property("selectedEntry")["key"] == first["key"]
                playing = player.playing
                assert window.property("modalOpen")
                QTest.keyClick(window, Qt.Key.Key_Space)
                assert player.playing == playing
                assert QMetaObject.invokeMethod(dialog, "accept")
                QTest.qWait(200)
                assert len(downloads.collections) == 3 and not pane.property("blockingShortcuts")
                window.resize(920, 620)
                QTest.qWait(80)
                assert pane.property("width") >= 680
                assert not engine.property("qmlWarnings"), engine.property("qmlWarnings")
                passed.append(True)
            except Exception:
                traceback.print_exc()
            finally:
                window.close()
                QGuiApplication.instance().exit(0 if passed else 1)

        QTimer.singleShot(200, verify)
        QTimer.singleShot(15000, window.close)
        return engine

    app.load_window = load
    with tempfile.TemporaryDirectory(prefix="youtube-music-downloads-") as folder:
        result = app.main(["--fixture", "--data-dir", folder])
    app.load_window = original
    assert result == 0 and passed
    print("Downloads filters, repair, navigation and removal dialog passed.")


if __name__ == "__main__":
    main()
