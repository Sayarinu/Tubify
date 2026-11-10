"""Exercise native Downloads navigation, repair controls and removal confirmation."""

import tempfile
import traceback

from PySide6.QtCore import QObject, QMetaObject, QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from youtube_music_native import app


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
