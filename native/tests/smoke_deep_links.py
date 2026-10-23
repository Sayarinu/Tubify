"""Verify cold-link preview and explicit actions against a synthetic player."""

import tempfile
import traceback

from PySide6.QtCore import QObject, QMetaObject, QPointF, QTimer, Qt
from PySide6.QtTest import QTest

from youtube_music_native import app

SONG = "https://music.youtube.com/watch?v=abcdefghijk"


def main():
    original, passed = app.load_window, []
    def load(*args, **kwargs):
        shell, player = args[0], args[2]
        state = shell.linkState
        before = dict(player.currentTrack)
        engine = original(*args, **kwargs)
        window = engine.rootObjects()[0]
        def click(item):
            point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point)
        def verify():
            try:
                dialog = window.findChild(QObject, "linkPreviewDialog")
                assert dialog.property("opened") and state.canPlay and not state.busy
                assert player.currentTrack == before, "Cold-link preview changed playback"
                for scale in (80, 100, 150):
                    shell.setUiScale(scale)
                    for width, height in ((1600, 900), (1280, 820), (920, 620)):
                        window.resize(width, height)
                        QTest.qWait(70)
                        panel = dialog.property("contentItem")
                        bounds = panel.mapRectToScene(panel.boundingRect())
                        assert bounds.left() >= 0 and bounds.right() <= width + 1
                        assert bounds.top() >= 0 and bounds.bottom() <= height + 1
                        button = dialog.findChild(QObject, "linkQueue")
                        button.forceActiveFocus()
                        QTest.qWait(30)
                        focus_bounds = button.mapRectToScene(button.boundingRect())
                        assert focus_bounds.top() >= bounds.top() - 1 and focus_bounds.bottom() <= bounds.bottom() + 1, (scale, width, bounds, focus_bounds)
                        assert not engine.property("qmlWarnings"), engine.property("qmlWarnings")
                window.requestActivate()
                initial = player.manualCount
                click(dialog.findChild(QObject, "linkQueue"))
                assert player.manualCount == initial + 1
                click(dialog.findChild(QObject, "linkPlay"))
                assert player.currentTrack["videoId"] == "abcdefghijk"
                state.receive("https://music.youtube.com/playlist?list=PLfixture123")
                QTest.qWait(50)
                assert dialog.findChild(QObject, "linkOpenPage").property("visible")
                click(dialog.findChild(QObject, "linkOpenPage"))
                assert args[3].route == "playlist" and not dialog.property("opened")
                state.receive("file:///private")
                QTest.qWait(50)
                assert dialog.property("opened") and not state.canPlay
                assert not dialog.findChild(QObject, "linkPlay").property("enabled")
                QMetaObject.invokeMethod(dialog, "close")
                passed.append(True)
                window.close()
            except Exception:
                traceback.print_exc()
                window.close()
        QTimer.singleShot(350, verify)
        return engine
    app.load_window = load
    with tempfile.TemporaryDirectory(prefix="native-link-ui-") as folder:
        result = app.main(["--fixture", "--data-dir", folder, SONG])
    assert result == 0 and passed
    print("Cold-link preview, explicit Play/Queue/Open and malformed-link safety passed.")


if __name__ == "__main__":
    main()
