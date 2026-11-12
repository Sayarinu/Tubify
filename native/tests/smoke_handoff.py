"""Continue on Phone: menu entry, QR dialog layout, Copy Link and pause-on-close."""

import tempfile
import traceback

from PySide6.QtCore import QObject, QMetaObject, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from tubify import app

TRACK = {"kind": "song", "videoId": "abcdefghijk", "title": "Fixture song", "artist": "Fixture artist", "duration": 200}


def main():
    original, passed = app.load_window, []

    def load(*args, **kwargs):
        shell, player = args[0], args[2]
        engine = original(*args, **kwargs)
        window = engine.rootObjects()[0]

        def find(name):
            return window.findChild(QObject, name)

        def phone_entry():
            return next(node for node in find("mediaMenu").findChildren(QObject) if node.property("text") == "Continue on Phone")

        def verify():
            try:
                player.playTracks([TRACK])
                player.setContext({"kind": "playlist", "playlistId": "PLfixture123"})
                QTest.qWait(100)
                shell.showMenu(player.currentTrack, {"nowPlaying": True})
                QTest.qWait(50)
                entry = phone_entry()
                assert find("mediaMenu").property("opened") and entry.property("visible")
                QMetaObject.invokeMethod(entry, "triggered")
                QTest.qWait(100)
                dialog = find("handoffDialog")
                assert dialog.property("opened") and not find("mediaMenu").property("opened")
                url = shell.handoffState.url
                assert url.startswith("https://music.youtube.com/watch?v=abcdefghijk&list=PLfixture123"), url
                assert find("handoffUrl").property("text") == url
                assert find("handoffQr").property("implicitWidth") > 20, "QR image did not load"
                for scale in (80, 100, 150):
                    shell.setUiScale(scale)
                    for width, height in ((1600, 900), (1280, 820), (920, 620)):
                        window.resize(width, height)
                        QTest.qWait(60)
                        panel = dialog.property("contentItem")
                        bounds = panel.mapRectToScene(panel.boundingRect())
                        assert bounds.left() >= 0 and bounds.right() <= width + 1, (scale, width, bounds)
                        assert bounds.top() >= 0 and bounds.bottom() <= height + 1, (scale, height, bounds)
                assert not engine.property("qmlWarnings"), engine.property("qmlWarnings")
                QMetaObject.invokeMethod(find("handoffCopy"), "clicked")
                assert QGuiApplication.clipboard().text() == url

                # Unticking Pause keeps playback going; the default pauses on close.
                player.resume()
                find("handoffPause").setProperty("checked", False)
                QMetaObject.invokeMethod(find("handoffDone"), "clicked")
                QTest.qWait(100)
                assert not dialog.property("opened") and player.wantsPlayback
                shell.handoffState.open()
                QTest.qWait(100)
                assert dialog.property("opened") and find("handoffPause").property("checked")
                assert window.property("modalOpen") and not window.property("playbackShortcuts")
                QMetaObject.invokeMethod(dialog, "reject")
                QTest.qWait(100)
                assert not player.wantsPlayback

                # The queue's own options keep their menu, without the phone entry.
                shell.showMenu(player.currentTrack, {})
                QTest.qWait(50)
                assert not phone_entry().property("visible")
                QMetaObject.invokeMethod(find("mediaMenu"), "close")
                passed.append(True)
            except Exception:
                traceback.print_exc()
            window.close()

        QTimer.singleShot(350, verify)
        return engine

    app.load_window = load
    with tempfile.TemporaryDirectory(prefix="native-handoff-ui-") as folder:
        result = app.main(["--fixture", "--data-dir", folder])
    assert result == 0 and passed
    print("Continue on Phone menu, QR dialog, Copy Link and pause-on-close passed.")


if __name__ == "__main__":
    main()
