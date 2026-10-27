"""Exercise the immersive stage without replacing playback, browsing or docks."""

import argparse
import math
from pathlib import Path
import tempfile
import time
import traceback

from PySide6.QtCore import QObject, QMetaObject, QPointF, QTimer, Qt
from PySide6.QtGui import QAccessible, QColor, QGuiApplication, QImage
from PySide6.QtTest import QTest
from PySide6.QtQml import QQmlProperty

from youtube_music_native import app
from youtube_music_native.theme import PRESETS, ThemeState
from smoke_visual import check_queue, visual_items


def check_autoplay(window, player, theme, output_dir=None, label="queue"):
    control = window.findChild(QObject, "queueAutoplay")
    indicator = control.findChild(QObject, "queueAutoplayIndicator")
    state = control.findChild(QObject, "queueAutoplayState")
    track = control.findChild(QObject, "queueAutoplayTrack")
    thumb = control.findChild(QObject, "queueAutoplayThumb")
    assert control.isVisible() and control.height() == 40
    assert abs(indicator.x() + indicator.width() - control.width()) < 0.1
    assert abs(state.x() + state.width() + 8 - indicator.x()) < 0.1
    assert track.width() == 44 and track.height() == 24 and track.property("radius") == 12
    assert control.findChild(QObject, "queueAutoplayLabel").property("contentWidth") < state.x() - 8
    bounds = control.mapRectToScene(control.boundingRect())
    assert bounds.left() >= 0 and bounds.right() <= window.width() + 1
    assert bounds.top() >= 0 and bounds.bottom() <= window.height() + 1
    accessible = QAccessible.queryAccessibleInterface(control)
    assert accessible and accessible.text(QAccessible.Text.Name) == "Autoplay similar music"
    assert accessible.state().checkable
    previous, playing = player.autoplay, player.playing
    if player.autoplay:
        player.toggleAutoplay()
    QTest.qWait(20)

    def verify(expected):
        assert control.property("checked") == player.autoplay == expected
        assert state.property("text") == ("On" if expected else "Off")
        assert abs(thumb.x() - (23 if expected else 3)) < 0.1
        assert track.property("color") == QColor(theme.accent if expected else theme.progressTrack)
        assert accessible.state().checked == expected
        if not expected:
            assert QQmlProperty.read(thumb, "border.width") == 1
            assert ThemeState._contrast(theme.background, theme.foreground) >= 3
            assert ThemeState._contrast(theme.background, theme.progressTrack) >= 3
        assert player.playing == playing
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            assert window.grabWindow().save(str(output_dir / f"{label}-{'on' if expected else 'off'}.png"))
    verify(False)
    point = track.mapToScene(QPointF(track.width() / 2, track.height() / 2)).toPoint()
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point)
    QTest.qWait(20)
    verify(True)
    window.requestActivate()
    control.forceActiveFocus()
    QTest.keyClick(window, Qt.Key.Key_Backtab)
    for _ in range(40):
        QTest.keyClick(window, Qt.Key.Key_Tab)
        QTest.qWait(10)
        if window.activeFocusItem() == control:
            break
    QTest.qWait(20)
    assert control.hasActiveFocus() and control.property("visualFocus"), "Tab must focus Autoplay visibly"
    assert QQmlProperty.read(track, "border.width") == 2
    QTest.keyClick(window, Qt.Key.Key_Space)
    QTest.qWait(20)
    verify(False)
    # The declarative binding must still follow controller changes after user input.
    player.toggleAutoplay()
    QTest.qWait(20)
    verify(True)
    if player.autoplay != previous:
        player.toggleAutoplay()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    options = parser.parse_args()
    original, passed = app.load_window, []

    def load(*args, **kwargs):
        engine = original(*args, **kwargs)
        window = engine.rootObjects()[0]
        shell, player, view, browse, downloads, lyrics = args[0], args[2], args[3], args[5], args[6], args[10]

        def settle():
            QTest.qWait(80)

        def find(name):
            return window.findChild(QObject, name)

        def verify():
            try:
                window.requestActivate()
                # Different colors make a retained tiny thumbnail distinguishable from the original.
                for size, color in ((60, "#dd3344"), (1200, "#3355dd")):
                    image = QImage(size, size, QImage.Format.Format_RGB32)
                    image.fill(QColor(color))
                    assert image.save(str(Path(folder) / (str(size) + ".png")))
                track = {**player.currentTrack, "title": "A sharp immersive cover", "videoId": "stage000001", "duration": 180, "artists": [{"name": "Fixture artist", "id": "UCfixture"}], "album": {"name": "Fixture album", "id": "MPREfixture"}}
                player.playTracks([track] * 3, source_label="Fixture album")
                key = track.get("videoId", track.get("id"))
                downloads._artwork[key] = (Path(folder) / "60.png").as_uri()
                downloads._large_artwork[key] = {"url": (Path(folder) / "1200.png").as_uri(), "width": 1200, "height": 1200}
                downloads.changed.emit()
                before = (player.currentTrack, player.position, player.playing)
                browse_page = find("browsePane")
                browsing = find("browseSections")
                queue_pane, lyrics_pane, transport = find("queuePane"), find("lyricsPane"), find("playerBar")
                toggle = find("immersiveToggle")
                for size in ((1600, 900), (1280, 820), (920, 620)):
                    window.resize(*size)
                    for queue_open, lyrics_open in ((False, False), (True, False), (False, True), (True, True)):
                        shell.setQueueOpen(queue_open)
                        shell.setLyricsOpen(lyrics_open)
                        settle()
                        browsing.setProperty("contentY", 100)
                        browsing.forceActiveFocus()
                        old_scroll = browsing.property("contentY")
                        old_focus = window.activeFocusItem()
                        old_width = find("browseLoader").width()
                        QTest.keyClick(window, Qt.Key.Key_F)
                        settle()
                        assert shell.expanded and window.visibility() != window.Visibility.FullScreen
                        stage, cover = find("expandedPlayer"), find("immersiveArtwork")
                        assert stage and stage.isVisible() and stage.width() >= 320
                        assert not find("navigationRail").isVisible() and not find("mainHeader").isVisible()
                        assert find("browsePane") == browse_page and not browse_page.isVisible()
                        assert find("browseLoader").width() == old_width
                        assert browsing.property("contentY") == old_scroll
                        assert find("queuePane") == queue_pane and find("lyricsPane") == lyrics_pane
                        assert find("playerBar") == transport and transport.isVisible()
                        tabbed = queue_open and lyrics_open and size[0] < 1040
                        assert bool(find("queueSidebar").isVisible()) == (queue_open and (not tabbed or shell.activeDock == "Queue"))
                        lyric_visible = lyrics_open and (not tabbed or shell.activeDock == "Lyrics")
                        assert bool(find("lyricsSidebar").isVisible()) == lyric_visible
                        assert lyrics._active == lyric_visible
                        assert 80 <= cover.width() <= stage.width() - 48
                        point = cover.mapToItem(stage, QPointF())
                        assert point.y() >= 0 and point.y() + cover.height() <= stage.height()
                        art = cover.findChild(QObject, "coverArtwork")
                        deadline = time.monotonic() + 2
                        while not cover.property("ready") and time.monotonic() < deadline:
                            QTest.qWait(10)
                        assert cover.property("ready"), art.property("source").toString()
                        assert art.property("source").toString().endswith("1200.png")
                        assert art.property("sourceSize").width() == math.ceil(cover.width() * window.devicePixelRatio())
                        assert (player.currentTrack, player.position, player.playing) == before
                        QTest.keyClick(window, Qt.Key.Key_Escape)
                        settle()
                        assert not shell.expanded and browse_page.isVisible()
                        assert window.activeFocusItem() == old_focus, (size, queue_open, lyrics_open)
                        assert browsing.property("contentY") == old_scroll
                    QMetaObject.invokeMethod(toggle, "clicked")
                    settle()
                    deadline = time.monotonic() + 2
                    while not find("immersiveArtwork").property("ready") and time.monotonic() < deadline:
                        QTest.qWait(10)
                    assert find("immersiveArtwork").property("ready")
                    QTest.qWait(50)
                    cover = find("immersiveArtwork")
                    pixel_point = cover.mapToScene(QPointF(cover.width()/2, cover.height()/2)) * window.devicePixelRatio()
                    deadline = time.monotonic() + 2
                    while True:
                        pixel = window.grabWindow().pixelColor(pixel_point.toPoint())
                        if pixel.blue() > 180 and pixel.red() < 80 or time.monotonic() >= deadline:
                            break
                        QTest.qWait(20)
                    assert pixel.blue() > 180 and pixel.red() < 80, (size, pixel.name(), cover.property("ready"), cover.property("physicalSize"), pixel_point)
                    if options.output_dir:
                        options.output_dir.mkdir(parents=True, exist_ok=True)
                        assert window.grabWindow().save(str(options.output_dir / ("immersive-" + str(size[0]) + ".png")))
                    QMetaObject.invokeMethod(toggle, "clicked")
                    settle()
                shell.setQueueOpen(False)
                shell.setLyricsOpen(False)
                shell.setExpanded(True)
                settle()
                # Bottom controls toggle the same panels without leaving the stage.
                QMetaObject.invokeMethod(find("queueToggle"), "clicked")
                QMetaObject.invokeMethod(find("lyricsToggle"), "clicked")
                settle()
                assert shell.expanded and shell.queueOpen and shell.lyricsOpen
                window.resize(1600, 900)
                settle()
                shell.setLyricsOpen(False)
                shell.setQueueWidth(280)
                theme = args[11]
                for scale in (80, 100, 150):
                    shell.setUiScale(scale)
                    window.resize(920, 620)
                    palettes = [preset["id"] for preset in PRESETS] if scale == 100 else ["classic-dark", "classic-light"]
                    for palette in palettes:
                        theme.selectTheme(palette)
                        settle()
                        assert abs(find("queuePane").width() - 280) < 0.1
                        check_autoplay(window, player, theme, options.output_dir, f"autoplay-{scale}-{palette}")
                theme.selectTheme("classic-dark")
                shell.setUiScale(100)
                window.resize(1600, 900)
                shell.setLyricsOpen(True)
                settle()
                lyrics.seekLine(1)
                assert player.position == 5 and lyrics.currentLine == 1
                shell.setLyricsOpen(False)
                settle()
                check_queue(window, shell, player, browse, downloads, None, True)
                assert shell.expanded
                # Old downloaded metadata retains readable artist/album fallback strings.
                legacy = {**track, "videoId": "stage000002", "artists": [], "artist": "Legacy artist", "album": "Legacy album", "thumbnail": "", "largeThumbnail": ""}
                player.playTracks([legacy])
                settle()
                artist = next(item for item in visual_items(window.contentItem()) if item.objectName() == "immersiveArtist-0")
                assert artist.property("text") == "Legacy artist"
                assert find("immersiveAlbum").property("text") == "Legacy album"
                assert not find("immersiveAlbum").isEnabled()
                canvas = find("immersiveArtwork").findChild(QObject, "coverCanvas")
                assert canvas.property("canvasSource") == ""
                # Collaborators share one centered line instead of stacking.
                duet = {**track, "videoId": "stage000003", "artists": [{"name": "Gotts Street Park", "id": "UCfirst"}, {"name": "Olive Jones", "id": "UCsecond"}]}
                player.playTracks([duet])
                settle()
                names = {item.objectName(): item for item in visual_items(window.contentItem()) if item.objectName().startswith("immersiveArtist-")}
                first, second = names["immersiveArtist-0"], names["immersiveArtist-1"]
                first_rect, second_rect = (item.mapRectToScene(item.boundingRect()) for item in (first, second))
                assert abs(first_rect.top() - second_rect.top()) < 0.5 and second_rect.left() > first_rect.right()
                if options.output_dir:
                    assert window.grabWindow().save(str(options.output_dir / "immersive-artists.png"))
                player.playTracks([track])
                settle()
                # Song options do not replay the track; artist and album links exit into browsing.
                before = (player.currentTrack, player.position, player.playing)
                QMetaObject.invokeMethod(find("immersiveTrackTitle"), "clicked")
                settle()
                assert find("mediaMenu").property("opened")
                QMetaObject.invokeMethod(find("mediaMenu"), "close")
                assert (player.currentTrack, player.position, player.playing) == before
                album = find("immersiveAlbum")
                QMetaObject.invokeMethod(album, "clicked")
                settle()
                assert not shell.expanded and view.route == "album"
                shell.setExpanded(True)
                settle()
                artist = next(item for item in visual_items(window.contentItem()) if item.objectName() == "immersiveArtist-0")
                QMetaObject.invokeMethod(artist, "clicked")
                settle()
                assert not shell.expanded and view.route == "artist"
                shell.setExpanded(True)
                settle()
                QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
                settle()
                field = find("searchField")
                assert not shell.expanded and field.hasActiveFocus() and field.isVisible()
                state = (player.playing, player.position, player.repeat, player.shuffled, shell.volume, shell.expanded)
                for key in (Qt.Key.Key_Space, Qt.Key.Key_F, Qt.Key.Key_M, Qt.Key.Key_R, Qt.Key.Key_S, Qt.Key.Key_Minus):
                    QTest.keyClick(window, key)
                assert (player.playing, player.position, player.repeat, player.shuffled, shell.volume, shell.expanded) == state
                assert not engine.property("qmlWarnings"), engine.property("qmlWarnings")
                passed.append(True)
            except Exception:
                traceback.print_exc()
            finally:
                window.close()
                QGuiApplication.instance().exit(0 if passed else 1)

        QTimer.singleShot(250, verify)
        QTimer.singleShot(25000, window.close)
        return engine

    app.load_window = load
    with tempfile.TemporaryDirectory(prefix="youtube-music-player-") as folder:
        result = app.main(["--fixture", "--data-dir", folder])
    app.load_window = original
    assert result == 0 and passed
    print("Immersive artwork, shared docks, browse/scroll/focus preservation and shortcut isolation passed.")


if __name__ == "__main__":
    main()
