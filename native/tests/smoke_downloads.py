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
                listing = window.findChild(QObject, "downloadsList")
                assert pane and listing.property("count") == 4
                pane.setProperty("selectedKind", "Songs")
                assert listing.property("count") == 1
                pane.setProperty("selectedKind", "All")
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
                pane.setProperty("selectedEntry", first)
                dialog = window.findChild(QObject, "downloadRemovalDialog")
                assert QMetaObject.invokeMethod(dialog, "open")
                QTest.qWait(50)
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
