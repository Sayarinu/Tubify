"""Continue the current song on a phone: a music.youtube.com link and a locally drawn QR code."""

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, Property, Signal, Slot
from PySide6.QtGui import QColor, QGuiApplication, QImage

from .deep_links import share_url
from .qrcodegen import QrCode

# Collections the phone app can open as a list; mixes and radios are generated per session.
LIST_KINDS = {"playlist", "album"}
QUIET_ZONE = 4


def handoff_url(track, context, position):
    context = context or {}
    playlist = context.get("playlistId", "") if context.get("kind") in LIST_KINDS else ""
    return share_url((track or {}).get("videoId", ""), playlist, position)


def qr_data_url(text):
    """A PNG data URL with one pixel per module; QML scales it up without smoothing."""
    code = QrCode.encode_text(text, QrCode.Ecc.MEDIUM)
    size = code.get_size() + 2 * QUIET_ZONE
    image = QImage(size, size, QImage.Format.Format_Grayscale8)
    image.fill(QColor("white"))
    black = QColor("black")
    for y in range(code.get_size()):
        for x in range(code.get_size()):
            if code.get_module(x, y):
                image.setPixelColor(x + QUIET_ZONE, y + QUIET_ZONE, black)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return "data:image/png;base64," + data.toBase64().data().decode("ascii")


class Handoff(QObject):
    changed = Signal()
    requested = Signal()

    def __init__(self, player, parent=None):
        super().__init__(parent)
        self.player = player
        self._url, self._qr = "", ""

    @Property(str, notify=changed)
    def url(self):
        return self._url

    @Property(str, notify=changed)
    def qrImage(self):
        return self._qr

    @Slot()
    def open(self):
        self._url = handoff_url(self.player.currentTrack, self.player.current_context(), self.player.position)
        self._qr = qr_data_url(self._url) if self._url else ""
        self.changed.emit()
        if self._url:
            self.requested.emit()

    @Slot()
    def copy(self):
        if self._url:
            QGuiApplication.clipboard().setText(self._url)

    @Slot(bool)
    def finish(self, pause):
        if pause and self._url:
            self.player.pause()
