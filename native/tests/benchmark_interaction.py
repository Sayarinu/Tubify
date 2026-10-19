"""Measure shell readiness, visible input response and animated long-list scrolling."""

import argparse
import json
import math
import os
from pathlib import Path
import statistics
import tempfile
import time
import traceback

STARTED = float(os.environ.get("NATIVE_BENCHMARK_STARTED", time.monotonic()))

from PySide6.QtCore import QObject, QTimer, Qt, QUrl
from PySide6.QtGui import QColor, QGuiApplication, QImage
from PySide6.QtQml import QQmlComponent
from PySide6.QtTest import QTest

from youtube_music_native import app


def p95(values):
    return sorted(values)[max(0, math.ceil(len(values) * .95) - 1)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--launch-only", action="store_true")
    parser.add_argument("--onscreen", action="store_true")
    args = parser.parse_args()
    if not args.onscreen and os.environ.get("QT_QPA_PLATFORM") != "offscreen":
        parser.error("Set QT_QPA_PLATFORM=offscreen, or explicitly choose --onscreen for a desktop run")
    original = app.load_window
    report, passed = {}, []
    with tempfile.TemporaryDirectory(prefix="native-interaction-") as directory:
        root = Path(directory)
        artwork = []
        for index in range(60):
            image = QImage(160, 160, QImage.Format.Format_RGB32)
            image.fill(QColor.fromHsv(index * 6, 150, 180))
            image.save(str(root / (str(index) + ".png")))
            artwork.append((root / (str(index) + ".png")).as_uri())

        def load(*values, **kwargs):
            engine = original(*values, **kwargs)
            window = engine.rootObjects()[0]
            shell, view, library = values[0], values[3], values[9]
            state = {"done": False, "first_frame": False, "input_start": None, "input_values": [], "animation": None}

            def finish(success):
                if state["done"]:
                    return
                state["done"] = True
                success = success and not engine.property("qmlWarnings")
                report.update(platform=QGuiApplication.platformName(), renderer=str(window.rendererInterface().graphicsApi()), client_size=[window.width(), window.height()], passed=success, qml_clean=not engine.property("qmlWarnings"))
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(report, indent=2))
                if success:
                    passed.append(True)
                window.close()
                QGuiApplication.instance().exit(0 if success else 1)

            def frame():
                if not state["first_frame"]:
                    state["first_frame"] = True
                    report["shell_ms"] = round((time.monotonic() - STARTED) * 1000, 3)
                    if args.launch_only:
                        QTimer.singleShot(0, lambda: finish(True))
                    else:
                        window.frameSwapped.disconnect(frame)
                if state["input_start"] is not None:
                    state["input_values"].append((time.monotonic() - state["input_start"]) * 1000)
                    state["input_start"] = None
                    if len(state["input_values"]) < 20:
                        QTimer.singleShot(40, input_once)
                    else:
                        report["local_input_p95_ms"] = round(p95(state["input_values"]), 3)
                        report["local_input_max_ms"] = round(max(state["input_values"]), 3)
                        QTimer.singleShot(0, lambda: finish(True))

            def input_once():
                try:
                    old = shell.volume
                    state["input_start"] = time.monotonic()
                    QTest.keyClick(window, Qt.Key.Key_M)
                    assert shell.volume != old, "Mute shortcut did not update the visible control"
                    window.update()
                except Exception:
                    traceback.print_exc()
                    finish(False)

            def scroll_finished():
                animation = state["animation"]
                if animation.property("running"):
                    return
                try:
                    times = animation.property("samples").toVariant()
                    assert len(times) >= 100
                    report.update(scroll_frames=len(times), scroll_p95_frame_ms=round(p95(times), 3), scroll_median_frame_ms=round(statistics.median(times), 3), scroll_mean_fps=round(1000 / statistics.mean(times), 2), list_songs=10000)
                    window.frameSwapped.connect(frame)
                    QTimer.singleShot(100, input_once)
                except Exception:
                    traceback.print_exc()
                    finish(False)

            def scroll():
                try:
                    shell.navigate("Library")
                    library.select("Songs")
                    view.showLocal("library_songs", {"items": [{"kind": "song", "videoId": "fixture0001", "title": "Scrolling fixture " + str(index), "thumbnail": artwork[index % len(artwork)]} for index in range(10000)], "cursor": None})
                    QTest.qWait(200)
                    listing = window.findChild(QObject, "librarySongs")
                    assert listing and listing.property("count") == 10000
                    component = QQmlComponent(engine)
                    component.setData(b'''import QtQuick
FrameAnimation {
    property var target
    property var samples: []
    onTriggered: {
        target.contentY += 650 * frameTime
        if (currentFrame > 5) samples.push(frameTime * 1000)
        if (elapsedTime >= 5) running = false
    }
}''', QUrl())
                    animation = component.createWithInitialProperties({"target": listing}, engine.contextForObject(listing))
                    assert animation, component.errors()
                    animation.setParent(listing)
                    state["animation"] = animation
                    animation.runningChanged.connect(scroll_finished)
                    animation.setProperty("running", True)
                except Exception:
                    traceback.print_exc()
                    finish(False)

            window.frameSwapped.connect(frame)
            QTimer.singleShot(0, window.update)
            if not args.launch_only:
                QTimer.singleShot(300, scroll)
            QTimer.singleShot(20000, lambda: finish(False))
            return engine

        app.load_window = load
        result = app.main(["--fixture", "--data-dir", str(root)])
        app.load_window = original
        assert result == 0 and passed
    print(json.dumps(report))


if __name__ == "__main__":
    main()
