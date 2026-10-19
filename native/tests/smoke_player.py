"""Exercise expanded views and shortcut isolation in an actual QML window."""

from pathlib import Path
import tempfile
import traceback

from PySide6.QtCore import QObject, QMetaObject, QPointF, QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from youtube_music_native import app


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
        shell, player, lyrics = args[0], args[2], args[10]

        def verify():
            try:
                position, playing = player.position, player.playing
                player.enqueue([dict(entry) for entry in player.entries[:3]])
                player.queue.source_label = "Fixture album"
                player.appendContext([
                    {"videoId": "source00001", "title": "Source one", "duration": 60},
                    {"videoId": "source00002", "title": "Source two", "duration": 60},
                ])
                assert [row["group"] for row in player.entries[:4]] == ["Now playing"] + ["Next in queue"] * 3
                shell.requestAction("expandPlayer")
                QTest.qWait(80)
                window.resize(1280, 1400)
                QTest.qWait(80)
                assert window.findChild(QObject, "expandedPlayer")
                queue_list = window.findChild(QObject, "queueList")
                assert queue_list
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
                QTest.qWait(50)
                preview = window.findChild(QObject, "queueDragPreview")
                indicators = [node for node in visual_items(window.contentItem()) if node.objectName().startswith("expandedQueueDrop")]
                assert preview and preview.isVisible()
                assert any(node.isVisible() for node in indicators)
                QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=end)
                QTest.qWait(50)
                assert player.entries[2]["key"] == dragging
                dragging = player.entries[1]["key"]
                row = visual_item(window.contentItem(), "queueSong-" + dragging)
                start = row.mapToScene(QPointF(min(60, row.width() - 120), row.height() / 2)).toPoint()
                end = start + QPointF(0, 64).toPoint()
                QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=start)
                QTest.mouseMove(window, start + QPointF(0, 20).toPoint(), delay=30)
                QTest.mouseMove(window, end, delay=30)
                QTest.qWait(50)
                preview = window.findChild(QObject, "queueDragPreview")
                indicators = [node for node in visual_items(window.contentItem()) if node.objectName().startswith("expandedQueueDrop")]
                assert preview and preview.isVisible()
                assert any(node.isVisible() for node in indicators)
                QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=end)
                QTest.qWait(50)
                assert player.entries[2]["key"] == dragging
                source = next(row for row in player.entries if row["group"].startswith("Next from "))
                first_manual = next(row for row in player.entries if row["group"] == "Next in queue")
                source_row = visual_item(window.contentItem(), "queueSong-" + source["key"])
                target_row = visual_item(window.contentItem(), "queueSong-" + first_manual["key"])
                start = source_row.mapToScene(QPointF(min(60, source_row.width() - 120), source_row.height() / 2)).toPoint()
                end = target_row.mapToScene(QPointF(100, target_row.height() / 2)).toPoint()
                QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=start)
                QTest.mouseMove(window, end, delay=40)
                QTest.qWait(50)
                QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=end)
                QTest.qWait(50)
                assert next(row for row in player.entries if row["key"] == source["key"])["group"] == "Next in queue"
                source = next(row for row in player.entries if row["group"].startswith("Next from "))
                source_row = visual_item(window.contentItem(), "queueSong-" + source["key"])
                section = visual_item(window.contentItem(), "expandedQueueSectionHeader-Next in queue")
                start = source_row.mapToScene(QPointF(min(60, source_row.width() - 120), source_row.height() / 2)).toPoint()
                end = section.mapToScene(QPointF(section.width() / 2, section.height() / 2)).toPoint()
                QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=start)
                QTest.mouseMove(window, end, delay=40)
                QTest.qWait(50)
                queue_list = window.findChild(QObject, "queueList")
                assert queue_list.property("dropToManual")
                QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=end)
                QTest.qWait(50)
                assert next(row for row in player.entries if row["key"] == source["key"])["group"] == "Next in queue"
                player.clearManualQueue()
                QTest.qWait(50)
                source = next(row for row in player.entries if row["group"].startswith("Next from "))
                source_row = visual_item(window.contentItem(), "queueSong-" + source["key"])
                section = visual_item(window.contentItem(), "expandedQueueSectionHeader-" + source["group"])
                start = source_row.mapToScene(QPointF(min(60, source_row.width() - 120), source_row.height() / 2)).toPoint()
                end = section.mapToScene(QPointF(section.width() / 2, section.height() / 2)).toPoint()
                QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=start)
                QTest.mouseMove(window, end, delay=40)
                QTest.qWait(50)
                assert queue_list.property("dropToManual")
                QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=end)
                QTest.qWait(50)
                assert player.manualCount == 1
                assert next(row for row in player.entries if row["key"] == source["key"])["group"] == "Next in queue"
                queued_track = player.entries[-1]
                artwork = next(node for node in visual_items(window.contentItem()) if node.objectName() == "queueArtworkActivate-" + queued_track["key"])
                QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=artwork.mapToScene(QPointF(artwork.width() / 2, artwork.height() / 2)).toPoint())
                QTest.qWait(50)
                assert player.currentTrack.get("videoId", player.currentTrack.get("id")) == queued_track.get("videoId", queued_track.get("id"))
                assert len(player.queue.history) >= 2
                skipped = [row["track"].get("videoId", row["track"].get("id")) for row in player.queue.history]
                player._position = 0
                player.previous()
                assert player.currentTrack.get("videoId", player.currentTrack.get("id")) == skipped[-1]
                player._position = 0
                player.previous()
                assert player.currentTrack.get("videoId", player.currentTrack.get("id")) == skipped[-2]
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
                    assert pane.property("width") >= 680 and pane.property("height") == size[1] - 180
                current = player.currentTrack
                source = list(player.queue.source)
                clear = window.findChild(QObject, "clearQueuedSongs")
                QMetaObject.invokeMethod(clear, "clicked")
                assert not player.queue.manual and player.queue.source == source and player.currentTrack == current
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
