"""Exercise independent dock intent and responsive geometry in the real QML scene."""

from pathlib import Path
import tempfile
import traceback

from PySide6.QtCore import QObject, QMetaObject, QPointF, QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from youtube_music_native import app


def find_visual(item, name):
    if item.objectName() == name:
        return item
    for child in item.childItems():
        found = find_visual(child, name)
        if found:
            return found


def main():
    original, passed = app.load_window, []

    def load(*args, **kwargs):
        engine = original(*args, **kwargs)
        window = engine.rootObjects()[0]
        shell, player, lyrics = args[0], args[2], args[10]

        def verify():
            try:
                content = window.findChild(QObject, "pageContent")
                queue = window.findChild(QObject, "queueSidebar")
                lyric = window.findChild(QObject, "lyricsSidebar")
                bar = window.findChild(QObject, "playerBar")
                baseline = (player.position, player.playing, player.currentTrack, shell.page)
                shell.setQueueOpen(False)
                shell.setLyricsOpen(False)
                assert not lyrics._active
                for size in ((1600, 900), (1280, 820), (920, 620)):
                    window.resize(*size)
                    shell.setQueueOpen(False)
                    shell.setLyricsOpen(True)
                    QTest.qWait(80)
                    assert lyric.isVisible() and not queue.isVisible() and lyrics._active
                    assert lyric.x() + lyric.width() == size[0]
                    assert content.x() + content.width() == lyric.x()
                    shell.setQueueOpen(True)
                    QTest.qWait(80)
                    dual = size[0] >= 1280
                    assert queue.isVisible() and lyric.isVisible() == dual
                    assert bool(window.property("tabbedDocks")) != dual
                    assert content.width() >= (480 if dual else 320)
                    assert queue.width() >= 280
                    if dual:
                        assert lyric.width() >= 280 and lyric.x() + lyric.width() == queue.x()
                    else:
                        assert not lyrics._active
                        tab = find_visual(window.contentItem(), "dockTab-Queue-Lyrics")
                        tab.forceActiveFocus()
                        QMetaObject.invokeMethod(tab, "clicked")
                        QTest.qWait(40)
                        assert lyric.isVisible() and not queue.isVisible() and lyrics._active, (shell.activeDock, lyric.isVisible(), queue.isVisible(), lyrics._active)
                        assert window.activeFocusItem().isVisible()
                        assert window.activeFocusItem().objectName() == "dockTab-Lyrics-Lyrics"
                    assert bar.isVisible() and bar.y() >= lyric.y() + lyric.height()
                    search = window.findChild(QObject, "searchField")
                    settings = window.findChild(QObject, "settingsButton")
                    assert search.x() + search.width() <= settings.x()
                    QMetaObject.invokeMethod(window.findChild(QObject, "dockClose-Lyrics"), "clicked")
                    QTest.qWait(40)
                    assert not shell.lyricsOpen and shell.queueOpen and queue.isVisible()
                    assert not lyrics._active
                shell.setLyricsWidth(500)
                shell.setQueueWidth(460)
                shell.setLyricsOpen(True)
                window.resize(1600, 900)
                QTest.qWait(40)
                assert lyric.isVisible() and queue.isVisible()
                assert content.width() >= 480
                window.resize(920, 620)
                QTest.qWait(40)
                assert lyric.isVisible() and not queue.isVisible()
                window.resize(1600, 900)
                QTest.qWait(40)
                assert lyric.isVisible() and queue.isVisible()
                assert (shell.lyricsWidth, shell.queueWidth) == (500, 460)
                handle = window.findChild(QObject, "lyricsResizeHandle")
                point = handle.mapToScene(QPointF(handle.width()/2, 150)).toPoint()
                QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=point)
                QTest.mouseMove(window, point + QPointF(50, 0).toPoint(), delay=30)
                QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=point + QPointF(50, 0).toPoint())
                QTest.qWait(40)
                assert shell.lyricsWidth < 500
                assert (player.position, player.playing, player.currentTrack, shell.page) == baseline
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
    with tempfile.TemporaryDirectory(prefix="youtube-music-docks-") as folder:
        result = app.main(["--fixture", "--data-dir", folder])
    app.load_window = original
    assert result == 0 and passed
    print("Independent dock controls, responsive tabs, sizing and playback preservation passed.")


if __name__ == "__main__":
    main()
