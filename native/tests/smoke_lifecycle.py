"""Verify desktop lifecycle controls without changing real startup settings."""
import argparse
from pathlib import Path
import tempfile
import traceback

from PySide6.QtCore import QObject, QMetaObject, QSettings, QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from youtube_music_native import app
from youtube_music_native.tray import TrayPlayer
from test_tray import FakeMenu, FakeTray
from test_lifecycle import Startup


class NativeTray(FakeTray):
    @staticmethod
    def supportsMessages():
        return True

    def showMessage(self, *args):
        self.messages.append(args)

    def __init__(self, parent):
        super().__init__(parent)
        self.messages = []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-minimized", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    options = parser.parse_args()
    original, original_tray, passed, quit_observed = app.load_window, app.TrayPlayer, [], []
    app.TrayPlayer = lambda *args, **kwargs: TrayPlayer(*args, **kwargs, tray_factory=NativeTray, menu_factory=FakeMenu)

    def load(*args, **kwargs):
        engine = original(*args, **kwargs)
        window = engine.rootObjects()[0]
        shell, player = args[0], args[2]
        def find(name):
            item = window.findChild(QObject, name)
            assert item, name
            return item
        def verify():
            try:
                application = QGuiApplication.instance()
                application.setQuitOnLastWindowClosed(False)
                life, tray = shell.lifecycleState, shell.trayState
                application.aboutToQuit.connect(lambda: quit_observed.append(life._quitting))
                assert window.isVisible()
                if options.start_minimized:
                    # xdg-shell has no minimized-state acknowledgement; Qt may report Windowed.
                    if not application.platformName().startswith("wayland"):
                        assert window.visibility() == window.Visibility.Minimized
                    window.showNormal()
                assert not life.startupAvailable
                life.startup = Startup()
                life.changed.emit()
                assert not life.closeToTray and not life.trackNotifications and not tray.enabled
                before = player.playing
                life.setStartMinimized(True)
                assert window.isVisible() and window.visibility() != window.Visibility.Minimized
                life.setCloseToTray(True)
                assert window.close()  # No tray: ordinary close is still accepted.
                assert not window.isVisible()
                window.show()
                tray.setEnabled(True)
                QTest.qWait(50)
                assert not window.close() and not window.isVisible()
                assert life.hidden_watch.isActive() and player.playing == before
                tray.setEnabled(False)
                assert window.isVisible() and not life.hidden_watch.isActive()
                tray.setEnabled(True)
                assert not window.close()
                NativeTray.supported = False
                life._check_hidden()
                assert window.isVisible() and "restored" in life.error
                NativeTray.supported = True
                tray.changed.emit()
                window.resize(920, 620)
                shell.setUiScale(150)
                dialog = find("desktopSettings")
                QMetaObject.invokeMethod(dialog, "open")
                QTest.qWait(40)
                for name in ("autostartOption", "trackNotificationsOption"):
                    control = find(name)
                    control.forceActiveFocus()
                    QTest.qWait(30)
                    panel = dialog.property("contentItem")
                    bounds = panel.mapRectToScene(panel.boundingRect())
                    control_bounds = control.mapRectToScene(control.boundingRect())
                    assert control_bounds.top() >= bounds.top() - 1 and control_bounds.bottom() <= bounds.bottom() + 1
                    QTest.keyClick(window, Qt.Key.Key_Space)
                    QTest.qWait(30)
                assert life.autostart and life.startup.enabled and life.trackNotifications
                assert player.playing == before
                if options.output_dir:
                    options.output_dir.mkdir(parents=True, exist_ok=True)
                    assert window.grabWindow().save(str(options.output_dir / "desktop-settings-150.png"))
                QMetaObject.invokeMethod(dialog, "close")
                player.playTracks([{"videoId": "synthetic", "title": "Synthetic song", "artist": "Synthetic artist", "duration": 100}])
                player.changed.emit()
                assert len(tray.tray.messages) == 1
                assert tray.tray.messages[0][:2] == ("Synthetic song", "Synthetic artist")
                life.setTrackNotifications(False)
                assert not engine.property("qmlWarnings"), engine.property("qmlWarnings")
                passed.append(True)
            except Exception:
                traceback.print_exc()
            finally:
                NativeTray.supported = True
                if passed:
                    QGuiApplication.instance().quit()
                else:
                    QGuiApplication.instance().exit(1)
        QTimer.singleShot(200, verify)
        return engine

    app.load_window = load
    with tempfile.TemporaryDirectory(prefix="youtube-music-lifecycle-") as folder:
        if options.start_minimized:
            settings = QSettings(str(Path(folder) / "settings.ini"), QSettings.Format.IniFormat)
            settings.setValue("startMinimized", True)
            settings.sync()
        result = app.main(["--fixture", "--data-dir", folder])
    app.load_window, app.TrayPlayer = original, original_tray
    assert result == 0 and passed and quit_observed == [True]
    print("Lifecycle defaults, minimized startup, tray recovery, notification opt-in and scaled settings passed.")


if __name__ == "__main__":
    main()
