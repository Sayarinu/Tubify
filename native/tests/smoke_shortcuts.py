"""Exercise shortcut settings and focus guards through an actual Qt window."""
import argparse
from pathlib import Path
import tempfile
import traceback

from PySide6.QtCore import QObject, QMetaObject, QPointF, QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from youtube_music_native import app
from test_shortcuts import FakeAdapter


def visual(item, name):
    if item.objectName() == name:
        return item
    for child in item.childItems():
        found = visual(child, name)
        if found:
            return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--ui-scale', type=int, default=100)
    options = parser.parse_args()
    original, passed = app.load_window, []

    def load(*args, **kwargs):
        engine = original(*args, **kwargs)
        window = engine.rootObjects()[0]
        shell, player = args[0], args[2]
        state = shell.shortcutState
        state.factory = FakeAdapter

        def verify():
            try:
                shell.setUiScale(options.ui_scale)
                window.resize(920, 620)
                window.requestActivate()
                dialog = window.findChild(QObject, 'shortcutSettings')
                QMetaObject.invokeMethod(dialog, 'open')
                QTest.qWait(100)
                enabled = window.findChild(QObject, 'globalShortcutsEnabled')
                point = enabled.mapToScene(QPointF(enabled.width()/2, enabled.height()/2)).toPoint()
                QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point)
                QTest.qWait(40)
                assert state.enabled and state.status == 'Registered'
                playing = player.playing
                state.adapter.activated.emit('toggle')
                QTest.qWait(20)
                assert player.playing == playing and not window.property('playbackShortcuts')
                field = visual(window.contentItem(), 'globalShortcut-toggle')
                field.forceActiveFocus()
                field.setProperty('text', 'Ctrl+Alt+Right')
                QMetaObject.invokeMethod(field, 'accepted')
                QTest.qWait(30)
                assert state.bindings[0]['error'] and state.bindings[0]['binding'] == 'Ctrl+Alt+Space'
                assert window.activeFocusItem() == field
                field = visual(window.contentItem(), 'globalShortcut-toggle')
                field.setProperty('text', 'Ctrl+Alt+P')
                QMetaObject.invokeMethod(field, 'accepted')
                QTest.qWait(30)
                assert state.bindings[0]['binding'] == 'Ctrl+Alt+P' and not state.bindings[0]['error']
                assert dialog.property('width') * shell.uiScaleFactor < window.width()
                assert dialog.property('height') * shell.uiScaleFactor < window.height()
                if options.output_dir:
                    options.output_dir.mkdir(parents=True, exist_ok=True)
                    assert window.grabWindow().save(str(options.output_dir / 'shortcuts-920.png'))
                QMetaObject.invokeMethod(dialog, 'close')
                QTest.qWait(60)
                search = window.findChild(QObject, 'searchField')
                search.forceActiveFocus()
                QTest.qWait(20)
                assert window.property('editingText') and not window.property('playbackShortcuts')
                state.adapter.activated.emit('toggle')
                QTest.qWait(20)
                assert player.playing == playing
                QTest.keyClick(window, Qt.Key.Key_Space)
                assert player.playing == playing and search.property('text') == ' '
                window.findChild(QObject, "playerBar").forceActiveFocus()
                QTest.qWait(20)
                assert window.property('playbackShortcuts')
                state.adapter.activated.emit('toggle')
                QTest.qWait(20)
                assert player.playing != playing
                QTest.keyClick(window, Qt.Key.Key_Space)
                assert player.playing == playing
                state.setEnabled(False)
                assert state.adapter is None
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
    print('Global shortcut settings, registration feedback, modal/text guards and local keys passed.')


if __name__ == '__main__':
    main()
