"""Exercise the single settings dialog with synthetic state and real keyboard input."""
import argparse
from pathlib import Path
import tempfile
import traceback

from PySide6.QtCore import QObject, QMetaObject, QPointF, QTimer, Qt
from PySide6.QtGui import QAccessible, QGuiApplication
from PySide6.QtTest import QTest

from youtube_music_native import app
from smoke_visual import visual_items


PAGES = {
    "appearanceSettingsDialog": "Appearance", "playbackSettings": "Playback",
    "lyricsSettingsDialog": "Lyrics", "desktopSettings": "Desktop",
    "shortcutSettings": "Global Shortcuts", "discordSettingsDialog": "Discord Presence",
    "lastFmSettingsDialog": "Last.fm", "apiSettings": "Local API",
    "obsSettings": "OBS Now Playing", "maintenanceSettings": "Updates & Troubleshooting",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    options = parser.parse_args()
    original, passed = app.load_window, []

    def load(*args, **kwargs):
        engine = original(*args, **kwargs)
        window, shell, player, theme = engine.rootObjects()[0], args[0], args[2], args[11]

        def find(name):
            result = window.findChild(QObject, name) or next((item for item in visual_items(window.contentItem()) if item.objectName() == name), None)
            assert result, name
            return result

        def shot(name):
            if options.output_dir:
                options.output_dir.mkdir(parents=True, exist_ok=True)
                assert window.grabWindow().save(str(options.output_dir / (name + ".png")))

        def click(item):
            item.forceActiveFocus()
            QTest.qWait(25)
            point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point)
            QTest.qWait(25)

        def verify():
            try:
                theme.selectTheme("dracula")
                dialog, appearance = find("settingsDialog"), find("appearanceSettingsDialog")
                before = (player.playing, player.position, player.currentTrack)
                for scale, size in ((100, (1600, 900)), (100, (1280, 820)), (80, (920, 620)), (150, (920, 620))):
                    shell.setUiScale(scale)
                    window.resize(*size)
                    QTest.qWait(40)
                    click(find("settingsButton"))
                    assert dialog.property("opened") and window.property("modalOpen")
                    assert window.findChild(QObject, "appearanceMenu") is None
                    for name, title in PAGES.items():
                        page, nav = find(name), find("settingsNav-" + name)
                        click(nav)
                        assert nav.property("checked") and page.property("opened"), (name, scale, nav.property("checked"), page.property("opened"))
                        assert page.property("title") == nav.property("text") == title
                        assert sum(find(key).property("opened") for key in PAGES) == 1
                        assert sum(find("settingsNav-" + key).property("checked") for key in PAGES) == 1
                        for item in (nav, page.property("contentItem")):
                            bounds = item.mapRectToScene(item.boundingRect())
                            assert bounds.left() >= -1 and bounds.right() <= size[0] + 1, (name, scale, bounds)
                            assert bounds.top() >= -1 and bounds.bottom() <= size[1] + 1, (name, scale, bounds)
                        assert (player.playing, player.position, player.currentTrack) == before
                        shot(f"{name}-{scale}-{size[0]}")
                    QTest.keyClick(window, Qt.Key.Key_Escape)
                    QTest.qWait(30)
                    assert not dialog.property("opened") and not window.property("modalOpen")
                    assert window.activeFocusItem() == find("settingsButton")

                # Content ordering and real keyboard interaction in the appearance page.
                shell.setUiScale(100)
                window.resize(1280, 820)
                QMetaObject.invokeMethod(appearance, "open")
                QTest.qWait(40)
                card = find("themeCard-classic-dark")
                card.forceActiveFocus()
                QTest.keyClick(window, Qt.Key.Key_Space)
                QTest.qWait(30)
                assert theme.activeThemeId == "classic-dark"
                theme.selectTheme("dracula")
                light = find("lightThemeGrid")
                control = find("reducedMotionControl")
                assert light.mapToScene(QPointF(0, light.height())).y() < control.mapToScene(QPointF(0, 0)).y()
                changes = []
                shell.appearanceChanged.connect(lambda: changes.append(True))
                control.forceActiveFocus()
                QTest.qWait(30)
                original_motion = shell.reducedMotion
                accessible = QAccessible.queryAccessibleInterface(control)
                assert accessible and accessible.state().checkable
                QTest.keyClick(window, Qt.Key.Key_Space)
                QTest.qWait(30)
                assert shell.reducedMotion != original_motion and len(changes) == 1
                assert accessible.state().checked == shell.reducedMotion
                indicator = control.property("indicator")
                assert indicator.property("radius") == indicator.height() / 2
                assert player.playing == before[0]
                shot("appearance-options")

                # Sensitive draft fields must be cleared on category changes and dialog close.
                QMetaObject.invokeMethod(find("lyricsSettingsDialog"), "open")
                find("lyricApiKey").setProperty("text", "synthetic-unsaved-key")
                QMetaObject.invokeMethod(find("lastFmSettingsDialog"), "open")
                assert find("lyricApiKey").property("text") == ""
                find("lastFmApiKey").setProperty("text", "synthetic-unsaved-key")
                find("lastFmSecret").setProperty("text", "synthetic-unsaved-secret")
                QMetaObject.invokeMethod(dialog, "close")
                QTest.qWait(30)
                assert find("lastFmApiKey").property("text") == find("lastFmSecret").property("text") == ""

                # Tab navigation is contained in the modal, including both navigation and content.
                QMetaObject.invokeMethod(find("discordSettingsDialog"), "open")
                QTest.qWait(30)
                for _ in range(28):
                    QTest.keyClick(window, Qt.Key.Key_Tab)
                    QTest.qWait(10)
                    ancestor = window.activeFocusItem()
                    panel = dialog.property("contentItem")
                    while ancestor and ancestor != panel:
                        ancestor = ancestor.parentItem()
                    assert ancestor == panel, "Focus escaped Settings"
                QMetaObject.invokeMethod(dialog, "close")
                assert not engine.property("qmlWarnings"), engine.property("qmlWarnings")
                passed.append(True)
            except Exception:
                traceback.print_exc()
            finally:
                window.close()
                QGuiApplication.instance().exit(0 if passed else 1)

        QTimer.singleShot(250, verify)
        return engine

    app.load_window = load
    try:
        with tempfile.TemporaryDirectory(prefix="tubify-settings-") as folder:
            result = app.main(["--fixture", "--data-dir", folder])
        assert result == 0 and passed
    finally:
        app.load_window = original
    print("Unified settings navigation, scaled pages, rounded controls, focus and draft clearing passed.")


if __name__ == "__main__":
    main()
