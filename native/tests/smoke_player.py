"""Exercise expanded views and shortcut isolation in an actual QML window."""

from pathlib import Path
import tempfile
import traceback

from PySide6.QtCore import QObject, QMetaObject, QPointF, QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from youtube_music_native import app


def main():
    original = app.load_window
    passed = []

    def load(*args, **kwargs):
        engine = original(*args, **kwargs)
        window = engine.rootObjects()[0]
        shell, player, lyrics = args[0], args[2], args[10]

        def verify():
            try:
                position, playing = player.position, player.playing
                shell.requestAction("expandPlayer")
                QTest.qWait(80)
                assert window.findChild(QObject, "expandedPlayer")
                assert window.findChild(QObject, "queueList")
                assert player.position == position and player.playing == playing
                shell.setPlayerTab("Lyrics")
                QTest.qWait(80)
                assert window.findChild(QObject, "lyricsPane") and lyrics.data["available"]
                lyrics.seekLine(1)
                assert player.position == 5 and lyrics.currentLine == 1
                shell.setPlayerTab("Up next")
                QTest.qWait(80)
                entry = player.entries[-1]
                shell.showMenu(entry, {"queueKey": entry["key"]})
                QTest.qWait(50)
                menu = window.findChild(QObject, "mediaMenu")
                item = next(node for node in menu.findChildren(QObject) if node.property("text") == "Remove from queue")
                QMetaObject.invokeMethod(item, "triggered")
                QMetaObject.invokeMethod(menu, "close")
                assert all(row["key"] != entry["key"] for row in player.entries)
                QTest.qWait(200)
                window.requestActivate()
                key = player.entries[1]["key"]
                def visual_item(item, name):
                    if item.objectName() == name:
                        return item
                    for child in item.childItems():
                        found = visual_item(child, name)
                        if found:
                            return found
                row = visual_item(window.contentItem(), "queueSong-" + key)
                assert row
                row.forceActiveFocus()
                QTest.qWait(30)
                assert window.activeFocusItem() == row, window.activeFocusItem().objectName()
                QTest.keyClick(window, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)
                QTest.qWait(30)
                assert player.entries[2]["key"] == key
                assert window.activeFocusItem().objectName() == "queueSong-" + key
                QTest.keyClick(window, Qt.Key.Key_Delete)
                assert all(row["key"] != key for row in player.entries)
                QTest.qWait(50)
                dragging = player.entries[1]["key"]
                handle = visual_item(window.contentItem(), "queueDrag-" + dragging)
                start = handle.mapToScene(QPointF(handle.width() / 2, handle.height() / 2)).toPoint()
                end = start + QPointF(0, 64).toPoint()
                QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=start)
                QTest.mouseMove(window, start + QPointF(0, 20).toPoint(), delay=30)
                QTest.mouseMove(window, end, delay=30)
                QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=end)
                QTest.qWait(50)
                assert player.entries[2]["key"] == dragging
                QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
                QTest.qWait(30)
                field = window.findChild(QObject, "searchField")
                assert field.property("activeFocus")
                state = (player.playing, player.position, player.repeat, player.shuffled, shell.volume, shell.expanded)
                for key in (Qt.Key.Key_Space, Qt.Key.Key_F, Qt.Key.Key_M, Qt.Key.Key_R, Qt.Key.Key_S, Qt.Key.Key_Minus):
                    QTest.keyClick(window, key)
                QTest.keyClick(window, Qt.Key.Key_Right)
                QTest.keyClick(window, Qt.Key.Key_N, Qt.KeyboardModifier.ShiftModifier)
                assert (player.playing, player.position, player.repeat, player.shuffled, shell.volume, shell.expanded) == state
                QTest.keyClick(window, Qt.Key.Key_Tab)
                assert not field.property("activeFocus") and window.activeFocusItem()
                for size in ((1280, 820), (920, 620)):
                    window.resize(*size)
                    QTest.qWait(80)
                    pane = window.findChild(QObject, "expandedPlayer")
                    assert pane.property("width") >= 680 and pane.property("height") >= 480
                shell.setExpanded(False)
                assert player.position == state[1] and player.playing == state[0]
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
    with tempfile.TemporaryDirectory(prefix="youtube-music-player-") as folder:
        result = app.main(["--fixture", "--data-dir", folder])
    app.load_window = original
    assert result == 0 and passed
    print("Expanded player, timed lyrics, queue editing and text-entry isolation passed.")


if __name__ == "__main__":
    main()
