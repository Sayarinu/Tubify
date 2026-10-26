"""Exercise native library controls, dialogs and text-input shortcut handling."""

from pathlib import Path
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
        shell, player, view, browse, library = args[0], args[2], args[3], args[5], args[9]

        def verify():
            try:
                shell.navigate("Library")
                QTest.qWait(50)
                assert view.route == "library_playlists" and window.findChild(QObject, "libraryPane")
                library.select("Songs")
                assert all(item["kind"] == "song" for item in view.data["items"])
                library.history()
                assert view.route == "history"
                browse.open({"kind": "playlist", "id": "PLfixture", "title": "Fixture playlist"})
                QTest.qWait(50)
                assert window.findChild(QObject, "collectionPane") and view.data["editable"]
                shell.requestAction("newPlaylist")
                QTest.qWait(50)
                field = window.findChild(QObject, "playlistNameField")
                editor = window.findChild(QObject, "playlistEditor")
                assert field and editor.property("visible")
                playing = player.playing
                field.setProperty("text", "Native")
                QTest.keyClick(window, Qt.Key.Key_Space)
                assert field.property("text") == "Native " and player.playing == playing
                QTest.keyClick(window, Qt.Key.Key_B)
                QTest.keyClick(window, Qt.Key.Key_Return)
                QTest.qWait(50)
                assert view.route == "playlist" and view.data["title"] == "Native b"
                assert view.data["items"] == []
                assert not editor.property("visible")
                browse.open({"kind": "playlist", "id": "PLfixture", "title": "Fixture playlist"})
                QTest.qWait(50)
                track = view.data["items"][0]
                count = len(player.entries)
                shell.showMenu(track, {"playlistId": "PLfixture-created", "index": 0})
                QTest.qWait(50)
                menu = window.findChild(QObject, "mediaMenu")
                item = next(node for node in menu.findChildren(QObject) if node.property("text") == "Add to Queue")
                assert QMetaObject.invokeMethod(item, "triggered")
                assert len(player.entries) == count + 1
                QMetaObject.invokeMethod(menu, "close")
                assert not engine.property("qmlWarnings")
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
    with tempfile.TemporaryDirectory(prefix="youtube-music-library-") as folder:
        result = app.main(["--fixture", "--data-dir", folder])
    app.load_window = original
    assert result == 0 and passed
    print("Native library dialogs, queue menu and text-entry shortcuts passed.")


if __name__ == "__main__":
    main()
