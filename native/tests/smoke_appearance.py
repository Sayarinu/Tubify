"""Exercise content zoom independently of platform DPI in the rendered Qt scene."""

import argparse
from pathlib import Path
import tempfile
import traceback

from PySide6.QtCore import QObject, QMetaObject, QPointF, QTimer, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage
from PySide6.QtTest import QSignalSpy, QTest

from youtube_music_native import app
from youtube_music_native.shell import ShellController


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    options = parser.parse_args()
    original, passed = app.load_window, []

    def load(*args, **kwargs):
        engine = original(*args, **kwargs)
        window = engine.rootObjects()[0]
        shell, player, browse, theme = args[0], args[2], args[5], args[11]

        def find(name):
            item = window.findChild(QObject, name)
            assert item, name
            return item

        def settle(condition):
            for _ in range(100):
                if condition():
                    return
                QTest.qWait(10)
            assert condition()

        def open_rendered(popup):
            # Popup pages are laid out while the next frame is prepared, so measure them only after a frame has been rendered.
            frames = QSignalSpy(window.frameSwapped)
            QMetaObject.invokeMethod(popup, "open")
            settle(lambda: popup.property("opened") and frames.count() > 0)

        def shot(name):
            if options.output_dir:
                options.output_dir.mkdir(parents=True, exist_ok=True)
                assert window.grabWindow().save(str(options.output_dir / (name + ".png")))

        def verify():
            try:
                root, content, queue, lyrics, bar = (find(name) for name in ("scaledContent", "pageContent", "queueSidebar", "lyricsSidebar", "playerBar"))
                settings = find("appearanceSettingsDialog")
                initial = (player.position, player.playing, player.currentTrack)
                dpr = window.devicePixelRatio()
                # The layout matrix toggles the expanded player 36 times; slides would push it past the 25 s watchdog
                # (which hides the window), so it runs without motion and the slide is checked separately below.
                motion = shell.reducedMotion
                shell.setReducedMotion(True)
                for scale in (80, 100, 150):
                    shell.setUiScale(scale)
                    factor = scale / 100
                    for size in ((1600, 900), (1280, 820), (920, 620)):
                        window.resize(*size)
                        for queue_open, lyrics_open in ((False, False), (True, False), (False, True), (True, True)):
                            shell.setQueueOpen(queue_open)
                            shell.setLyricsOpen(lyrics_open)
                            QTest.qWait(35)
                            assert abs(root.width() * factor - size[0]) < 0.1
                            assert abs(root.height() * factor - size[1]) < 0.1
                            assert window.devicePixelRatio() == dpr
                            assert bar.isVisible()
                            bounds = bar.mapRectToScene(bar.boundingRect())
                            assert bounds.left() >= 0 and bounds.right() <= size[0] + 0.1
                            assert bounds.bottom() <= size[1] and bounds.height() > 0
                            assert content.width() >= (480 if queue.isVisible() and lyrics.isVisible() else 320) - 0.1
                            if queue.isVisible():
                                assert queue.width() >= 280
                            if lyrics.isVisible():
                                assert lyrics.width() >= 280
                            shell.setExpanded(True)
                            stage = find("expandedPlayer")
                            # Wait until the expanded player fills the content area.
                            settle(lambda: abs(stage.mapToScene(QPointF()).y() - content.mapToScene(QPointF()).y()) < 0.5)
                            cover = find("immersiveArtwork")
                            assert stage.isVisible() and bar.isVisible()
                            assert not find("navigationRail").isVisible()
                            cover_bounds = cover.mapRectToScene(cover.boundingRect())
                            assert cover_bounds.left() >= 0 and cover_bounds.right() <= size[0] + 1
                            assert cover_bounds.top() >= 0 and cover_bounds.bottom() <= bounds.top() + 1, (scale, size, cover_bounds)
                            assert shell.queueOpen == queue_open and shell.lyricsOpen == lyrics_open
                            shell.setExpanded(False)
                            # Wait until the closed player has unloaded.
                            settle(lambda: not window.findChild(QObject, "expandedPlayer"))
                            search, settings_button = find("searchField"), find("settingsButton")
                            assert search.x() + search.width() <= settings_button.x() + 0.1
                            for name in ("queueToggle", "lyricsToggle", "playerTransport"):
                                item = find(name)
                                rectangle = item.mapRectToScene(item.boundingRect())
                                assert rectangle.left() >= bounds.left() and rectangle.right() <= bounds.right(), name
                        shot(f"scale-{scale}-{size[0]}")
                        # The gear opens the shared dialog directly at every content scale.
                        settings_button = find("settingsButton")
                        point = settings_button.mapToScene(settings_button.boundingRect().center()).toPoint()
                        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point)
                        QTest.qWait(30)
                        menu = find("settingsDialog")
                        assert menu.property("opened")
                        menu_content = menu.property("contentItem")
                        menu_bounds = menu_content.mapRectToScene(menu_content.boundingRect())
                        assert menu_bounds.left() >= -1 and menu_bounds.right() <= size[0] + 1
                        assert menu_bounds.top() >= -1 and menu_bounds.bottom() <= size[1] + 1
                        QMetaObject.invokeMethod(menu, "close")
                        open_rendered(settings)
                        panel = menu.property("contentItem")
                        bounds = panel.mapRectToScene(panel.boundingRect())
                        assert bounds.left() >= 0 and bounds.right() <= size[0] + 1, (scale, size, bounds)
                        assert bounds.top() >= 0 and bounds.bottom() <= size[1] + 1, (scale, size, bounds)
                        assert abs(bounds.center().x() - size[0] / 2) < 1, (scale, size, bounds)
                        assert abs(bounds.center().y() - size[1] / 2) < 1, (scale, size, bounds)
                        shot(f"settings-{scale}-{size[0]}")
                        QMetaObject.invokeMethod(settings, "close")
                shell.setReducedMotion(motion)
                shell.setUiScale(150)
                window.resize(920, 620)
                for name in ("colorPickerDialog", "shortcutHelpDialog", "accountDialog", "lyricsSettingsDialog", "playbackSettings"):
                    popup = find(name)
                    open_rendered(popup)
                    panel = popup.property("contentItem")
                    rectangle = panel.mapRectToScene(panel.boundingRect())
                    assert rectangle.top() >= 0 and rectangle.bottom() <= 620, (name, rectangle)
                    if name == "colorPickerDialog":
                        # A modal owns Tab focus, and clipped controls scroll into view.
                        # The header's pipette and close buttons sit above the scrolling content.
                        dialog_item = panel.parentItem()
                        for _ in range(40):
                            QTest.keyClick(window, Qt.Key.Key_Tab)
                            QTest.qWait(10)
                            focused = window.activeFocusItem()
                            ancestor = focused
                            while ancestor and ancestor not in (panel, dialog_item):
                                ancestor = ancestor.parentItem()
                            assert ancestor in (panel, dialog_item), "Focus escaped the color picker"
                            if ancestor == panel:
                                bounds = focused.mapRectToScene(focused.boundingRect())
                                assert rectangle.top() - 1 <= bounds.top() and bounds.bottom() <= rectangle.bottom() + 1, bounds
                    if name in ("lyricsSettingsDialog", "playbackSettings"):
                        option = find("lyricApiKey" if name == "lyricsSettingsDialog" else "skipDislikedOption")
                        option.forceActiveFocus()
                        QTest.qWait(30)
                        focused_bounds = option.mapRectToScene(option.boundingRect())
                        assert focused_bounds.top() >= rectangle.top() - 1 and focused_bounds.bottom() <= rectangle.bottom() + 1, (name, focused_bounds, rectangle)
                    if name == "playbackSettings":
                        # A late text/layout update must keep an already focused option visible.
                        shell.playbackOptions._status = "Synthetic playback status that wraps across several lines. " * 5
                        shell.playbackOptions.timerChanged.emit()
                        QTest.qWait(100)
                        assert window.activeFocusItem() == option
                        focused_bounds = option.mapRectToScene(option.boundingRect())
                        rectangle = panel.mapRectToScene(panel.boundingRect())
                        assert focused_bounds.top() >= rectangle.top() - 1 and focused_bounds.bottom() <= rectangle.bottom() + 1, (name, focused_bounds, rectangle)
                        shell.playbackOptions._status = ""
                        shell.playbackOptions.timerChanged.emit()
                    shot(name + "-150-920")
                    QMetaObject.invokeMethod(popup, "close")
                QTest.qWait(30)
                toggle = find("navigationToggle")
                assert toggle.isVisible()
                toggle.forceActiveFocus()
                QTest.keyClick(window, Qt.Key.Key_Space)
                QTest.qWait(50)
                drawer = find("navigationDrawer")
                assert drawer.property("opened")
                shot("navigation-150-920")
                QTest.keyClick(window, Qt.Key.Key_Escape)
                QTest.qWait(50)
                assert not drawer.property("opened")
                assert window.activeFocusItem() == toggle
                # The expanded player slides up, reverses cleanly mid-close and unloads after sliding down.
                def stage_offset():
                    stage = window.findChild(QObject, "expandedPlayer")
                    return stage and stage.mapToScene(QPointF()).y() - content.mapToScene(QPointF()).y()
                shell.setExpanded(True)
                QTest.qWait(30)
                assert stage_offset() > 1
                settle(lambda: abs(stage_offset()) < 0.5)
                stage = find("expandedPlayer")
                expanded_area = stage.mapRectToScene(stage.boundingRect())
                shell.setExpanded(False)
                QTest.qWait(120)
                closing = find("expandedPlayer")
                assert not closing.isEnabled() and find("browseLoader").isVisible()
                # The closing pane keeps its expanded geometry while the sidebar and header return beneath it.
                closing_area = closing.mapRectToScene(closing.boundingRect())
                assert find("mainHeader").isVisible()
                assert (closing_area.x(), closing_area.width(), closing_area.height()) == (expanded_area.x(), expanded_area.width(), expanded_area.height())
                assert closing_area.y() > expanded_area.y()
                shell.setExpanded(True)
                assert find("expandedPlayer") == closing
                settle(lambda: abs(stage_offset()) < 0.5)
                assert closing.isEnabled() and window.findChild(QObject, "expandedPlayer") == closing
                shell.setExpanded(False)
                settle(lambda: not window.findChild(QObject, "expandedPlayer"))
                title = find("playerTitleText")
                title.setProperty("text", "A long synthetic title that must stay still when reduced motion is enabled")
                shell.setReducedMotion(True)
                QTest.qWait(60)
                assert title.x() == 0
                QTest.qWait(1100)
                assert title.x() == 0
                # Reduced motion opens and closes the expanded player without a slide.
                shell.setExpanded(True)
                assert stage_offset() == 0
                shell.setExpanded(False)
                assert not find("immersiveLoader").property("active")
                for preset in theme.darkThemes + theme.lightThemes:
                    theme.selectTheme(preset["id"])
                    for scale in (80, 100, 150):
                        shell.setUiScale(scale)
                        for size in ((1600, 900), (1280, 820), (920, 620)):
                            window.resize(*size)
                            QTest.qWait(10)
                            assert content.width() >= 320 - 0.1
                            assert bar.isVisible()
                theme.selectTheme("classic-dark")
                shell.setUiScale(150)
                browse.open({"kind": "album", "id": "MPREfixture", "title": "Synthetic album"})
                QTest.qWait(50)
                image = find("backdropImage")
                background = image.parentItem()
                background.setProperty("mediaKey", "")
                artwork = Path(shell.settings.fileName()).with_name("appearance-fixture.png")
                pixels = QImage(640, 240, QImage.Format.Format_RGB32)
                pixels.fill(QColor("#348b65"))
                assert pixels.save(str(artwork))
                background.setProperty("source", artwork.as_uri())
                shell.setArtworkBlur(False)
                QTest.qWait(100)
                assert not image.property("source").isEmpty() and image.isVisible()
                assert not background.property("useBlur")
                shot("artwork-background-no-blur")
                shell.setArtworkBlur(True)
                QTest.qWait(30)
                shot("artwork-background-blur")
                shell.setArtworkBackground(False)
                shell.setArtworkBlur(False)
                QTest.qWait(30)
                assert image.property("source").isEmpty() and not image.isVisible()
                shot("artwork-background-disabled")
                restored = ShellController(shell.settings.fileName())
                assert restored.uiScale == 150 and restored.reducedMotion
                assert not restored.artworkBackground and not restored.artworkBlur
                assert (player.position, player.playing, player.currentTrack) == initial
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
    with tempfile.TemporaryDirectory(prefix="youtube-music-appearance-") as folder:
        result = app.main(["--fixture", "--data-dir", folder])
    app.load_window = original
    assert result == 0 and passed
    print("Independent content scale, responsive navigation/docks, popup bounds and appearance preferences passed.")


if __name__ == "__main__":
    main()
