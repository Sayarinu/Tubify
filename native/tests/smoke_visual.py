"""Render every view, check accessible controls and stress virtualized lists."""

import argparse
import json
from pathlib import Path
import tempfile
import time
import traceback
import wave

from PySide6.QtCore import QObject, QTimer, Qt
from PySide6.QtGui import QAccessible, QColor, QGuiApplication, QImage
from PySide6.QtTest import QTest

from youtube_music_native import app


def visual_items(item):
    yield item
    for child in item.childItems():
        yield from visual_items(child)


def fully_visible(item):
    if not item.isVisible():
        return False
    parent = item.parentItem()
    while parent:
        if parent.clip():
            position = item.mapToItem(parent, item.boundingRect().topLeft())
            if position.x() < 0 or position.y() < 0 or position.x() + item.width() > parent.width() or position.y() + item.height() > parent.height():
                return False
        parent = parent.parentItem()
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--native-gpu", action="store_true")
    parser.add_argument("--soak-seconds", type=int, default=0)
    args = parser.parse_args()
    original = app.load_window
    passed, results = [], []
    if args.native_gpu:
        from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
        QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
        engine_type = app.QQmlApplicationEngine
        class Engine(engine_type):
            def __init__(self):
                super().__init__()
                self.setInitialProperties({"flags": Qt.WindowType.Window | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.WindowStaysOnBottomHint})
        app.QQmlApplicationEngine = Engine
    with tempfile.TemporaryDirectory(prefix="youtube-music-visual-") as folder:
        root = Path(folder)
        art = QImage(160, 160, QImage.Format.Format_RGB32)
        art.fill(QColor("#d04060"))
        for x in range(80, 160):
            for y in range(160):
                art.setPixelColor(x, y, QColor("#4060d0"))
        art.save(str(root / "art.png"))
        if args.soak_seconds:
            from youtube_music_native.media import MediaFiles
            media = MediaFiles(root / "media")
            audio = media.root / "fixture.wav"
            with wave.open(str(audio), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(16000)
                handle.writeframes(b"\0\0" * 16000 * 60)
            media.publish("fixture0001", audio)
            media.close()

        def load(*values, **kwargs):
            engine = original(*values, **kwargs)
            window = engine.rootObjects()[0]
            shell, account, player, view, browse, downloads, search, library = values[0], values[1], values[2], values[3], values[5], values[6], values[7], values[9]
            uri = (root / "art.png").as_uri()
            for section in shell._fixture["shelves"]:
                for track in section["items"]:
                    track.update(thumbnail=uri, videoId="fixture0001", duration=60)
            for entry in player.queue.entries:
                entry["track"].update(thumbnail=uri, videoId="fixture0001", duration=60)
            account._profile["avatar"] = uri
            account.changed.emit()
            if args.soak_seconds:
                from youtube_music_native.audio import Audio
                from youtube_music_native.jobs import Worker
                player._fixture = False
                player.worker = Worker(player, idle_ms=15000)
                player.worker.succeeded.connect(player._resolved)
                player.worker.failed.connect(player._failed)
                player.audio_factory = lambda **options: Audio(output="null", **options)
                player.save_timer.start()
                player.playTracks([entry["track"] for entry in player.queue.entries])
                player.setRepeat("all")
            player.changed.emit()
            scenarios = [
                ("home", lambda: shell.navigate("Home")),
                ("explore", lambda: shell.navigate("Explore")),
                ("search", lambda: shell.search("fixture music")),
                ("library", lambda: shell.navigate("Library")),
                ("artists", lambda: library.select("Artists")),
                ("album", lambda: browse.open({"kind": "album", "id": "MPREfixture", "title": "Fixture album"})),
                ("playlist", lambda: browse.open({"kind": "playlist", "id": "PLfixture", "title": "Fixture playlist"})),
                ("artist", lambda: (browse.open({"kind": "artist", "id": "UCfixture", "title": "Fixture artist"}), view.patch({"hero": uri}))),
                ("queue", lambda: (shell.setPlayerTab("Up next"), shell.setExpanded(True))),
                ("lyrics", lambda: (shell.setPlayerTab("Lyrics"), shell.setExpanded(True))),
                ("downloads", lambda: shell.navigate("Downloads")),
            ]
            state = {"index": 0, "done": False, "started": time.monotonic(), "audio_position": 0., "rounded_artwork": 0}

            def finish(success):
                if state["done"]:
                    return
                state["done"] = True
                if success:
                    passed.append(True)
                if args.output_dir:
                    args.output_dir.mkdir(parents=True, exist_ok=True)
                    (args.output_dir / "report.json").write_text(json.dumps({"views": results, "passed": bool(passed), "soak_seconds": round(time.monotonic() - state["started"], 1), "renderer": str(window.rendererInterface().graphicsApi()), "rounded_artwork_checks": state["rounded_artwork"]}))
                window.close()
                QGuiApplication.instance().exit(0 if success else 1)

            def check():
                # Snapshot a completed scene; slow CI hosts can still be incubating delegates after 80 ms.
                incubation = engine.incubationController()
                deadline = time.monotonic() + 2
                while incubation and incubation.incubatingObjectCount() and time.monotonic() < deadline:
                    incubation.incubateFor(5)
                    QTest.qWait(10)
                assert not incubation or not incubation.incubatingObjectCount(), "View did not finish creating its visible delegates"
                assert not engine.property("qmlWarnings"), engine.property("qmlWarnings")
                image = window.grabWindow()
                assert not image.isNull()
                scale = image.width() / window.width()
                for item in visual_items(window.contentItem()):
                    if item.property("mediaKey") is not None and item.property("ready") and item.width() > 80 and fully_visible(item):
                        # Probe beyond 100 px as well as the center: SVG percentage masks can clip larger covers.
                        for fraction in (.2, .5, .8):
                            point = item.mapToScene(item.boundingRect().topLeft())
                            px, py = round((point.x() + item.width() * fraction) * scale), round((point.y() + item.height() / 2) * scale)
                            if 0 <= px < image.width() and 0 <= py < image.height():
                                pixel = image.pixelColor(px, py)
                                assert pixel.red() + pixel.blue() > 240, (item.width(), fraction, pixel.name())
                    if args.native_gpu and item.property("mediaKey") is not None and item.property("ready") and item.width() > 80 and abs(item.property("radius") - item.width() / 2) < 1 and fully_visible(item):
                        position = item.mapToScene(item.boundingRect().topLeft())
                        x, y = round(position.x() * scale), round(position.y() * scale)
                        center = item.mapToScene(item.boundingRect().center())
                        cx, cy = round(center.x() * scale), round(center.y() * scale)
                        if 0 <= x < image.width() and 0 <= y < image.height() and 0 <= cx < image.width() and 0 <= cy < image.height():
                            corner, middle = image.pixelColor(x + 1, y + 1), image.pixelColor(cx, cy)
                            assert max(corner.red(), corner.blue()) < 160, (str(window.rendererInterface().graphicsApi()), corner.name(), x, y, item.width(), item.property("radius"))
                            assert middle.red() + middle.blue() > 240
                            state["rounded_artwork"] += 1
                    tip = item.property("tip")
                    if not tip or not item.isVisible() or not item.isEnabled():
                        continue
                    position = item.mapToScene(item.boundingRect().center())
                    x, y = round(position.x() * scale), round(position.y() * scale)
                    if not (14 * scale < x < image.width() - 14 * scale and 14 * scale < y < image.height() - 14 * scale):
                        continue
                    interface = QAccessible.queryAccessibleInterface(item)
                    assert interface and interface.text(QAccessible.Text.Name) == tip
                    # A rendered icon must survive layout and state changes in software too.
                    pixels = sum(max(image.pixelColor(px, py).red(), image.pixelColor(px, py).green(), image.pixelColor(px, py).blue()) > 80 for px in range(x - 10, x + 10) for py in range(y - 10, y + 10))
                    parent, transport = item.parentItem(), False
                    while parent:
                        transport = transport or parent.objectName() == "playerBar"
                        parent = parent.parentItem()
                    if transport:
                        if pixels <= 4:
                            # A source change may fall between grabWindow's frame and the property snapshot.
                            QTest.qWait(35)
                            image = window.grabWindow()
                            pixels = sum(max(image.pixelColor(px, py).red(), image.pixelColor(px, py).green(), image.pixelColor(px, py).blue()) > 80 for px in range(x - 10, x + 10) for py in range(y - 10, y + 10))
                        if pixels <= 4 and args.output_dir:
                            image.save(str(args.output_dir / "failed-control.png"))
                        assert pixels > 4, tip
                return image

            def initial():
                try:
                    if args.native_gpu and QGuiApplication.platformName() != "offscreen":
                        assert not window.isActive(), "The verification window must not take focus"
                    for size in ((1280, 820), (920, 620)):
                        window.resize(*size)
                        for name, action in scenarios:
                            action()
                            QTest.qWait(80)
                            image = check()
                            if name == "artist":
                                hero = window.findChild(QObject, "artistHero")
                                assert hero.isVisible()
                                point = hero.mapToScene(hero.boundingRect().topLeft())
                                pixel = image.pixelColor(round(point.x() + hero.width() / 2), round(point.y() + 30))
                                assert max(pixel.red(), pixel.blue()) > 40, pixel.name()
                            if args.output_dir:
                                args.output_dir.mkdir(parents=True, exist_ok=True)
                                assert image.save(str(args.output_dir / (name + "-" + str(size[0]) + ".png")))
                            results.append({"view": name, "width": size[0], "height": size[1]})
                    if args.native_gpu:
                        assert state["rounded_artwork"] > 0
                    browse.open({"kind": "playlist", "id": "PLfixture"})
                    view._error = "The provider is unavailable. Downloaded music remains available. " * 3
                    view.changed.emit()
                    QTest.qWait(80)
                    check()
                    account.requireReconnect("Reconnect to browse online music.")
                    QTest.qWait(80)
                    check()
                    account._reconnect = False
                    account.changed.emit()
                    shell.navigate("Library")
                    library.select("Songs")
                    tracks = [{"kind": "song", "videoId": "fixture0001", "title": "Long list fixture " + str(index), "thumbnail": uri} for index in range(10000)]
                    view.showLocal("library_songs", {"items": tracks, "cursor": None})
                    QTest.qWait(120)
                    listing = window.findChild(QObject, "librarySongs")
                    assert listing.property("count") == 10000
                    listing.setProperty("contentY", listing.property("contentHeight") - listing.property("height"))
                    QTest.qWait(100)
                    count = sum(item.metaObject().className().startswith("SongRow_") for item in visual_items(window.contentItem()))
                    assert 0 < count < 60, count
                    check()
                    if args.soak_seconds:
                        timer.start()
                    else:
                        finish(True)
                except Exception:
                    traceback.print_exc()
                    finish(False)

            def tick():
                try:
                    name, action = scenarios[state["index"] % len(scenarios)]
                    action()
                    QTest.qWait(50)
                    check()
                    state["index"] += 1
                    state["audio_position"] = max(state["audio_position"], player.position)
                    if time.monotonic() - state["started"] >= args.soak_seconds:
                        assert player.sourceKind == "local" and state["audio_position"] > 2
                        timer.stop()
                        finish(True)
                except Exception:
                    traceback.print_exc()
                    timer.stop()
                    finish(False)
            timer = QTimer(shell)
            timer.setInterval(1000)
            timer.timeout.connect(tick)
            QTimer.singleShot(250, initial)
            QTimer.singleShot(max(30000, (args.soak_seconds + 30) * 1000), lambda: finish(False))
            return engine

        app.load_window = load
        result = app.main(["--fixture", "--data-dir", str(root)])
        app.load_window = original
        assert result == 0 and passed
    print("All views at both sizes, accessible controls and a 10,000-song list passed.")


if __name__ == "__main__":
    main()
