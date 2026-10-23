"""Exercise Discord opt-in settings without connecting to a real Discord account."""
from pathlib import Path
import tempfile
import traceback

from PySide6.QtCore import QObject, QMetaObject, QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from youtube_music_native import app


def main():
    original = app.load_window
    passed = []
    def load(*args, **kwargs):
        engine = original(*args, **kwargs)
        window, shell, player = engine.rootObjects()[0], args[0], args[2]
        def verify():
            try:
                window.resize(920, 620)
                dialog = window.findChild(QObject, "discordSettingsDialog")
                QMetaObject.invokeMethod(dialog, "open")
                QTest.qWait(80)
                assert dialog.property("visible")
                toggle = dialog.findChild(QObject, "discordEnabledOption")
                assert not toggle.property("checked")
                QMetaObject.invokeMethod(toggle, "click")
                field = dialog.findChild(QObject, "discordClientId")
                field.setProperty("text", "123456789012345678")
                QMetaObject.invokeMethod(field, "accepted")
                assert shell.discordState.enabled
                assert shell.discordState.pipe is None
                assert "fixture" in shell.discordState.status
                field.forceActiveFocus()
                playing = player.playing
                QTest.keyClick(window, Qt.Key.Key_Space)
                assert player.playing == playing
                assert dialog.property("height") < window.height()
                assert not engine.property("qmlWarnings"), engine.property("qmlWarnings")
                QMetaObject.invokeMethod(dialog, "close")
                passed.append(True)
            except Exception:
                traceback.print_exc()
            finally:
                window.close()
                QGuiApplication.instance().exit(0 if passed else 1)
        QTimer.singleShot(200, verify)
        return engine
    app.load_window = load
    try:
        with tempfile.TemporaryDirectory(prefix="youtube-music-discord-") as folder:
            result = app.main(["--fixture", "--data-dir", folder])
        assert result == 0 and passed
    finally:
        app.load_window = original
    print("Discord consent, application ID, fixture isolation and modal shortcuts passed.")


if __name__ == "__main__":
    main()
