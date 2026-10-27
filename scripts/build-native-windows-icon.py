"""Render the shared Tubify artwork into a multi-resolution Windows ICO."""
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

app = QGuiApplication([])
renderer = QSvgRenderer(str(Path(__file__).resolve().parents[1] / "native/src/youtube_music_native/assets/music.svg"))
if not renderer.isValid():
    raise RuntimeError("Tubify artwork could not be loaded")
sizes = (16, 24, 32, 48, 64, 128, 256)
images = []
for size in sizes:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError("Could not encode icon image")
    images.append(bytes(buffer.data()))
offset = 6 + 16 * len(images)
directory = bytearray(struct.pack("<HHH", 0, 1, len(images)))
for size, data in zip(sizes, images):
    directory.extend(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
    offset += len(data)
Path(sys.argv[1]).write_bytes(directory + b"".join(images))
