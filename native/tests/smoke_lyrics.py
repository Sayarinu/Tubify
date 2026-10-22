"""Exercise readable lyric timing, follow controls and input in a real QML scene."""

import argparse
from pathlib import Path
import tempfile
import time

from PySide6.QtCore import QObject, QPoint, QPointF, QMetaObject, QUrl, Qt, Signal
from PySide6.QtGui import QAccessible, QColor, QGuiApplication, QInputDevice, QPointingDevice, QShortcut, QKeySequence, QWheelEvent
from PySide6.QtQml import QQmlProperty
from PySide6.QtQuick import QQuickView
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

from youtube_music_native.lyric_view import LyricView
from youtube_music_native.theme import ThemeState


class Player(QObject):
    changed = Signal()
    positionChanged = Signal()
    seeked = Signal(float)
    currentTrack = {"videoId": "fixture0001"}
    position = 0.

    def seek(self, position):
        self.tick(position)
        self.seeked.emit(position)

    def tick(self, position):
        self.position = position
        self.positionChanged.emit()


class Account(QObject):
    sessionChanged = Signal()


def visual_items(item):
    yield item
    for child in item.childItems():
        yield from visual_items(child)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    options = parser.parse_args()
    QQuickStyle.setStyle("Basic")
    app = QGuiApplication.instance() or QGuiApplication([])
    with tempfile.TemporaryDirectory(prefix="youtube-music-lyrics-") as folder:
        theme = ThemeState(Path(folder) / "settings.ini")
        player, account = Player(), Account()
        lyrics = LyricView(account, player, folder, fixture=True)
        lyrics.setActive(True)
        original = [{"text": f"Original line {index}: a quiet moment in the evening", "start": index * 5.25, "end": (index + 1) * 5.25} for index in range(40)]
        lyrics._data.update(lines=original, source="Original test fixture", cached=True)
        lyrics._accept()
        window = QQuickView()
        window.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
        window.resize(280, 640)
        window.setColor(QColor(theme.background))
        warnings = []
        window.engine().warnings.connect(lambda values: warnings.extend(value.toString() for value in values))
        context = window.rootContext()
        context.setContextProperty("themeState", theme)
        context.setContextProperty("lyricState", lyrics)
        context.setContextProperty("playerState", player)
        source = Path(__file__).parents[1] / "src/youtube_music_native/qml/LyricsPane.qml"
        window.setSource(QUrl.fromLocalFile(str(source)))
        assert window.status() == QQuickView.Status.Ready, warnings
        playback_shortcuts = []
        space_shortcut = QShortcut(QKeySequence("Space"), window)
        space_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        space_shortcut.activated.connect(lambda: playback_shortcuts.append(True))
        window.show()
        window.requestActivate()
        QTest.qWait(120)
        pane = window.rootObject()
        lines = pane.findChild(QObject, "lyricLines")
        timer = pane.findChild(QObject, "lyricResumeTimer")
        follow = pane.findChild(QObject, "followLyrics")
        bar = pane.findChild(QObject, "lyricScrollBar")
        assert pane.objectName() == "lyricsPane" and lines and timer and follow and bar
        assert timer.property("interval") == 6000

        def item(name):
            return next(node for node in visual_items(pane) if node.objectName() == name)

        def centered(index):
            QTest.qWait(80)
            row = item(f"lyricLine-{index}")
            center = row.mapToItem(lines, QPointF(row.width() / 2, row.height() / 2))
            assert abs(center.y() - lines.height() / 2) < 2, (index, center.y(), lines.height())

        def click(control):
            point = control.mapToScene(QPointF(control.width() / 2, control.height() / 2)).toPoint()
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point)
            QTest.qWait(80)

        def wheel(*, touchpad=False):
            point = QPointF(120, 200)
            device = QPointingDevice("Fixture touchpad", 42, QInputDevice.DeviceType.TouchPad,
                                     QPointingDevice.PointerType.Finger, QInputDevice.Capability.Position | QInputDevice.Capability.Scroll,
                                     1, 0) if touchpad else QPointingDevice.primaryPointingDevice()
            phases = (Qt.ScrollPhase.ScrollBegin, Qt.ScrollPhase.ScrollUpdate, Qt.ScrollPhase.ScrollEnd) if touchpad else (Qt.ScrollPhase.NoScrollPhase,)
            for phase in phases:
                scrolling = phase in (Qt.ScrollPhase.ScrollUpdate, Qt.ScrollPhase.NoScrollPhase)
                event = QWheelEvent(point, point, QPoint(0, -80) if touchpad and scrolling else QPoint(),
                                    QPoint(0, -120) if scrolling else QPoint(), Qt.MouseButton.NoButton,
                                    Qt.KeyboardModifier.NoModifier, phase, False,
                                    Qt.MouseEventSource.MouseEventNotSynthesized, device)
                app.sendEvent(window, event)
                QTest.qWait(30)
            QTest.qWait(120)

        # The first and final lines center too; active text and unsynced text use the primary color.
        centered(0)
        assert QQmlProperty(item("lyricText-0"), "font.pixelSize").read() == 20
        assert item("lyricText-0").property("color").name().upper() == theme.foreground
        assert item("lyricText-1").property("color").name().upper() == theme.secondary
        assert "Saved lyrics" in pane.findChild(QObject, "lyricSource").property("text")
        player.seek(original[-1]["start"])
        centered(39)
        player.seek(original[12]["start"])
        centered(12)
        window.resize(720, 560)
        centered(12)
        assert QQmlProperty(item("lyricText-12"), "font.pixelSize").read() == 24
        window.resize(280, 640)
        centered(12)

        if options.output_dir:
            options.output_dir.mkdir(parents=True, exist_ok=True)
            for theme_id in ("classic-dark", "classic-light", "youtube-music-purple"):
                theme.selectTheme(theme_id)
                window.setColor(QColor(theme.background))
                QTest.qWait(80)
                assert window.grabWindow().save(str(options.output_dir / f"{theme_id}-280.png"))
            theme.selectTheme("classic-dark")
            window.setColor(QColor(theme.background))

        # Scroll wheel and pixel-based trackpad events both scroll and pause following.
        for touchpad in (False, True):
            before = lines.property("contentY")
            wheel(touchpad=touchpad)
            assert not pane.property("following") and follow.isVisible()
            assert lines.property("contentY") != before, "Manual scrolling was swallowed"
            held = lines.property("contentY")
            player.tick(original[20]["start"])
            QTest.qWait(80)
            assert abs(lines.property("contentY") - held) < 1, "Playback interrupted manual scrolling"
            click(follow)
            assert pane.property("following")
            centered(20)
            player.seek(original[12]["start"])
            centered(12)

        # Keyboard scrolling pauses; explicit seek restores following even inside the same line.
        lines.forceActiveFocus()
        QTest.keyClick(window, Qt.Key.Key_PageDown)
        QTest.qWait(80)
        assert not pane.property("following")
        player.seek(original[12]["start"] + 0.5)
        centered(12)
        assert pane.property("following")
        lines.forceActiveFocus()
        QTest.keyClick(window, Qt.Key.Key_Tab)
        QTest.qWait(80)
        assert window.activeFocusItem().objectName().startswith("lyricLine-")
        assert not pane.property("following"), "Tab navigation should keep its focused line in view"
        player.seek(original[12]["start"])
        centered(12)
        row = item("lyricLine-12")
        accessible = QAccessible.queryAccessibleInterface(row)
        assert accessible.role() == QAccessible.Role.Button
        assert accessible.text(QAccessible.Text.Description) == "Seek to 1:03"
        pane.forceActiveFocus()
        QTest.keyClick(window, Qt.Key.Key_Space)
        assert playback_shortcuts == [True], "Playback shortcut fixture did not activate"
        row.forceActiveFocus()
        player.tick(original[12]["start"] + 1)
        QTest.keyClick(window, Qt.Key.Key_Return)
        assert player.position == 63.0, player.position
        player.tick(original[12]["start"] + 1)
        QTest.keyClick(window, Qt.Key.Key_Space)
        assert player.position == 63.0
        assert playback_shortcuts == [True], "Lyric activation leaked to the playback shortcut"
        click(item("lyricLine-13"))
        assert player.position == 68.25, player.position
        centered(13)

        # Dragging the list and grabbing its scrollbar both pause following.
        start, end = QPoint(120, 250), QPoint(120, 100)
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(window, QPoint(120, 220), delay=30)
        QTest.mouseMove(window, end, delay=30)
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=end)
        QTest.qWait(150)
        assert not pane.property("following")
        click(follow)
        position = bar.property("visualPosition") + bar.property("visualSize") / 2
        thumb = bar.mapToScene(QPointF(bar.width() / 2, position * bar.height())).toPoint()
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=thumb)
        QTest.mouseMove(window, thumb + QPoint(0, 60), delay=30)
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=thumb + QPoint(0, 60))
        QTest.qWait(80)
        assert not pane.property("following")
        # Wait the actual six-second interval; no line change is required to resume and center.
        QTest.qWait(5500)
        assert not pane.property("following"), "Follow resumed before the six-second pause"
        deadline = time.monotonic() + 2
        while not pane.property("following") and time.monotonic() < deadline:
            QTest.qWait(20)
        assert pane.property("following"), "Follow did not resume after the scroll pause"
        centered(13)

        # Reopening centers the active line after manually scrolling away.
        lines.forceActiveFocus()
        QTest.keyClick(window, Qt.Key.Key_Home)
        assert not pane.property("following")
        pane.setVisible(False)
        pane.setVisible(True)
        centered(13)
        assert pane.property("following")

        lyrics._data.update(timed=False, lines=[{"text": "Plain original lyrics at a comfortable size", "start": -1., "end": -1.}])
        lyrics._accept()
        QTest.qWait(100)
        plain = item("lyricLine-0")
        assert item("lyricText-0").property("color").name().upper() == theme.foreground
        assert QAccessible.queryAccessibleInterface(plain).role() == QAccessible.Role.StaticText
        assert not follow.isVisible() and "Unsynced lyrics" in pane.findChild(QObject, "lyricSource").property("text")
        old_position = player.position
        click(plain)
        assert player.position == old_position
        lyrics._error = "Could not refresh while offline."
        lyrics.changed.emit()
        QTest.qWait(80)
        assert lines.isVisible() and pane.findChild(QObject, "lyricRefreshStatus").isVisible()
        lyrics._data = {"available": False, "lines": []}
        lyrics.changed.emit()
        QTest.qWait(80)
        assert not lines.isVisible() and pane.findChild(QObject, "lyricEmptyState").isVisible()
        assert not warnings, warnings
        window.close()
        lyrics.close()
    print("Lyric readability, accessible seeking and six-second manual follow controls passed.")


if __name__ == "__main__":
    main()
