"""In-app playback keys respect text fields and act when the player has focus."""
import tempfile
import traceback

from PySide6.QtCore import QObject, QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from youtube_music_native import app


def main():
    original, passed = app.load_window, []

    def load(*args, **kwargs):
        engine = original(*args, **kwargs)
        window = engine.rootObjects()[0]
        player = args[2]

        def verify():
            try:
                window.resize(920, 620)
                window.requestActivate()
                QTest.qWait(60)
                playing = player.playing
                search = window.findChild(QObject, 'searchField')
                search.forceActiveFocus()
                QTest.qWait(20)
                assert window.property('editingText') and not window.property('playbackShortcuts')
                QTest.keyClick(window, Qt.Key.Key_Space)
                assert player.playing == playing and search.property('text') == ' '
                window.findChild(QObject, "playerBar").forceActiveFocus()
                QTest.qWait(20)
                assert window.property('playbackShortcuts')
                QTest.keyClick(window, Qt.Key.Key_Space)
                QTest.qWait(20)
                assert player.playing != playing
                assert not engine.property('qmlWarnings'), engine.property('qmlWarnings')
                passed.append(True)
            except Exception:
                traceback.print_exc()
            finally:
                window.close()
                QGuiApplication.instance().exit(0 if passed else 1)
        QTimer.singleShot(200, verify)
        return engine

    app.load_window = load
    with tempfile.TemporaryDirectory(prefix='youtube-music-shortcuts-') as folder:
        result = app.main(['--fixture', '--data-dir', folder])
    app.load_window = original
    assert result == 0 and passed
    print('Text-field guards and in-app playback keys passed.')


if __name__ == '__main__':
    main()
