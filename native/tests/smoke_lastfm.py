"""Exercise Last.fm settings with a fake worker; never access a real account."""

import tempfile
from pathlib import Path
import traceback

from PySide6.QtCore import QObject, QMetaObject, QPointF, QTimer, Qt, Signal
from PySide6.QtTest import QTest

from youtube_music_native import app


class Worker(QObject):
    succeeded = Signal(int, dict)
    failed = Signal(int, dict)
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.requests = []
    def request(self, operation, payload):
        self.requests.append(payload)
        return len(self.requests)
    def close(self):
        pass


def main():
    original, passed = app.load_window, []
    def load(*args, **kwargs):
        shell = args[0]
        state = shell.lastFm
        state._fixture = False
        worker = Worker()
        state._worker_factory = lambda *args, **kwargs: worker
        state._browser = lambda url: True
        engine = original(*args, **kwargs)
        window = engine.rootObjects()[0]
        player = args[2]
        def click(item):
            point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point)
        def verify():
            try:
                dialog = window.findChild(QObject, "lastFmSettingsDialog")
                window.resize(1280, 820)
                window.requestActivate()
                assert not state.enabled and not worker.requests
                QMetaObject.invokeMethod(dialog, "open")
                QTest.qWait(60)
                assert worker.requests[-1]["action"] == "status"
                worker.succeeded.emit(1, {"configured": True, "connected": True, "username": "Fixture listener", "pendingCount": 0})
                enabled = dialog.findChild(QObject, "lastFmEnabled")
                click(enabled)
                assert state.enabled
                state.setEnabled(False)
                assert not state.enabled
                for scale in (80, 100, 150):
                    shell.setUiScale(scale)
                    for width, height in ((1600, 900), (1280, 820), (920, 620)):
                        window.resize(width, height)
                        QTest.qWait(80)
                        panel = dialog.property("contentItem")
                        bounds = panel.mapRectToScene(panel.boundingRect())
                        assert bounds.left() >= 0 and bounds.right() <= width + 1
                        assert bounds.top() >= 0 and bounds.bottom() <= height + 1
                        field = dialog.findChild(QObject, "lastFmSecret")
                        field.forceActiveFocus()
                        QTest.qWait(30)
                        focus_bounds = field.mapRectToScene(field.boundingRect())
                        assert focus_bounds.top() >= bounds.top() - 1 and focus_bounds.bottom() <= bounds.bottom() + 1, (scale, width, height, focus_bounds, bounds)
                        assert not engine.property("qmlWarnings"), engine.property("qmlWarnings")
                key = dialog.findChild(QObject, "lastFmApiKey")
                secret = dialog.findChild(QObject, "lastFmSecret")
                key.setProperty("text", "synthetic-key")
                secret.setProperty("text", "synthetic-secret")
                key.forceActiveFocus()
                playing = player.playing
                QTest.keyClick(window, Qt.Key.Key_Space)
                assert player.playing == playing
                QMetaObject.invokeMethod(dialog, "close")
                QTest.qWait(60)
                assert not key.property("text") and not secret.property("text")
                passed.append(True)
                window.close()
            except Exception:
                traceback.print_exc()
                window.close()
        QTimer.singleShot(300, verify)
        return engine
    app.load_window = load
    with tempfile.TemporaryDirectory(prefix="lastfm-ui-") as path:
        result = app.main(["--fixture", "--data-dir", path])
    assert result == 0 and passed
    print("Last.fm settings and disabled-state smoke passed.")


if __name__ == "__main__":
    main()
