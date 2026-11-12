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
                panel_header_height = lambda: window.findChild(QObject, "panelHeaderDivider").parentItem().height()
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
                        assert page_line.mapToScene(QPointF(page_line.width(), 0)).x() == panel.x()
                        assert panel.width() >= 280
                        # The panel never squeezes the page below 480 px unless it is already at its 280 px minimum.
                        assert content.width() >= 480 or panel.width() == 280, (size, content.width())
                        assert content.x() + content.width() + 12 == panel.x()
                        # The panel's gap replaces the page's right gutter.
                        page = window.findChild(QObject, "browseSections")
                        assert page.isVisible() and page.mapToScene(QPointF(page.width(), 0)).x() + 12 == panel.x()
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
                # The bar's controls open each panel over the full player, whose stage moves aside.
                for size in ((1600, 900), (920, 620)):
                    window.resize(*size)
                    shell.setExpanded(True)
                    QTest.qWait(40)
                    stage = window.findChild(QObject, "expandedPlayer")
                    artwork = window.findChild(QObject, "immersiveArtwork")
                    artwork_center = lambda: artwork.mapToScene(QPointF(artwork.width() / 2, 0)).x()
                    # The background runs under the bar and panel to the window edge.
                    assert stage.isVisible() and stage.x() == 0 and stage.width() == size[0]
                    assert abs(artwork_center() - size[0] / 2) <= 1, (size, artwork_center())
                    for toggle, name in (("queueToggle", "Queue"), ("lyricsToggle", "Lyrics"), ("nowPlayingViewToggle", "NowPlaying")):
                        QMetaObject.invokeMethod(window.findChild(QObject, toggle), "clicked")
                        QTest.qWait(40)
                        assert shell.panel == name and shell.expanded and panel.isVisible() and stage.isVisible()
                        assert stage.width() == size[0] and abs(artwork_center() - (size[0] - window.property("panelSpace")) / 2) <= 1
                        assert artwork.mapToScene(QPointF(artwork.width(), 0)).x() <= panel.x()
                        # Its header keeps its height though the page header has collapsed.
                        assert panel_header_height() == 52
                        QMetaObject.invokeMethod(window.findChild(QObject, toggle), "clicked")
                        QTest.qWait(40)
                        assert shell.panel == "" and shell.expanded and not panel.isVisible()
                    # Leaving and entering the full player leave the panel open.
                    shell.setQueueOpen(True)
                    QTest.qWait(40)
                    QMetaObject.invokeMethod(window.findChild(QObject, "immersiveToggle"), "clicked")
                    QTest.qWait(40)
                    assert not shell.expanded and shell.queueOpen and panel.isVisible()
                    QMetaObject.invokeMethod(window.findChild(QObject, "immersiveToggle"), "clicked")
                    QTest.qWait(40)
                    assert shell.expanded and shell.queueOpen and panel.isVisible()
                    shell.setPanel("")
                    shell.setExpanded(False)
                    QTest.qWait(40)
                window.resize(1600, 900)
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
                # Switching panels fades the old one out, then brings the new one in, while the card stays put.
                body = window.findChild(QObject, "panelBody")
                shell.setLyricsOpen(True)
                assert queue.isVisible() and not lyric.isVisible() and lyrics._active and abs(offset()) < 0.5 and panel.property("opacity") == 1
                wait(lambda: lyric.isVisible() and body.property("opacity") == 1)
                assert not queue.isVisible()
                # Quick switches end on the last panel chosen.
                shell.setPanel("NowPlaying")
                shell.setQueueOpen(True)
                shell.setLyricsOpen(True)
                wait(lambda: body.property("opacity") == 1 and lyric.isVisible() and not now.isVisible())
                assert not queue.isVisible()
                # A panel opening from closed only slides.
                shell.setPanel("")
                wait(lambda: not panel.isVisible())
                shell.setQueueOpen(True)
                assert queue.isVisible() and body.property("opacity") == 1
                wait(lambda: abs(offset()) < 0.5 and panel.property("opacity") == 1)
                # The header's buttons stay in front of the panel for the whole slide, leaving and arriving.
                profile = window.findChild(QObject, "profileButton")
                profile_edge = lambda: profile.mapToScene(QPointF(profile.width(), 0)).x()
                clear_of_panel = lambda: profile_edge() <= panel.mapToScene(QPointF()).x() + 0.5
                beside_open_panel = profile_edge()
                shell.setPanel("")
                assert panel.isVisible() and panel.property("leaving") and not panel.isEnabled() and queue.isVisible()
                assert abs(profile_edge() - beside_open_panel) <= 2
                while panel.isVisible():
                    assert clear_of_panel()
                    QTest.qWait(10)
                # Closing fades the panel out as it slides.
                assert panel.property("opacity") < 0.1
                assert profile_edge() > beside_open_panel
                shell.setQueueOpen(True)
                while abs(offset()) >= 0.5 or panel.property("opacity") < 1:
                    assert clear_of_panel()
                    QTest.qWait(10)
                assert abs(profile_edge() - beside_open_panel) <= 1
                shell.setPanel("")
                assert panel.isVisible() and panel.property("leaving") and not panel.isEnabled() and queue.isVisible()
                assert content.x() + content.width() == window.findChild(QObject, "scaledContent").width()
                # A slow runner can finish the slide before this looks again, so only a slide still running is reversed.
                wait(lambda: offset() > 1 or not panel.property("leaving"))
                # Reopening mid-close reverses from where the panel is.
                if panel.property("leaving"):
                    closing_offset = offset()
                    shell.setQueueOpen(True)
                    assert panel.isEnabled() and not panel.property("leaving") and 0 < offset() <= closing_offset + 0.5
                else:
                    shell.setQueueOpen(True)
                wait(lambda: abs(offset()) < 0.5 and panel.property("opacity") == 1)
                shell.setPanel("")
                wait(lambda: not panel.isVisible())
                # The full player slides up and down behind an open panel, spanning the window throughout.
                shell.setQueueOpen(True)
                wait(lambda: abs(offset()) < 0.5)
                shell.setExpanded(True)
                stage = window.findChild(QObject, "expandedPlayer")
                assert window.property("immersiveOpening") and stage.width() == window.width()
                wait(lambda: not window.property("immersiveOpening"))
                assert stage.width() == window.width() and panel.isVisible()
                # The artwork moves along with the panel instead of jumping when the slide starts.
                artwork = window.findChild(QObject, "immersiveArtwork")
                artwork_center = lambda: artwork.mapToScene(QPointF(artwork.width() / 2, 0)).x()
                beside_panel = artwork_center()
                centered = stage.width() / 2
                assert centered - beside_panel > 100
                shell.setPanel("")
                assert abs(artwork_center() - beside_panel) <= 2
                wait(lambda: not panel.isVisible())
                assert abs(artwork_center() - centered) <= 1
                shell.setQueueOpen(True)
                assert abs(artwork_center() - centered) <= 2
                wait(lambda: abs(offset()) < 0.5)
                assert abs(artwork_center() - beside_panel) <= 1
                shell.setExpanded(False)
                assert window.property("immersiveClosing") and stage.width() == window.width() and panel.isVisible()
                wait(lambda: not window.property("immersiveClosing"))
                assert shell.queueOpen and not stage.isVisible()
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
