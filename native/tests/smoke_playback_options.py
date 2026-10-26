"""Check real playback settings controls, seek hover and existing save commands."""
import tempfile
import traceback

from PySide6.QtCore import QObject, QMetaObject, QPointF, QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from youtube_music_native import app


def visual(item, name):
    if item.objectName() == name:
        return item
    for child in item.childItems():
        found = visual(child, name)
        if found:
            return found


def main():
    original, passed = app.load_window, []

    def load(*args, **kwargs):
        engine = original(*args, **kwargs)
        window = engine.rootObjects()[0]
        shell, player, library = args[0], args[2], args[9]

        def verify():
            try:
                options = shell.playbackOptions
                dialog = window.findChild(QObject, "playbackSettings")
                QMetaObject.invokeMethod(dialog, "open")
                QTest.qWait(80)
                preset = visual(window.contentItem(), "sleepPreset-10")
                assert preset and preset.isVisible()
                QMetaObject.invokeMethod(preset, "clicked")
                assert options.sleepRemaining == 600
                cancel = window.findChild(QObject, "cancelSleep")
                QMetaObject.invokeMethod(cancel, "clicked")
                assert not options.sleepRemaining and not options.timer.isActive()
                toggle = window.findChild(QObject, "nonlinearVolumeOption")
                point = toggle.mapToScene(QPointF(toggle.width()/2, toggle.height()/2)).toPoint()
                QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point)
                assert options.nonlinearVolume
                fill = window.findChild(QObject, "speakerFillOption")
                assert not fill.property("enabled") and not options.speakerFill
                player._audio_options_changed({"available": True, "active": False, "message": "Synthetic 5.1 output"})
                assert fill.property("enabled")
                original_size = (window.width(), window.height())
                window.setWidth(920)
                window.setHeight(620)
                shell.setUiScale(150)
                QTest.qWait(80)
                fill.forceActiveFocus()
                QTest.qWait(80)
                QTest.keyClick(window, Qt.Key.Key_Space)
                assert options.speakerFill
                center = fill.mapToScene(QPointF(fill.width()/2, fill.height()/2))
                assert 0 < center.y() < window.height()
                player._audio_options_changed({"available": False, "active": False, "failed": True, "message": "Synthetic failure"})
                assert fill.property("enabled")  # A saved preference can always be turned off.
                QTest.keyClick(window, Qt.Key.Key_Space)
                assert not options.speakerFill
                QMetaObject.invokeMethod(dialog, "close")
                shell.setUiScale(100)
                window.setWidth(original_size[0])
                window.setHeight(original_size[1])
                QTest.qWait(80)
                seek = window.findChild(QObject, "playbackSeek")
                point = seek.mapToScene(QPointF(seek.width()/2, seek.height()/2)).toPoint()
                QTest.mouseMove(window, point, delay=20)
                QTest.qWait(220)
                preview = window.findChild(QObject, "seekPreview")
                assert preview.property("visible")
                assert preview.property("text") == f"{int(player.duration/2)//60}:{int(player.duration/2)%60:02}"
                applied = []
                args[8].applied.connect(applied.append)
                shell.showMenu(player.currentTrack, {})
                QTest.qWait(50)
                menu = window.findChild(QObject, "mediaMenu")
                save = next(item for item in menu.findChildren(QObject) if item.property("text") == "Save to Library")
                QMetaObject.invokeMethod(save, "triggered")
                assert any(result["action"] == "song_library" for result in applied)
                chosen = []
                library.chooserRequested.connect(chosen.append)
                playlist = next(item for item in menu.findChildren(QObject) if item.property("text") == "Add to Playlist")
                QMetaObject.invokeMethod(playlist, "triggered")
                assert chosen and (chosen[0].get("videoId") or chosen[0].get("id")) == (player.currentTrack.get("videoId") or player.currentTrack.get("id"))
                assert not engine.property("qmlWarnings"), engine.property("qmlWarnings")
                passed.append(True)
            except Exception:
                traceback.print_exc()
            finally:
                window.close()
                QGuiApplication.instance().exit(0 if passed else 1)
        QTimer.singleShot(200, verify)
        return engine

    app.load_window = load
    with tempfile.TemporaryDirectory(prefix="youtube-music-playback-options-") as folder:
        result = app.main(["--fixture", "--data-dir", folder])
    app.load_window = original
    assert result == 0 and passed
    print("Playback preferences, sleep controls, seek previews and save actions passed.")


if __name__ == "__main__":
    main()
