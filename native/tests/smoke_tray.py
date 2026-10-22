"""Render the tray player and dispatch controls using a synthetic native tray."""
import tempfile
import traceback

from PySide6.QtCore import QObject, QMetaObject, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from youtube_music_native import app
from youtube_music_native.tray import TrayPlayer
from test_tray import FakeTray, FakeMenu


def main():
    original, original_tray, passed = app.load_window, app.TrayPlayer, []
    app.TrayPlayer = lambda *args, **kwargs: TrayPlayer(*args, **kwargs, tray_factory=FakeTray, menu_factory=FakeMenu)

    def load(*args, **kwargs):
        engine = original(*args, **kwargs)
        window = engine.rootObjects()[0]
        shell, player = args[0], args[2]
        def verify():
            try:
                service = shell.trayState
                assert service.popup is None and not service.enabled
                service.setEnabled(True)
                QTest.qWait(80)
                popup = service.popup
                assert popup and not popup.isVisible() and service.active
                service.setPinned(True)
                service.showPlayer()
                QTest.qWait(80)
                assert popup.isVisible() and window.isVisible()
                before = player.playing
                QMetaObject.invokeMethod(popup.findChild(QObject, "trayPlayPause"), "clicked")
                assert player.playing != before
                seek = popup.findChild(QObject, "traySeek")
                seek.setProperty("value", 0.25)
                QMetaObject.invokeMethod(seek, "moved")
                assert player.position == player.duration * 0.25
                volume = popup.findChild(QObject, "trayVolume")
                volume.setProperty("value", 30)
                QMetaObject.invokeMethod(volume, "moved")
                assert shell.volume == 30
                results = []
                args[8].applied.connect(results.append)
                QMetaObject.invokeMethod(popup.findChild(QObject, "trayLike"), "clicked")
                assert results[-1]["action"] == "song_rating"
                popup.setPosition(20, 20)
                service.settings.setValue("trayX", 200)
                QMetaObject.invokeMethod(popup.findChild(QObject, "trayQueueToggle"), "clicked")
                QTest.qWait(80)
                assert service.queueOpen and popup.findChild(QObject, "queueUpcomingList")
                assert popup.height() > 292 and popup.x() == 20
                service.settings.setValue("trayX", 99999)
                service.settings.setValue("trayY", 99999)
                popup.hide()
                service.positionPopup()
                service.showPlayer()
                areas = [screen.availableGeometry() for screen in QGuiApplication.screens()]
                assert any(area.contains(popup.geometry()) for area in areas)
                popup.close()
                QTest.qWait(30)
                assert not popup.isVisible() and window.isVisible()
                service.setEnabled(False)
                QTest.qWait(30)
                assert service.popup is None and not service.active
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
    with tempfile.TemporaryDirectory(prefix="youtube-music-tray-") as folder:
        result = app.main(["--fixture", "--data-dir", folder])
    app.load_window, app.TrayPlayer = original, original_tray
    assert result == 0 and passed
    print("Tray transport, ratings, seek, volume, queue, pin and safe close passed.")


if __name__ == "__main__":
    main()
