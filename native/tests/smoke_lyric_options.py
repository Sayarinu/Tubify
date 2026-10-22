"""Exercise provider consent/settings and supplied-timing styles in the app UI."""

import argparse
from pathlib import Path
import tempfile
import traceback

from PySide6.QtCore import QObject, QMetaObject, QPointF, QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from youtube_music_native import app
from youtube_music_native.lyric_formats import ttml


def visual_items(item):
    yield item
    for child in item.childItems():
        yield from visual_items(child)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    options = parser.parse_args()
    original, passed = app.load_window, []

    def load(*args, **kwargs):
        engine = original(*args, **kwargs)
        window = engine.rootObjects()[0]
        shell, player, lyrics = args[0], args[2], args[10]
        def verify():
            try:
                dialog = window.findChild(QObject, "lyricsSettingsDialog")
                assert dialog
                window.resize(1280, 820)
                window.requestActivate()
                QMetaObject.invokeMethod(dialog, "open")
                QTest.qWait(120)
                assert dialog.property("opened")
                consent = dialog.findChild(QObject, "externalLyricsOption")
                assert not consent.property("checked") and not lyrics.options["external"]
                point = consent.mapToScene(QPointF(consent.width() / 2, consent.height() / 2)).toPoint()
                QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point)
                assert lyrics.options["external"]
                lyrics.moveProvider("better", -1)
                lyrics.setProviderEnabled("unison", False)
                assert [row["id"] for row in lyrics.providers] == ["lrclib", "better", "unison"]
                assert not lyrics.providers[-1]["enabled"]
                for width, height in ((1280, 820), (920, 620)):
                    window.resize(width, height)
                    QTest.qWait(80)
                    assert dialog.property("width") < width and dialog.property("height") < height
                    scroll = dialog.findChild(QObject, "lyricsSettingsScroll")
                    assert scroll.property("contentWidth") == scroll.property("availableWidth"), "Settings must never scroll horizontally"
                    assert not engine.property("qmlWarnings"), engine.property("qmlWarnings")
                    if options.output_dir:
                        options.output_dir.mkdir(parents=True, exist_ok=True)
                        assert window.grabWindow().save(str(options.output_dir / f"lyrics-settings-{width}.png"))
                field = dialog.findChild(QObject, "lyricApiKey")
                field.forceActiveFocus()
                playing = player.playing
                QTest.keyClick(window, Qt.Key.Key_Space)
                assert player.playing == playing, "Typing in lyric settings triggered playback"
                QMetaObject.invokeMethod(dialog, "close")
                QTest.qWait(80)
                assert not field.property("text")
                shell.setLyricsOpen(True)
                lyrics.setOption("timestamps", True)
                lyrics.setOption("style", "word")
                result = ttml('<tt><p begin="0" end="10"><span begin="0" end="4">Original</span> <span begin="4" end="10">fixture</span></p><p begin="10" end="20">Plain next line</p></tt>')
                lyrics._data = {**result, "videoId": player.currentTrack.get("videoId", player.currentTrack.get("id", "fixture0001")), "source": "Original timing fixture", "match": "exact"}
                lyrics._accept()
                player.seek(1)
                QTest.qWait(120)
                pane = window.findChild(QObject, "lyricsPane")
                label = next(node for node in visual_items(pane) if node.objectName() == "lyricText-0")
                timestamp = next(node for node in visual_items(pane) if node.objectName() == "lyricTimestamp-0")
                assert timestamp.isVisible() and timestamp.property("text") == "0:00"
                assert "<font" in label.property("text") and "Word timing" in pane.findChild(QObject, "lyricSource").property("text")
                before = label.property("text")
                player.seek(4.)
                QTest.qWait(80)
                assert label.property("text") != before, "Supplied word timestamp did not update styling"
                lyrics.setOption("style", "syllable")
                QTest.qWait(80)
                assert label.property("text") == "Original fixture", "Word data must not create syllable effects"
                assert not engine.property("qmlWarnings"), engine.property("qmlWarnings")
                passed.append(True)
                window.close()
                QGuiApplication.instance().exit(0)
            except Exception:
                traceback.print_exc()
                window.close()
                QGuiApplication.instance().exit(1)
        QTimer.singleShot(150, verify)
        return engine

    app.load_window = load
    with tempfile.TemporaryDirectory(prefix="youtube-music-lyric-options-") as folder:
        result = app.main(["--fixture", "--data-dir", folder])
    assert result == 0 and passed
    print("Lyric consent, provider settings, modal shortcuts and genuine timing styles passed.")


if __name__ == "__main__":
    main()
