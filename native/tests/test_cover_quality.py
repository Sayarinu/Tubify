"""Exercise actual QML source choice and physical decoding in isolated Qt apps."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("scale", [1, 1.5, 2])
def test_large_cover_uses_upgraded_source_at_display_pixel_ratio(tmp_path, scale):
    script = r'''
import math
from pathlib import Path
import sys
from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from youtube_music_native.download_view import DownloadView
from youtube_music_native.theme import ThemeState
from youtube_music_native.app import PACKAGE
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
engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty('downloadsState', downloads)
engine.rootContext().setContextProperty('themeState', theme)
engine.rootContext().setContextProperty('smallCover', small)
engine.loadData(b'import QtQuick\nimport QtQuick.Controls\nimport "."\nApplicationWindow { visible: true; width: 700; height: 700; Cover { objectName: "largeCover"; width: 300; height: 300; largeArtwork: true; mediaKey: "abcdefghijk"; source: smallCover; media: ({videoId: "abcdefghijk"}) } }', QUrl.fromLocalFile(str(PACKAGE / 'qml' / 'test.qml')))
window = engine.rootObjects()[0]
cover = window.findChild(QObject, 'largeCover')
art = cover.findChild(QObject, 'coverArtwork')
for size in (300, 600):
    cover.setProperty('width', size)
    cover.setProperty('height', size)
    for _ in range(100):
        app.processEvents()
        QTest.qWait(10)
        if cover.property('ready'):
            break
    assert art.property('source').toString() == large
    assert art.property('sourceSize').width() == math.ceil(size * float(sys.argv[2]))
    assert cover.property('ready')
    QTest.qWait(100)
    frame = window.grabWindow()
    assert not frame.isNull()
    center = frame.pixelColor(round(size * float(sys.argv[2]) / 2), round(size * float(sys.argv[2]) / 2))
    assert center.red() > 180 and center.green() < 80, center.name()
cover.setProperty('mediaKey', 'lmnopqrstuv')
cover.setProperty('media', {'videoId': 'lmnopqrstuv'})
downloads._artwork['lmnopqrstuv'] = (root / 'missing.png').as_uri()
downloads.changed.emit()
QTest.qWait(60)
assert cover.property('failedSource').endswith('missing.png')
downloads._large_artwork['lmnopqrstuv'] = {'url': large, 'width': 1200, 'height': 1200}
downloads.changed.emit()
QTest.qWait(100)
assert art.property('source').toString() == large and cover.property('ready')
cover.setProperty('visible', False)
downloads.calls.clear()
cover.setProperty('width', 400)
QTest.qWait(180)
assert not downloads.calls
cover.setProperty('visible', True)
QTest.qWait(180)
assert downloads.calls and downloads.calls[-1][1] == math.ceil(600 * float(sys.argv[2]))
window.close()
engine.deleteLater()
downloads.close()
'''
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software", "QT_SCALE_FACTOR": str(scale), "PYTHONPATH": str(Path(__file__).parents[1] / "src")}
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path), str(scale)], env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
