"""Exercise the one-at-a-time side panel and its geometry in the real QML scene."""

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
                panel = window.findChild(QObject, "sidePanel")
                lyric = window.findChild(QObject, "lyricsPane")
                queue = window.findChild(QObject, "queuePane")
                now = window.findChild(QObject, "nowPlayingPane")
                bar = window.findChild(QObject, "playerBar")
                baseline = (player.position, player.playing, player.currentTrack, shell.page)
                # The layout matrix checks where the panel lands, so it runs without the open/close slide; the slide is checked below.
                shell.setReducedMotion(True)
                shell.setPanel("")
                assert not lyrics._active
                for size in ((1600, 900), (1280, 820), (920, 620)):
                    window.resize(*size)
                    for name, pane in (("Lyrics", lyric), ("Queue", queue), ("NowPlaying", now)):
                        shell.setPanel(name)
                        QTest.qWait(80)
                        assert panel.isVisible() and pane.isVisible()
                        assert [other.isVisible() for other in (lyric, queue, now)].count(True) == 1
                        assert lyrics._active == (name == "Lyrics")
                        # The card lines up with the player bar, and its header divider with the page's.
                        assert panel.x() + panel.width() == bar.x() + bar.width() == size[0] - 12
                        assert panel.y() + panel.height() + 12 == bar.y()
                        page_line = window.findChild(QObject, "mainHeaderDivider")
                        panel_line = window.findChild(QObject, "panelHeaderDivider")
                        assert panel_line.mapToScene(QPointF()).y() == page_line.mapToScene(QPointF()).y()
                        assert panel.width() >= 280
                        # The panel never squeezes the page below 480 px unless it is already at its 280 px minimum.
                        assert content.width() >= 480 or panel.width() == 280, (size, content.width())
                        assert content.x() + content.width() + 12 == panel.x()
                        assert bar.isVisible()
                        search = window.findChild(QObject, "searchField")
                        settings = window.findChild(QObject, "settingsButton")
                        assert search.x() + search.width() <= settings.x()
                    close = window.findChild(QObject, "dockClose")
                    close.forceActiveFocus()
                    QMetaObject.invokeMethod(close, "clicked")
                    QTest.qWait(40)
                    assert shell.panel == "" and not panel.isVisible() and not lyrics._active
                    assert window.activeFocusItem().isVisible()
                # The bar's controls replace whichever view is open, including the full player.
                window.resize(1600, 900)
                for toggle, name in (("queueToggle", "Queue"), ("lyricsToggle", "Lyrics"), ("nowPlayingViewToggle", "NowPlaying")):
                    shell.setExpanded(True)
                    assert shell.panel == ""
                    QTest.qWait(40)
                    QMetaObject.invokeMethod(window.findChild(QObject, toggle), "clicked")
                    QTest.qWait(40)
                    assert shell.panel == name and not shell.expanded and panel.isVisible()
                    QMetaObject.invokeMethod(window.findChild(QObject, toggle), "clicked")
                    QTest.qWait(40)
                    assert shell.panel == "" and not panel.isVisible()
                # Every panel has the same size.
                shell.setPanelWidth(460)
                sizes = set()
                for name in ("Lyrics", "Queue", "NowPlaying"):
                    shell.setPanel(name)
                    QTest.qWait(40)
                    sizes.add((panel.width(), panel.height()))
                    assert panel.width() == 460 and content.width() >= 480
                assert len(sizes) == 1
                shell.setQueueOpen(True)
                QTest.qWait(40)
                handle = window.findChild(QObject, "panelResizeHandle")
                point = handle.mapToScene(QPointF(handle.width()/2, 150)).toPoint()
                QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=point)
                QTest.mouseMove(window, point + QPointF(50, 0).toPoint(), delay=30)
                QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=point + QPointF(50, 0).toPoint())
                QTest.qWait(40)
                assert shell.panelWidth < 460

                # Opening a panel slides it in from the right edge; closing slides it out while the page takes its space.
                def offset():
                    return panel.mapToScene(QPointF()).x() - panel.x()

                def wait(condition):
                    for _ in range(100):
                        if condition():
                            return
                        QTest.qWait(10)
                    assert condition()

                shell.setPanel("")
                shell.setReducedMotion(False)
                shell.setQueueOpen(True)
                # The slide starts synchronously from off the right edge, faded out.
                assert panel.isVisible() and panel.isEnabled() and offset() > panel.width() - 1 and panel.property("opacity") < 0.1
                assert content.x() + content.width() + 12 == panel.x()
                wait(lambda: abs(offset()) < 0.5 and panel.property("opacity") == 1)
                # Switching panels swaps the content at once.
                shell.setLyricsOpen(True)
                assert lyric.isVisible() and not queue.isVisible() and abs(offset()) < 0.5 and panel.property("opacity") == 1
                shell.setQueueOpen(True)
                shell.setPanel("")
                assert panel.isVisible() and panel.property("leaving") and not panel.isEnabled() and queue.isVisible()
                assert content.x() + content.width() == window.findChild(QObject, "scaledContent").width()
                # A slow runner can finish the slide before this looks again, so only a slide still running is reversed.
                wait(lambda: offset() > 1 or not panel.property("leaving"))
                assert panel.property("opacity") == 1
                # Reopening mid-close reverses from where the panel is.
                if panel.property("leaving"):
                    closing_offset = offset()
                    shell.setQueueOpen(True)
                    assert panel.isEnabled() and not panel.property("leaving") and 0 < offset() <= closing_offset + 0.5
                else:
                    shell.setQueueOpen(True)
                wait(lambda: abs(offset()) < 0.5)
                shell.setPanel("")
                wait(lambda: not panel.isVisible())
                # Reduced motion shows and hides the panel without sliding.
                shell.setReducedMotion(True)
                shell.setLyricsOpen(True)
                assert panel.isVisible() and abs(offset()) < 0.5
                shell.setPanel("")
                assert not panel.isVisible()
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
    print("One-at-a-time panel, sizing, slide and playback preservation passed.")


if __name__ == "__main__":
    main()
