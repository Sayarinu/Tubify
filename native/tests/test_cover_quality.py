"""Exercise actual QML source choice and physical decoding in isolated Qt apps."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("scale", [1, 1.5, 2])
@pytest.mark.parametrize("ui_scale", [80, 100, 150])
def test_large_cover_uses_upgraded_source_at_display_pixel_ratio(tmp_path, scale, ui_scale):
    script = r'''
import math
from pathlib import Path
import sys
import time
from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from tubify.downloads.download_view import DownloadView
from tubify.theme import ThemeState
from tubify.shell import ShellController
from tubify.app import PACKAGE
app = QGuiApplication([])
root = Path(sys.argv[1])
for size in (60, 1200):
    image = QImage(size, size, QImage.Format.Format_RGB32)
    image.fill(0xFFCC3344)
    assert image.save(str(root / (str(size) + '.png')))
small, large = [(root / (str(size) + '.png')).as_uri() for size in (60, 1200)]
class RecordingDownloads(DownloadView):
    calls = []
    @Slot("QVariantMap", int, bool)
    def ensureArtwork(self, media, pixels, retry):
        self.calls.append((media, pixels))
downloads = RecordingDownloads(root, fixture=True)
downloads._artwork['abcdefghijk'] = small
downloads._large_artwork['abcdefghijk'] = {'url': large, 'width': 1200, 'height': 1200}
theme = ThemeState(root / 'theme.ini')
shell = ShellController(root / 'shell.ini')
shell.setUiScale(int(sys.argv[3]))
physical_scale = float(sys.argv[2]) * shell.uiScaleFactor
engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty('appState', shell)
engine.rootContext().setContextProperty('downloadsState', downloads)
engine.rootContext().setContextProperty('themeState', theme)
engine.rootContext().setContextProperty('smallCover', small)
engine.loadData(b'import QtQuick\nimport QtQuick.Controls\nimport "."\nApplicationWindow { visible: true; width: 1000; height: 1000; Cover { scale: appState.uiScaleFactor; transformOrigin: Item.TopLeft; objectName: "largeCover"; width: 300; height: 300; largeArtwork: true; mediaKey: "abcdefghijk"; source: smallCover; media: ({videoId: "abcdefghijk"}) } }', QUrl.fromLocalFile(str(PACKAGE / 'qml' / 'components' / 'test.qml')))
window = engine.rootObjects()[0]
cover = window.findChild(QObject, 'largeCover')
art = cover.findChild(QObject, 'coverArtwork')
def wait_until(predicate, description):
    deadline = time.monotonic() + 2
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert predicate(), description
for size in (300, 600):
    cover.setProperty('width', size)
    cover.setProperty('height', size)
    wait_until(lambda: cover.property('ready'), 'Cover image did not become ready')
    assert art.property('source').toString() == large
    assert art.property('sourceSize').width() == math.ceil(size * float(sys.argv[2]) * shell.uiScaleFactor)
    assert cover.property('ready')
    def painted():
        frame = window.grabWindow()
        if frame.isNull():
            return False
        center = frame.pixelColor(round(size * physical_scale / 2), round(size * physical_scale / 2))
        return center.red() > 180 and center.green() < 80
    wait_until(painted, 'Ready cover did not paint its decoded pixels')
cover.setProperty('mediaKey', 'lmnopqrstuv')
cover.setProperty('media', {'videoId': 'lmnopqrstuv'})
downloads._artwork['lmnopqrstuv'] = (root / 'missing.png').as_uri()
downloads.changed.emit()
wait_until(lambda: cover.property('failedSource').endswith('missing.png'), 'Missing thumbnail did not report failure')
downloads._large_artwork['lmnopqrstuv'] = {'url': large, 'width': 1200, 'height': 1200}
downloads.changed.emit()
wait_until(lambda: art.property('source').toString() == large and cover.property('ready'), 'Large image did not replace failed thumbnail')
cover.setProperty('visible', False)
downloads.calls.clear()
cover.setProperty('width', 400)
QTest.qWait(180)
assert not downloads.calls
cover.setProperty('visible', True)
# QML timers advance with render frames; a 30ms margin above the debounce is
# unreliable on macOS CI. Wait for the request, then check its exact resolution.
wait_until(lambda: bool(downloads.calls), 'Visible Cover did not request an artwork upgrade')
assert downloads.calls[-1][1] == math.ceil(600 * float(sys.argv[2]) * shell.uiScaleFactor), downloads.calls
window.close()
engine.deleteLater()
downloads.close()
'''
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software", "QT_SCALE_FACTOR": str(scale), "PYTHONPATH": str(Path(__file__).parents[1] / "src")}
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path), str(scale), str(ui_scale)], env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("backend", ["software", ""])
def test_large_cover_shows_small_thumbnail_until_the_large_image_arrives(tmp_path, backend):
    script = r'''
import faulthandler
import sys
# Report where the child is stuck instead of being killed silently by the timeout.
faulthandler.dump_traceback_later(20, exit=True)
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socketserver
import threading
import time
from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from tubify.downloads.download_view import DownloadView
from tubify.theme import ThemeState
from tubify.shell import ShellController
from tubify.app import PACKAGE
app = QGuiApplication([])
root = Path(sys.argv[1])
for name, size, color in (("small", 60, 0xFFCC2222), ("large", 1200, 0xFF22CC22)):
    image = QImage(size, size, QImage.Format.Format_RGB32)
    image.fill(color)
    assert image.save(str(root / (name + ".png")))
small = (root / "small.png").as_uri()
release = threading.Event()
class Slow(BaseHTTPRequestHandler):
    def do_GET(self):
        release.wait(10)
        body = (root / "large.png").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass
class LoopbackServer(ThreadingHTTPServer):
    # HTTPServer.server_bind resolves the host's FQDN, which can block for many
    # seconds on macOS runners; a loopback fixture needs no name.
    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = "127.0.0.1", self.server_address[1]
server = LoopbackServer(("127.0.0.1", 0), Slow)
threading.Thread(target=server.serve_forever, daemon=True).start()
large = "http://127.0.0.1:%d/large.png" % server.server_port
downloads = DownloadView(root, fixture=True)
downloads._large_artwork["abcdefghijk"] = {"url": large, "width": 1200, "height": 1200}
theme = ThemeState(root / "theme.ini")
shell = ShellController(root / "shell.ini")
engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("appState", shell)
engine.rootContext().setContextProperty("downloadsState", downloads)
engine.rootContext().setContextProperty("themeState", theme)
engine.rootContext().setContextProperty("smallCover", small)
engine.loadData(b'import QtQuick\nimport QtQuick.Controls\nimport "."\nApplicationWindow { visible: true; width: 400; height: 400; Cover { objectName: "largeCover"; width: 300; height: 300; largeArtwork: true; mediaKey: "abcdefghijk"; source: smallCover; media: ({videoId: "abcdefghijk", thumbnail: smallCover}) } }', QUrl.fromLocalFile(str(PACKAGE / "qml" / "components" / "test.qml")))
window = engine.rootObjects()[0]
cover = window.findChild(QObject, "largeCover")
def wait_until(predicate, description, seconds=3):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert predicate(), description
def center():
    frame = window.grabWindow()
    return None if frame.isNull() else frame.pixelColor(150, 150)
def red():
    color = center()
    return color is not None and color.red() > 180 and color.green() < 80
def green():
    color = center()
    return color is not None and color.green() > 180 and color.red() < 80
wait_until(red, "The cached small thumbnail did not show while the large image loaded")
assert not cover.property("ready")
release.set()
wait_until(lambda: cover.property("ready") and green(), "The large image did not replace the thumbnail")
window.close()
engine.deleteLater()
downloads.close()
server.shutdown()
server.server_close()
'''
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": str(Path(__file__).parents[1] / "src")}
    if backend:
        env["QT_QUICK_BACKEND"] = backend
    else:
        env.pop("QT_QUICK_BACKEND", None)
    try:
        result = subprocess.run([sys.executable, "-c", script, str(tmp_path)], env=env, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired as error:
        raise AssertionError(f"Cover test hung; stderr so far: {error.stderr!r}") from None
    assert result.returncode == 0, result.stderr
